from dotenv import load_dotenv
import os
import sys
load_dotenv()

import shutil
import yaml
import librosa
import argparse
import time
import torch
import torch.nn.functional as F
import torchaudio
import torchaudio.transforms as tat
import soundfile as sf
import gradio as gr
import numpy as np
import io
from pathlib import Path
import io  # 为了高效率转换出二进制数据
from scipy.io.wavfile import write  # 为了高效率转换出二进制数据
import json

from pathlib import Path
seedvc_path = (Path(__file__).parent / "seed-vc").resolve()  # 添加seed-vc路径
sys.path.insert(0, str(seedvc_path))
from modules.commons import *
from hf_utils import load_custom_model_from_hf

from models import ModelFactory


#-----
IS_GRADIO = False

TOTAL_SEMANTIC_TIME = []  # senmantic 推理时长
TOTAL_DIT_TIME = []  # Dit 推理时长
TOTAL_VOCODER_TIME = []  # Vocoder 推理时长
TOTAL_ELAPSED_TIME_MS = []  # 模型推理时长
TOTAL_INFER_TIME = []  # 记录每一次的infer—time, 每个chunk 端到端时间
TOTAL_VAD_TIME = []  # 记录每次VAD的耗时
TOTAL_PREPROCESS_TIME = []  # 记录VAD之后的预处理部分的耗时
TOTAL_AUDIO_CALLBACK_TIME = []  # Audio callback 函数总耗时
TOTAL_TO_BYTES_TIME = []  # 完成推理后，转换为 Bytes 的耗时
#-----


# Load model and configuration
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

prompt_condition, mel2, style2 = None, None, None
reference_wav_name = ""

PROMPT_LEN = 3  # in seconds
ce_dit_difference = 2  # 2 seconds

@torch.no_grad()
def cal_reference(model_set,
                  reference_wav,
                  new_reference_wav_name,
                  max_prompt_length,
                 ):
    """提前计算 prompt_condition
    """
    global prompt_condition, mel2, style2
    global reference_wav_name
    global PROMPT_LEN  # ------ 名字换成大写，全局变量
    
    # 获取各 model
    model = model_set['dit_model']
    semantic_fn = model_set['semantic_fn']
    vocoder_fn = model_set['vocoder_fn']
    campplus_model = model_set['campplus_model']
    to_mel = model_set['to_mel']
    mel_fn_args = model_set['mel_fn_args']
    
    # 计算
    sr = mel_fn_args["sampling_rate"]
    hop_length = mel_fn_args["hop_size"]
    if prompt_condition is None or reference_wav_name != new_reference_wav_name or PROMPT_LEN != max_prompt_length:
        PROMPT_LEN = max_prompt_length
        print(f"Setting max prompt length to {max_prompt_length} seconds.")
        reference_wav = reference_wav[:int(sr * PROMPT_LEN)]
        reference_wav_tensor = torch.from_numpy(reference_wav).to(device)

        ori_waves_16k = torchaudio.functional.resample(reference_wav_tensor, sr, 16000)  # 这里也是先转换成了16k
        S_ori = semantic_fn(ori_waves_16k.unsqueeze(0))
        feat2 = torchaudio.compliance.kaldi.fbank(
            ori_waves_16k.unsqueeze(0), num_mel_bins=80, dither=0, sample_frequency=16000
        )
        feat2 = feat2 - feat2.mean(dim=0, keepdim=True)
        style2 = campplus_model(feat2.unsqueeze(0))

        mel2 = to_mel(reference_wav_tensor.unsqueeze(0))  # mel2 是需要 22050k的，所以reference-wav先动
        target2_lengths = torch.LongTensor([mel2.size(2)]).to(mel2.device)
        prompt_condition = model.length_regulator(
            S_ori, ylens=target2_lengths, n_quantizers=3, f0=None
        )[0]

        reference_wav_name = new_reference_wav_name
        
        # 最终输出的是 prompt_condition ; 16k-need
        #            style2 ;  16k-need
        #            mel2 ; 22050-need

@torch.no_grad()
def custom_infer(model_set,
                 reference_wav,
                 new_reference_wav_name,
                 input_wav_res,  # 这里是16k的输入
                 block_frame_16k,
                 skip_head,
                 skip_tail,
                 return_length,
                 diffusion_steps,
                 inference_cfg_rate,
                 max_prompt_length,
                 ):
    global prompt_condition, mel2, style2
    global reference_wav_name
    global PROMPT_LEN  # ------ 名字换成大写，全局变量
    global ce_dit_difference  # 这里新加了一个参数，干嘛的？
    
    # 获取各 model
    model = model_set['dit_model']
    semantic_fn = model_set['semantic_fn']
    dit_fn = model_set['dit_fn']  
    vocoder_fn = model_set['vocoder_fn']
    campplus_model = model_set['campplus_model']
    to_mel = model_set['to_mel']
    mel_fn_args = model_set['mel_fn_args']
    
    sr = mel_fn_args["sampling_rate"]
    hop_length = mel_fn_args["hop_size"]
    # ---- 这里用不上，先彻底注释掉
    # if prompt_condition is None or reference_wav_name != new_reference_wav_name or PROMPT_LEN != max_prompt_length:
    #     print("哎嗨，我进来计算reference了！")  # ------ 增加一个信号
    #     PROMPT_LEN = max_prompt_length
    #     print(f"Setting max prompt length to {max_prompt_length} seconds.")
    #     reference_wav = reference_wav[:int(sr * PROMPT_LEN)]
    #     reference_wav_tensor = torch.from_numpy(reference_wav).to(device)

    #     ori_waves_16k = torchaudio.functional.resample(reference_wav_tensor, sr, 16000)
    #     S_ori = semantic_fn(ori_waves_16k.unsqueeze(0))
    #     feat2 = torchaudio.compliance.kaldi.fbank(
    #         ori_waves_16k.unsqueeze(0), num_mel_bins=80, dither=0, sample_frequency=16000
    #     )
    #     feat2 = feat2 - feat2.mean(dim=0, keepdim=True)
    #     style2 = campplus_model(feat2.unsqueeze(0))

    #     mel2 = to_mel(reference_wav_tensor.unsqueeze(0))
    #     target2_lengths = torch.LongTensor([mel2.size(2)]).to(mel2.device)
    #     prompt_condition = model.length_regulator(
    #         S_ori, ylens=target2_lengths, n_quantizers=3, f0=None
    #     )[0]

    #     reference_wav_name = new_reference_wav_name
    # ---- 这里用不上，先彻底注释掉

    converted_waves_16k = input_wav_res  # 这里转换成 16k 了已经？
    start_event = torch.cuda.Event(enable_timing=True)
    end_event = torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    start_event.record()
    S_alt = semantic_fn(converted_waves_16k.unsqueeze(0))  # 之前一大段whisper的计算，这里成了一行，very nice
    end_event.record()
    torch.cuda.synchronize()  # Wait for the events to be recorded!
    elapsed_time_ms_semantic = start_event.elapsed_time(end_event)

    S_alt = S_alt[:, ce_dit_difference * 50:]  # 这是新的改动，干嘛的？
    target_lengths = torch.LongTensor([(skip_head + return_length + skip_tail - ce_dit_difference * 50) / 50 * sr // hop_length]).to(S_alt.device)
    cond = model.length_regulator(
        S_alt, ylens=target_lengths , n_quantizers=3, f0=None
    )[0]
    cat_condition = torch.cat([prompt_condition, cond], dim=1)
    
    #---------------
    # 参数优化for 推理加速
    # diffusion_steps += 1  # 模型代码还没有改，这里先注释掉
    
    #---------------
    
    
    #----------------
    # bs 测试
    bs = 1
    
    if cat_condition.shape[0] != bs:
        cat_condition = cat_condition.repeat(bs, 1, 1)
    x_lens = torch.LongTensor([cat_condition.size(1)]).to(mel2.device)  # 先把变量拿过来
    # x_lens = x_lens.repeat(bs, 1)
    if mel2.shape[0] != bs:
        mel2 = mel2.repeat(bs,1,1)
    if style2.shape[0] != bs:
        style2 = style2.repeat(bs,1)
    #----------------
    
    # vc_target = model.cfm.forward(
    #     cat_condition,
    #     x_lens,
    #     mel2,
    #     style2,
    #     # None,  # 去掉 f0 的输入
    #     n_timesteps=diffusion_steps,  # 去掉 ds 输入
    #     # inference_cfg_rate=inference_cfg_rate,  # 去掉 inference_cfg_rate 输入
    # )
    
    # ----------------
    # 增加 dit 的时间消耗记录
    start_event = torch.cuda.Event(enable_timing=True)
    end_event = torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    start_event.record()
    # ----------------
    
    # -----------------
    vc_target = dit_fn(   # 这里改成调用 dit_fn
        cat_condition,
        x_lens,  # ----- 这里改成上面的值了，不做临时变量了
        mel2,
        style2,
        None,
        n_timesteps=diffusion_steps,
        inference_cfg_rate=inference_cfg_rate,
    )
    vc_target = vc_target[:, :, mel2.size(-1) :]
    # print(f"vc_target.shape: {vc_target.shape}")  # -----这行注释掉，不显示了
    
    # ----------------
    # 增加 dit 的时间消耗记录
    end_event.record()
    torch.cuda.synchronize()  # Wait for the events to be recorded!
    elapsed_time_ms_dit = start_event.elapsed_time(end_event)
    # ----------------
    
    
    # ----------------
    # 增加 vocoder 的时间消耗记录
    start_event = torch.cuda.Event(enable_timing=True)
    end_event = torch.cuda.Event(enable_timing=True)
    torch.cuda.synchronize()
    start_event.record()
    # ----------------
    vc_wave = vocoder_fn(vc_target).squeeze()
    # ----------------
    # 增加 vocoder 的时间消耗记录
    end_event.record()
    torch.cuda.synchronize()  # Wait for the events to be recorded!
    elapsed_time_ms_vocoder = start_event.elapsed_time(end_event)
    # ----------------
    
    output_len = return_length * sr // 50
    tail_len = skip_tail * sr // 50
    
    # -------------
    # output 增加 batch-size 的兼容
    if len(vc_wave.shape) == 2:
        output = vc_wave[0, -output_len - tail_len: -tail_len]
    else:
        output = vc_wave[-output_len - tail_len: -tail_len]  # 原版的
    # -------------
    
    # -------------
    # 时间记录
    print(f"Model_Time: ( semantic: {elapsed_time_ms_semantic:0.1f}ms | dit: {elapsed_time_ms_dit:0.1f}ms | vocoder: {elapsed_time_ms_vocoder:0.1f}ms )")
    TOTAL_SEMANTIC_TIME.append(elapsed_time_ms_semantic)
    TOTAL_DIT_TIME.append(elapsed_time_ms_dit)
    TOTAL_VOCODER_TIME.append(elapsed_time_ms_vocoder)
    # -------------
    
    return output

class Config:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

if __name__ == "__main__":
    class GUIConfig:
        def __init__(self) -> None:
            self.reference_audio_path: str = ""
            # self.index_path: str = ""
            self.diffusion_steps: int = 10
            self.sr_type: str = "sr_model"
            self.block_time: float = 0.25  # s
            self.threhold: int = -60
            self.crossfade_time: float = 0.05
            self.extra_time: float = 2.5
            self.extra_time_right: float = 2.0
            self.I_noise_reduce: bool = False
            self.O_noise_reduce: bool = False
            self.inference_cfg_rate: float = 0.7
            self.sg_hostapi: str = ""
            self.wasapi_exclusive: bool = False
            self.sg_input_device: str = ""
            self.sg_output_device: str = ""


    class GUI:
        def __init__(self) -> None:
            self.gui_config = GUIConfig()
            self.config = Config()
            self.function = "vc"   # 这个看起来有两个枚举值 [vc, im]
            self.delay_time = 0
            self.hostapis = None
            self.input_devices = None
            self.output_devices = None
            self.input_devices_indices = None
            self.output_devices_indices = None
            self.stream = None
            self.model_set = ModelFactory().get_models()  
            self.reference_wav = None # 先置None
            self.vad_model = self.model_set["vad_model"]
            
            # 尝试2
            from modelscope.pipelines import pipeline
            from modelscope.utils.constant import Tasks
            self.denoise_fn = pipeline(
                    Tasks.acoustic_noise_suppression,
                    # model='damo/speech_dfsmn_ans_psm_48k_causal',
                    model="checkpoints/modelscope_cache/hub/damo/speech_dfsmn_ans_psm_48k_causal",
                    stream_mode=True)
            #---------------
            
            self.launcher()
            

        def load(self):
            try:
                os.makedirs("configs/inuse", exist_ok=True)
                if not os.path.exists("configs/inuse/config.json"):
                    shutil.copy("configs/config.json", "configs/inuse/config.json")
                with open("configs/inuse/config.json", "r") as j:
                    data = json.load(j)  # 在这里应该会报错，config时个空的，会进入except
                    data["sr_model"] = data["sr_type"] == "sr_model"  # sr_model 是一个bool值
                    data["sr_device"] = data["sr_type"] == "sr_device"  # sr_device 也是一个 bool 值, 看起来 sr_type 有两种值 sr_model 或者 sr_device
                    if data["sg_hostapi"] in self.hostapis:
                        self.update_devices(hostapi_name=data["sg_hostapi"])
                        if (
                            data["sg_input_device"] not in self.input_devices
                            or data["sg_output_device"] not in self.output_devices
                        ):
                            self.update_devices()
                            data["sg_hostapi"] = self.hostapis[0]
                            data["sg_input_device"] = self.input_devices[
                                self.input_devices_indices.index(sd.default.device[0])
                            ]
                            data["sg_output_device"] = self.output_devices[
                                self.output_devices_indices.index(sd.default.device[1])
                            ]
                    else:
                        data["sg_hostapi"] = self.hostapis[0]
                        data["sg_input_device"] = self.input_devices[
                            self.input_devices_indices.index(sd.default.device[0])
                        ]
                        data["sg_output_device"] = self.output_devices[
                            self.output_devices_indices.index(sd.default.device[1])
                        ]
            except:
                with open("configs/inuse/config.json", "w") as j:
                    data = {
                        "source_path": "g.wav",
                        "save_dir": "testsets/output/",
                        "reference_audio_path": "testsets/000042.wav",
                        "sr_type": "sr_model",  # 
                        "block_time": 0.5,  # 0.5 ；这里的 block time 是 0.5s
                        "crossfade_length": 0.04,  # 0.04 ；用于平滑过渡的交叉渐变长度，这里设定为 0.04 秒。交叉渐变通常用于避免声音中断或“断层”现象。
                        "extra_time": 2.5,  # 2.5；  附加时间，设置为 0.5秒。可能用于在处理音频时延长或平滑过渡的时间。
                                            # 原本默认0.5，后面更新成2.5了
                        "extra_time_right": 0.02, # 0.02； 可能是与“右声道”相关的额外时间，设置为 0.02秒。看起来是为了为右声道音频数据添加一些额外的处理时间。
                        "diffusion_steps": 10, # 10； 
                        "inference_cfg_rate": 0.7, # 0.7；
                        "max_prompt_length": 3.0, # 3；
                    }
                    data["sr_model"] = data["sr_type"] == "sr_model"  # True
                    data["sr_device"] = data["sr_type"] == "sr_device"  # False
                    
                    
                    
                    # ----------------------------
                    # 直接在这边读区的时候赋值了
                    self.gui_config.reference_audio_path = data["reference_audio_path"]
                    self.gui_config.sr_type = ["sr_model", "sr_device"][
                        [
                            data["sr_model"],
                            data["sr_device"],
                        ].index(True)
                    ]
                    # self.gui_config.threhold = data["threhold"]
                    self.gui_config.diffusion_steps = data["diffusion_steps"]
                    self.gui_config.inference_cfg_rate = data["inference_cfg_rate"]
                    self.gui_config.max_prompt_length = data["max_prompt_length"]
                    self.gui_config.block_time = data["block_time"]
                    self.gui_config.crossfade_time = data["crossfade_length"]
                    self.gui_config.extra_time = data["extra_time"]
                    self.gui_config.extra_time_right = data["extra_time_right"]
                    self.gui_config.save_dir = data['save_dir']  # 新增存储路径
                    self.gui_config.source_path = data['source_path']  # 新增 output name， gradio时默认的名字
                    # ----------------------------
                    
            return data
     
        def launcher(self):
            self.config = Config()  # 这个Config只有device，cuda或者cpu
            data = self.load()  # 一些参数配置
            
            with gr.Blocks(title="换声测试") as app:
                gr.Markdown("## 换声测试")

                with gr.Row():
                    inputs = gr.Audio(type="numpy")
                    outputs=gr.Audio(type="numpy", streaming=True, format='mp3')
                    
                inputs.change(fn=self.infer, inputs=inputs, outputs=outputs)
            
            if IS_GRADIO:
                app.launch(
                    server_name="0.0.0.0",
                    server_port=6006,
                    quiet=False
                )
                
        def load_reference_wav(self):
            """给外置计算reference对应模型输入用的
            """
            self.reference_wav, _ = librosa.load(
                    self.gui_config.reference_audio_path, sr=self.model_set["mel_fn_args"]["sampling_rate"]  # 22050
            )
       
       
        def infer(self, input_audio):
            """
            input_audio: 为了兼容gradio, [sr, wav]
            """
            # -------------------------
            # start vc 部分
            # -------------------------
            torch.cuda.empty_cache()
            
            # ---- referebce 彻底放在外面读取
            # if self.reference_wav is None:
            #     self.reference_wav, _ = librosa.load(
            #         self.gui_config.reference_audio_path, sr=self.model_set["mel_fn_args"]["sampling_rate"]  # 22050
            #     )
            # ---- referebce 彻底放在外面读取
                
            self.gui_config.samplerate = (
                self.model_set["mel_fn_args"]["sampling_rate"]
                if self.gui_config.sr_type == "sr_model"
                else self.get_device_samplerate()
            )  # gui-samplerate 赋值，22050
            self.gui_config.channels = 1  # 这里channel就默认是1了
            self.zc = self.gui_config.samplerate // 50  # 44100 // 100 = 441， 代表10ms; 
                                                        # 22050//50 = 441, 代表 20ms； 
                                                        # 是一个精度因子，20ms为一个最小精度。
            self.block_frame = (
                int(
                    np.round( 
                        self.gui_config.block_time
                        * self.gui_config.samplerate
                        / self.zc
                    )
                )
                * self.zc
            )  # 22050hz 对应 11025帧，对应500ms
            self.block_frame_16k = 320 * self.block_frame // self.zc  # 16k对应8000帧 ; 
                                                                      # 320帧对应的是20ms的帧数，后面的 block_frame // zc 对应 N 个20ms
                                                                      # 这就是 320帧 的固定倍数了
            self.crossfade_frame = (   # 和计算bloack_frame一样，计算出对应的 crossfade 帧
                int(
                    np.round(
                        self.gui_config.crossfade_time
                        * self.gui_config.samplerate
                        / self.zc
                    )
                )
                * self.zc
            )
            self.sola_buffer_frame = min(self.crossfade_frame, 4 * self.zc) # 80ms帧 和 crossfade帧(默认40ms)中的小数
            self.sola_search_frame = self.zc  # sola_search 20ms帧
            self.extra_frame = (  # 同理
                int(
                    np.round(
                        self.gui_config.extra_time
                        * self.gui_config.samplerate
                        / self.zc
                    )
                )
                * self.zc
            )
            self.extra_frame_right = (  # 同理
                    int(
                        np.round(
                            self.gui_config.extra_time_right
                            * self.gui_config.samplerate
                            / self.zc
                        )
                    )
                    * self.zc
            )
            self.input_wav: torch.Tensor = torch.zeros(  # 变量出了这里几个意外，还有一个 sola-buffer
                self.extra_frame
                + self.crossfade_frame
                + self.sola_search_frame
                + self.block_frame
                + self.extra_frame_right,
                device=self.config.device,
                dtype=torch.float32,
            )  # 2 * 44100 + 0.08 * 44100 + 0.01 * 44100 + 0.25 * 44100
            self.input_wav_denoise: torch.Tensor = self.input_wav.clone()  # ------- 整个篇目仅此一家
            self.input_wav_res: torch.Tensor = torch.zeros(
                320 * self.input_wav.shape[0] // self.zc,
                device=self.config.device,
                dtype=torch.float32,
            )  # input wave 44100 -> 16000   # 16k对应的 input_wav
            self.rms_buffer: np.ndarray = np.zeros(4 * self.zc, dtype="float32")  # callback里面用上的地方，被注释掉了
            self.sola_buffer: torch.Tensor = torch.zeros(
                self.sola_buffer_frame, device=self.config.device, dtype=torch.float32
            )
            self.nr_buffer: torch.Tensor = self.sola_buffer.clone()
            self.output_buffer: torch.Tensor = self.input_wav.clone()
            self.skip_head = self.extra_frame // self.zc
            self.skip_tail = self.extra_frame_right // self.zc
            self.return_length = (
                self.block_frame + self.sola_buffer_frame + self.sola_search_frame
            ) // self.zc
            self.fade_in_window: torch.Tensor = (
                torch.sin(
                    0.5
                    * np.pi
                    * torch.linspace(
                        0.0,
                        1.0,
                        steps=self.sola_buffer_frame,
                        device=self.config.device,
                        dtype=torch.float32,
                    )
                )
                ** 2
            ) # 一个tensor，0-1的序列(共sola_buffer_frame个元素)，经过sin再经过平方，整体就是平滑的从 0 到 1。
            self.fade_out_window: torch.Tensor = 1 - self.fade_in_window  # 反向的，这样对于前面和后面的一个 fade-out，一个 fade-in
            self.resampler = tat.Resample(
                orig_freq=self.gui_config.samplerate,
                new_freq=16000,
                dtype=torch.float32,
            ).to(self.config.device)  # 用于从 22050 降低到 16000； 更精细点是从 gui-samplerate 到 16k
                                      # 也就是说有3个samplerate，model-sampelrate, gui-samplerate, 16k
                                      # 但是一般 model和gui的相同； 那么就是两个samplerate： 22050， 16k
            if self.model_set["mel_fn_args"]["sampling_rate"] != self.gui_config.samplerate:  # resampler2 是从 model-samplerate => gui-samplerate
                self.resampler2 = tat.Resample(
                    orig_freq=self.model_set["mel_fn_args"]["sampling_rate"],
                    new_freq=self.gui_config.samplerate,
                    dtype=torch.float32,
                ).to(self.config.device)
            else:
                self.resampler2 = None  
            # ---------------------------------
            # 与2024-11-27一致，在这个地方加入 vad
            self.vad_cache = {}
            self.vad_chunk_size = 1000 * self.gui_config.block_time
            self.vad_speech_detected = False
            self.set_speech_detected_false_at_end_flag = False
            # ---------------------------------
        
        
            # -------------------------
            # start stream 部分
            # -------------------------
            # input_sr, input_audio_data = self.audio_preprocess(input_audio)  # 这里给gradio留着，如果还有需要的话。
            input_sr, input_audio_data = input_audio
            
            # -----  这里的 22050 转换可以删去
            # if input_sr != self.gui_config.samplerate:    # TODO-1
            #     print(f'输入音频重采样:{input_sr} => {self.gui_config.samplerate}')  # 这里是重采样到 22050
            #     input_audio_data = librosa.resample(input_audio_data, orig_sr=input_sr, target_sr=self.gui_config.samplerate)
            # -----   直接用 16k 音频
            
    
            # num_blocks = len(input_audio_data) // self.block_frame 
            num_blocks = len(input_audio_data) // self.block_frame_16k  # 这里block-frame改成16k
            total_output = []     
            for i in range(num_blocks):
                # ---------------------
                # 增加每个chunk整体时间记录
                print("------Chunk In------")
                infer_start_time = time.time()                
                # ----------------------
                
                # block = input_audio_data[i * self.block_frame: (i + 1) * self.block_frame]  
                block = input_audio_data[i * self.block_frame_16k: (i + 1) * self.block_frame_16k]  # 这里也切换成16k
                
                # 传递给 callback 函数处理
                output_wave = self.audio_callback(block).reshape(-1,)  # 这里出来的是22050的音频
                total_output.append(output_wave)  # 这里是存储的地方
                
                # 转换成有效输出
                t_trans_start = time.time()  # ---- 增加转换时间记录
                output_wave = (output_wave * 32768.0).astype(np.int16)  # 这里和最终存储音频无关，源代码也是这样，是为了转化成mp3
                # wav_bytes = AudioSegment(
                #     output_wave.tobytes(), frame_rate=self.gui_config.samplerate,
                #     sample_width=output_wave.dtype.itemsize, channels=1
                # ).export(format="mp3").read()
                # -------------
                # 换一种方式转换成二进制码
                wav_buffer = io.BytesIO()  # 使用 io.BytesIO 来存储 WAV 数据
                write(wav_buffer, self.gui_config.samplerate, output_wave)  # 用 scipy 的 write 函数直接写入 WAV 格式
                wav_bytes = wav_buffer.getvalue()  # 获取 WAV 数据
                # -------------
                
                # -------------
                t_trans_end = time.time()  # ---- 增加转换时间记录
                to_bytes_time = (t_trans_end-t_trans_start)*1000  # --- 单独计算一下
                print(f'To_Bytes_Time: {to_bytes_time:0.1f}') # ---- 增加转换时间记录
                TOTAL_TO_BYTES_TIME.append(to_bytes_time)
                # -------------
                
                # 最后一个chunk，保存
                if i == (num_blocks - 1):
                    # 输出路径的名字
                    output_path = (str(Path(self.gui_config.save_dir).joinpath('.'.join(Path(self.gui_config.source_path).name.split('.')[:-1]))) 
                                   + f"_stream_ds{self.gui_config.diffusion_steps}"
                                   + f"_ref-{'.'.join(Path(self.gui_config.reference_audio_path).name.split('.')[:-1])}"
                                   + ".wav"
                                   )
                    sf.write(output_path, np.concatenate(total_output), self.gui_config.samplerate)
                    print(f"完整音频已存储:{output_path}")
                    
                # ---------------------
                # 增加每个chunk整体时间记录
                infer_end_time = time.time()
                infer_use_time = (infer_end_time - infer_start_time)*1000
                print(f"Chunk_Total_Time: {infer_use_time:0.1f}ms")
                TOTAL_INFER_TIME.append(infer_use_time)
                print("------Chunk Out------", end='\n\n')
                # ----------------------
                yield wav_bytes
                    
        def audio_preprocess(self, audio:tuple):
            sample_rate, audio_data = audio  # 解包音频数据
            # print(audio_data) 
            # print(type(audio_data[0]))
            assert isinstance(audio_data, np.ndarray)
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=0)  # 合并为单声道（简单的做法）
                print(f"audio_data channels bigger than 1:{audio_data.ndim}")
                
            if isinstance(audio_data[0], np.int16):
                audio_data = audio_data.astype(np.float32) / 32768.0 
            return sample_rate, audio_data

        def audio_callback(
            self, indata: np.ndarray
        ):
            print("Audio_callback in...")
            """
            Audio block callback function
            """
            # print(indata.shape)
            start_time = time.perf_counter()
            indata = librosa.to_mono(indata.T)  # 转换完之后的indata shape: (11025,), max=1.0116995573043823, min=-1.0213052034378052
            
            # if self.gui_config.threhold > -60:
            #     indata = np.append(self.rms_buffer, indata)
            #     rms = librosa.feature.rms(
            #         y=indata, frame_length=4 * self.zc, hop_length=self.zc
            #     )[:, 2:]
            #     self.rms_buffer[:] = indata[-4 * self.zc :]
            #     indata = indata[2 * self.zc - self.zc // 2 :]
            #     db_threhold = (
            #         librosa.amplitude_to_db(rms, ref=1.0)[0] < self.gui_config.threhold
            #     )
            #     for i in range(db_threhold.shape[0]):
            #         if db_threhold[i]:
            #             indata[i * self.zc : (i + 1) * self.zc] = 0
            #     indata = indata[self.zc // 2 :]
            
            # ----- 原本预处理注释掉 -----
            # self.input_wav[: -self.block_frame] = self.input_wav[
            #     self.block_frame :
            # ].clone()  # 平移 block-frame，留给新的indata
            #            # 改成 16k 之后，这里先不变
            # self.input_wav[-indata.shape[0] :] = torch.from_numpy(indata).to(
            #     self.config.device
            # )  # indata 进入
            # self.input_wav_res[: -self.block_frame_16k] = self.input_wav_res[
            #     self.block_frame_16k :
            # ].clone()  # input_res 做同样的操作
            # self.input_wav_res[-320 * (indata.shape[0] // self.zc + 1) :] = (
            #     self.resampler(self.input_wav[-indata.shape[0] - 2 * self.zc :])[
            #         320:
            #     ]
            # )  # 这里有点小动作，resampler的时候多加了2个zc，应该是为了resample的更好，然后再取一个 zc + indata长度，和赋值的 + 1 对应上了
            #    # 在 16k 里，一个zc就是320
            #    #  那这个耗时也清楚了是 resampler 导致的
            # ----- 原本预处理注释掉 -----
            
            # -------------------------------
            # 预处理直接全改，改成16k对应的预处理
            # assert indata.shape[0] == self.block_frame_16k
            self.input_wav_res[: -self.block_frame_16k] = self.input_wav_res[
                self.block_frame_16k :
            ].clone()  # input_res 做同样的操作; # 先做平移
            # self.input_wav_res = torch.roll(self.input_wav_res, shifts=-self.block_frame_16k, dims=0)  # 使用更高效的平移手段。
            #                                                                                            # 负方向滚动
            self.input_wav_res[-indata.shape[0] :] = torch.from_numpy(indata).to(
                self.config.device
            )  # indata 进入;  # 再填值
            # ------------------------------
            preprocess_Time = (time.perf_counter() - start_time)*1000  # ----  放到外面来
            print(f"Preprocess_Time: {preprocess_Time:.1f}ms")  # ----- 改成ms
            TOTAL_PREPROCESS_TIME.append(preprocess_Time)  # ---- 增加全局的记录
            
        
            # ------------------------------
            # 这里加入降噪模块
            
            
            
            
            
            
            
            
            
            # -----------------------------
            
            
            
            
            
            
            
            
            
            
            # -----------------------
            # 与新版一致，这里加入vad模块
            # 这里把vad放到预处理的后面来，为了加入降噪模块后性能更好
            # 本身vad和预处理两个就是独立的，互不影响，谁放前面都行
            # VAD first
            start_event = torch.cuda.Event(enable_timing=True)
            end_event = torch.cuda.Event(enable_timing=True)
            torch.cuda.synchronize()
            start_event.record()
            # indata_16k = librosa.resample(indata, orig_sr=self.gui_config.samplerate, target_sr=16000)  # 由于输入本来就是16k，这里也省略了
            indata_16k = indata  # 改成直接赋值
            res = self.vad_model.generate(input=indata_16k, cache=self.vad_cache, is_final=False, chunk_size=self.vad_chunk_size)  # ---- 改成优化后的函数
            # res = self.vad_model_generate(input=indata_16k, cache=self.vad_cache, is_final=False, chunk_size=self.vad_chunk_size)  # ---- 改成优化后的函数， 验证失败
            res_value = res[0]["value"]
            # print(res_value)
            if len(res_value) % 2 == 1 and not self.vad_speech_detected:
                self.vad_speech_detected = True
            elif len(res_value) % 2 == 1 and self.vad_speech_detected:
                self.set_speech_detected_false_at_end_flag = True
            end_event.record()
            torch.cuda.synchronize()  # Wait for the events to be recorded!
            elapsed_time_ms = start_event.elapsed_time(end_event)
            print(f"VAD_Time: {elapsed_time_ms:0.1f}ms")
            
            TOTAL_VAD_TIME.append(elapsed_time_ms)  # 这里增加一个全局VAD均值计算
            # -----------------------

            
                
            # -------------------------------
            # 与新版一致，加入vad部分
            # 它这个有点奇怪为什么先推理再放，其实可以直接返回zeros的
            if not self.vad_speech_detected:
                print(f"speech not detected...")
                infer_wav = torch.zeros_like(self.input_wav[self.extra_frame :])  # 这里只是取了一个维度，与里面的值无关
            # --------------------------------
            else:  # 这里逻辑改成如果有说话人，才进入推理，而不是每次无脑推了。没有推理的时间也不会记录。
                # infer
                start_event = torch.cuda.Event(enable_timing=True)
                end_event = torch.cuda.Event(enable_timing=True)
                torch.cuda.synchronize()
                start_event.record()
                infer_wav = custom_infer(
                    self.model_set,
                    self.reference_wav,
                    self.gui_config.reference_audio_path,
                    self.input_wav_res,  # 整个input_res 放进去了。
                    self.block_frame_16k,
                    self.skip_head,
                    self.skip_tail,
                    self.return_length,
                    int(self.gui_config.diffusion_steps),
                    self.gui_config.inference_cfg_rate,
                    self.gui_config.max_prompt_length,
                )
                if self.resampler2 is not None:
                    infer_wav = self.resampler2(infer_wav)
                end_event.record()
                torch.cuda.synchronize()  # Wait for the events to be recorded!
                elapsed_time_ms = start_event.elapsed_time(end_event)
                print(f"Total_Model_Time: {elapsed_time_ms:0.1f}ms")
                TOTAL_ELAPSED_TIME_MS.append(elapsed_time_ms)
            # --------------------------------

            # SOLA algorithm from https://github.com/yxlllc/DDSP-SVC
            conv_input = infer_wav[
                None, None, : self.sola_buffer_frame + self.sola_search_frame  # 这里说明前面的 input_wav 那一堆还不能删
            ]  # 这里取的是 0 : sola_buffer+sola_search 的长度
               # None， None 是拓展新的维度，比如 一维变三维

            cor_nom = F.conv1d(conv_input, self.sola_buffer[None, None, :])  # sola-buffer 一开始是zeros
                                                                             # 这里是滑动窗口 点积， 每个buffer-frame的长度跟buffer点积
                                                                             # 结果是的到长度为 sola_search_frame + 1 的值
            cor_den = torch.sqrt(
                F.conv1d(
                    conv_input**2,
                    torch.ones(1, 1, self.sola_buffer_frame, device=self.config.device),
                )
                + 1e-8
            )   # 这里是求分母，input**2 是能量，在 sola_buffer上卷积，最终也得到 sola_search_frame + 1 的长度
            if sys.platform == "darwin":
                _, sola_offset = torch.max(cor_nom[0, 0] / cor_den[0, 0])
                sola_offset = sola_offset.item()
            else:
                sola_offset = torch.argmax(cor_nom[0, 0] / cor_den[0, 0])  # 这里就是相似度了，找到最相似的 arg

            print(f"sola_offset = {int(sola_offset)}")

            #post_process_start = time.perf_counter()
            infer_wav = infer_wav[sola_offset:]  # 这里从最相似的部分索引出来
            infer_wav[: self.sola_buffer_frame] *= self.fade_in_window  # sola_buffer 的长度进行 fade_in
            infer_wav[: self.sola_buffer_frame] += (
                self.sola_buffer * self.fade_out_window
            )  # 之前的 sola_buffer 进行 fade_out
            self.sola_buffer[:] = infer_wav[
                self.block_frame : self.block_frame + self.sola_buffer_frame
            ]  # 这里再得到新的 sola_buffer, 从 block_frame 开始 增加 buffer_frame；相当于前一个音频片段推理输出
               # 由于下面输出的是最前面 block_frame的音频，这里就取后续的这部分留下来做 sola 和 fade
            outdata = (
                infer_wav[: self.block_frame]  # 每次输出一个 bloack_frame
                .t()
                .cpu()
                .numpy()
            )  # outdata.shape => (11025,)
            # ----------------------------
            # 对输出幅值再加一层限制，防止单根线那种的尖爆音
            threshold = 0.7
            outdata = np.clip(outdata, -threshold, threshold)
            # ----------------------------
            
            
            # ---------------------------
            # 对输出进行后处理降噪
            outdata = librosa.resample(outdata, orig_sr=22050, target_sr=48000)  # 先粗暴更换采样率, 这个更换之后会导致长度超长
            outdata = (outdata * 32768.0).astype(np.int16)
            result = self.denoise_fn(outdata.tobytes())
            outdata = np.frombuffer(result['output_pcm'], dtype='int16')
            outdata = outdata.astype(np.float32) / 32768.0  # 先转换成float，格式对齐，后面再改
            outdata = librosa.resample(outdata, orig_sr=48000, target_sr=22050)  # 这里先转回去，因为samplerate在保存的时候还没变
            # ---------------------------
            
            total_time = time.perf_counter() - start_time
            # --------------------------
            # 与新版一样，加入vad部分
            if self.set_speech_detected_false_at_end_flag:
                self.vad_speech_detected = False
                self.set_speech_detected_false_at_end_flag = False
            # --------------------------
            print(f"\nAudio_callback_time: {total_time*1000:.1f}ms")
            TOTAL_AUDIO_CALLBACK_TIME.append(total_time*1000)
            
            return outdata
    
    gui = GUI()
    
    # test
    if not IS_GRADIO:
        
        # -------------------------
        # 1. 参数解析
        import argparse
        def parse_args():
            parser = argparse.ArgumentParser(description="批量语音转换脚本")
            parser.add_argument('--reference_audio_path', type=str, 
                                default="wavs/references/csmsc042-s0.2.wav",
                                # default="wavs/references/csmsc042.wav", 
                                # default="wavs/references/csmsc042-s0.5.wav",
                                # default="wavs/references/csmsc042-s1.0.wav",
                                help="参考音频文件路径")
            
            parser.add_argument('--file_list', type=str, 
                                default=None, 
                                help="要处理的文件列表 (空格分隔的字符串), 没传默认为 None")
            
            parser.add_argument('--save_dir', type=str, 
                                default='wavs/outputs', 
                                help="保存目录路径")
            
            parser.add_argument('--block_time', type=float, 
                                default=0.5, 
                                help="块大小，单位秒，默认值为 0.5 秒")
            
            parser.add_argument('--crossfade_length', type=float, 
                                default=0.04, 
                                help="交叉渐变长度，单位秒，默认值为 0.04 秒")
            
            parser.add_argument('--diffusion_steps', type=int, 
                                default=10, 
                                help="扩散步骤，默认值为 3")
            
            parser.add_argument('--prompt_len', type=float, 
                                default=3, 
                                help="参考截断长度，单位秒，默认值为 3 秒")
            return parser.parse_args()

        args = parse_args()
        reference_audio_path = args.reference_audio_path
        file_list = args.file_list.split() if args.file_list else None
        save_dir = args.save_dir 
        block_time = args.block_time
        crossfade_length = args.crossfade_length
        diffusion_steps = args.diffusion_steps
        PROMPT_LEN = args.prompt_len
        
        if file_list is None:
            # 单通内部赋值
            file_list = ["wavs/cases/低沉男性-YL-2025-03-14.wav"]  
            
            # 文件夹内部赋值
            # src_path = Path("wavs/cases")
            # file_list = [file for file in src_path.iterdir() if file.is_file() and file.name.split('.')[-1] in ['wav']]

        # 输出解析后的值
        print('-'*21+"ARGS"+'-'*21)
        print(f"reference_audio_path: {reference_audio_path}")
        print(f"file_list: {file_list}")
        print(f"save_dir: {save_dir}")
        print(f"block_time: {block_time}")
        print(f"crossfade_length: {crossfade_length}")
        print(f"diffusion_steps: {diffusion_steps}")
        print(f"PROMPT_LEN: {PROMPT_LEN}")
        print('-'*42)
        # --------------------------
        

        # 2. 对应参数赋值给gui class，并做准备工作
        gui.gui_config.block_time = block_time
        gui.gui_config.crossfade_time = crossfade_length
        gui.gui_config.diffusion_steps = diffusion_steps
        gui.gui_config.reference_audio_path = reference_audio_path
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        gui.gui_config.save_dir = save_dir
        
        # 计算 reference, 因为这里外置了 reference，所以不能在初始化的时候计算
        # 这样里面的代码甚至不用改，应该不会触发计算了
        gui.load_reference_wav()  # 先读取
        cal_reference(gui.model_set,
                      gui.reference_wav,
                      gui.gui_config.reference_audio_path,
                      gui.gui_config.max_prompt_length)


        # 3. 开始VC
        print('-' * 42)
        print("准备工作完毕，开始文件夹批量换声, 请按回车继续...")
        try:
            input()
        except EOFError:
            pass  # 忽略 EOFError，直接继续
        
        for file in file_list:
                # wav, sr = librosa.load(file, sr=gui.model_set["mel_fn_args"]["sampling_rate"], mono=True)  # 22050, 默认读取为单声道
                wav, sr = librosa.load(file, sr=16000, mono=True)  # source 输入统一为16k
                gui.gui_config.source_path = str(file)
                for o in gui.infer([sr, wav]):
                    nonsense = 42
        
        # 4. 后处理，相关数据计算
        cut_num = 5
        TOTAL_VAD_TIME = TOTAL_VAD_TIME[cut_num:]  # VAD耗时
        TOTAL_PREPROCESS_TIME = TOTAL_PREPROCESS_TIME[cut_num:]  # 预处理耗时
        TOTAL_ELAPSED_TIME_MS = TOTAL_ELAPSED_TIME_MS[cut_num:]  # 模型推理耗时； 去掉前5个，设置一个比较大的冗余，测试各种方法时，前面推的会慢很多
        TOTAL_SEMANTIC_TIME = TOTAL_SEMANTIC_TIME[cut_num:]  # semantic
        TOTAL_DIT_TIME = TOTAL_DIT_TIME[cut_num:]  # dit
        TOTAL_VOCODER_TIME = TOTAL_VOCODER_TIME[cut_num:]  # vocoder
        TOTAL_AUDIO_CALLBACK_TIME = TOTAL_AUDIO_CALLBACK_TIME[cut_num:]  # audio_callback 的耗时
        TOTAL_TO_BYTES_TIME = TOTAL_TO_BYTES_TIME[cut_num:]  # 转换为Bytes的时间
        TOTAL_INFER_TIME = TOTAL_INFER_TIME[cut_num:]  # 这个是从INFER进入到出来的完整时间
        
        
        print(f"---Audio CallBack---")
        print(f"平均每chunk VAD 耗时: {np.mean(TOTAL_VAD_TIME):0.1f}ms")  # VAD平均耗时
        print(f"平均每chunk 预处理 耗时: {np.mean(TOTAL_PREPROCESS_TIME):0.1f}ms")  # 预处理耗时
        print(f"Model:")
        print(f"    Semantic: {np.mean(TOTAL_SEMANTIC_TIME):0.1f}ms")
        print(f"    Dit: {np.mean(TOTAL_DIT_TIME):0.1f}ms")
        print(f"    Vocoder: {np.mean(TOTAL_VOCODER_TIME):0.1f}ms")
        print(f"平均每chunk 模型推理 耗时: {np.mean(TOTAL_ELAPSED_TIME_MS):0.1f}ms")  # 计算平均推理时长
        print(f"---Chunk 端到端---")
        print(f"平均每chunk Audio-CallBack总体 耗时: {np.mean(TOTAL_AUDIO_CALLBACK_TIME):0.1f}ms")
        print(f"平均每chunk to_bytes 耗时: {np.mean(TOTAL_TO_BYTES_TIME):0.1f}ms")
        print(f"平均每chunk 端到端时长: {np.mean(TOTAL_INFER_TIME):0.1f}ms")  # 计算平均推理时长
 
