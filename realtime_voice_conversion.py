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
from pydantic import BaseModel, Field
from rich import print
from collections import deque
from loguru import logger
import traceback

from pathlib import Path
seedvc_path = (Path(__file__).parent / "seed-vc").resolve()  # 添加seed-vc路径
sys.path.insert(0, str(seedvc_path))
from modules.commons import *
from hf_utils import load_custom_model_from_hf

from models import ModelFactory


class RealtimeVoiceConversionConfig(BaseModel):
    reference_audio_path: str = "testsets/000042.wav"
    
    sr_type: str = "sr_model"  # 这个指的是 samplerate 来自哪里，是model本身，还是设备 device，获取设备的 samplerate
    block_time: float = 0.5,  # 0.5 ；这里的 block time 是 0.5s
    
    # noise_gata
    noise_gate: bool = True  # 是否使用噪声门
    noise_gate_threshold: float = -60  # 噪声门的阈值，单位是分贝，-60dB
    
    diffusion_steps: int = 10  # 10； 
    
    crossfade_time: float = 0.04,  # 0.04 ；用于平滑过渡的交叉渐变长度，这里设定为 0.04 秒。交叉渐变通常用于避免声音中断或“断层”现象。
    extra_time: float = 2.5  # 2.5；  附加时间，设置为 0.5秒。可能用于在处理音频时延长或平滑过渡的时间。
                             # 原本默认0.5，后面更新成2.5了
    extra_time_right: float = 0.02  # 0.02； 可能是与“右声道”相关的额外时间，设置为 0.02秒。看起来是为了为右声道音频数据添加一些额外的处理时间。 
                                    # 这里RVC好像默认的是2s，需要后续对比一下
    I_noise_reduce: bool = False
    O_noise_reduce: bool = False
    inference_cfg_rate: float = 0.7  # 0.7；
    sg_hostapi: str = ""
    wasapi_exclusive: bool = False
    sg_input_device: str = ""
    sg_output_device: str = ""
    
    max_prompt_length: float = 3.0 # 3；
    save_dir: str = "wavs/output/"  # 存储
    source_path: str = "g.wav"  # 源音频文件的地址
    
    ce_dit_difference: float = 2  # 2 seconds  # 这个参数还不知道是用来干嘛的
    
    samplerate: float = None  # infer的时候会赋值
    
    rms_mix_rate: float = 0    # 0.25； 这个参数是用来控制 RMS 混合的比例，
                               # 范围是 0 到 1。
                               # 0 表示完全使用 Input 的包络，1 表示完全使用 Infer 包络。
    
    device: str = str(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    
    max_tracking_counter: int = 10_000  # 用于记录单chunk推理时间损耗的最大记录数量
    

class RealtimeVoiceConversion:
    def __init__(self, cfg:RealtimeVoiceConversionConfig) -> None:
        self.cfg = cfg
        self.models = ModelFactory(device=self.cfg.device).get_models()  
        self._init_performance_tracking()  # 初始化耗时记录
        self.reference = self._update_reference()
        self.vad_model = self.models["vad_model"]
    
    def _init_performance_tracking(self):
        """初始化耗时记录，用于计算平均各模块耗时
        """
        self.vad_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次VAD的耗时
        self.noise_gate_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次噪声门的耗时
        self.preprocessing_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次预处理的耗时
        
        self.senmantic_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次senmantic推理的耗时
        self.dit_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次dit推理的耗时
        self.vocoder_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次vocoder推理的耗时
        self.vc_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次换声模型整体推理的耗时
        
        self.rms_mix_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次RMS混合的耗时
        self.sola_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次SOLA算法的耗时
        
        self.chunk_time = deque(maxlen=self.cfg.max_tracking_counter)  # 用于记录每次chunk整体推理的耗时
        
        self.tracking_counter = 0  # 用于记录时间的计数器
        
    def _performance_report(self):
        """Report module timing statistics"""
        msg = "\n"
        time_records = {
            "VAD": self.vad_time,
            "Noise Gate": self.noise_gate_time,
            "Preprocessing": self.preprocessing_time,
            "Semantic Extraction": self.senmantic_time,
            "Diffusion Model": self.dit_time,
            "Vocoder": self.vocoder_time,
            "Voice Conversion Overall": self.vc_time,
            "RMS Mixing": self.rms_mix_time,
            "SOLA Algorithm": self.sola_time,
            "Chunk Overall": self.chunk_time
        }
        
        
        msg += "========== Voice Conversion Module Timing Statistics (ms) ==========\n"
        stats = {}
        for name, records in time_records.items():
            if not records:  # Skip if queue is empty
                continue
                
            records_arr = np.array(list(records)) * 1000 # Convert to milliseconds
            temp_stats = {
                "Mean": f"{np.mean(records_arr):0.1f}",
                "Min": f"{np.min(records_arr):0.1f}",
                "Max": f"{np.max(records_arr):0.1f}",
                "Median": f"{np.median(records_arr):0.1f}",
                "Std Dev": f"{np.std(records_arr):0.1f}",
                "Count": len(records)
            }
            stats[name] = temp_stats    
        
        msg += json.dumps(stats, indent=4, ensure_ascii=False) + "\n"
        msg += "====================================================================\n"
        logger.info(msg)
        
    def _update_reference(self):
        """读取reference音频，并计算相关的模型输入
        """
        reference_wav = self._load_reference_wav()
        reference = self._cal_reference(reference_wav=reference_wav)
        return reference
        
    def _load_reference_wav(self):
        """给外置计算reference对应模型输入用的
        """
        reference_wav, _ = librosa.load(
                self.cfg.reference_audio_path, sr=self.models["mel_fn_args"]["sampling_rate"]  # 22050
        )
        return reference_wav
    
    @torch.no_grad()
    def _cal_reference(self, reference_wav):
        """计算reference相关的模型输入
        """
        
        # 获取各 model
        model = self.models['dit_model']
        semantic_fn = self.models['semantic_fn']
        campplus_model = self.models['campplus_model']
        to_mel = self.models['to_mel']
        mel_fn_args = self.models['mel_fn_args']
        
        # 计算
        sr = mel_fn_args["sampling_rate"]
        reference_wav = reference_wav[:int(sr * self.cfg.max_prompt_length)]  # reference_wav如果不够长，会截断
        reference_wav_tensor = torch.from_numpy(reference_wav).to(self.cfg.device)

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

        reference = {
            "wav": reference_wav,
            "prompt_condition": prompt_condition,
            "mel2": mel2,
            "style2": style2,
        }
        # 最终输出的是 prompt_condition ; 16k-need
        #            style2 ;  16k-need
        #            mel2 ; 22050-need
        return reference

    @torch.no_grad()
    def _custom_infer(self,
                    input_wav_res,  # 这里是16k的输入
                    block_frame_16k,
                    skip_head,
                    skip_tail,
                    return_length,
                    diffusion_steps,
                    inference_cfg_rate,
                    max_prompt_length,
                    ):
        # 获取 前global参数
        ce_dit_difference = self.cfg.ce_dit_difference  
        
        # 获取 reference 相关
        prompt_condition = self.reference["prompt_condition"]
        mel2 = self.reference["mel2"]
        style2 = self.reference["style2"]
        
        # 获取各 model
        model = self.models['dit_model']
        semantic_fn = self.models['semantic_fn']
        dit_fn = self.models['dit_fn']  
        vocoder_fn = self.models['vocoder_fn']
        campplus_model = self.models['campplus_model']
        to_mel = self.models['to_mel']
        mel_fn_args = self.models['mel_fn_args']
        
        sr = mel_fn_args["sampling_rate"]
        hop_length = mel_fn_args["hop_size"]
        

        converted_waves_16k = input_wav_res  # 这里转换成 16k 了已经？
        t0 = time.perf_counter()
        S_alt = semantic_fn(converted_waves_16k.unsqueeze(0))  # 之前一大段whisper的计算，这里成了一行，very nice
        senmantic_time = time.perf_counter() - t0
        self.senmantic_time.append(senmantic_time)

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
        
        # ------ dit model ------
        t0 = time.perf_counter()    
    
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
        
        dit_time = time.perf_counter() - t0
        self.dit_time.append(dit_time)
        # -----------------------
        
        
        # ------ vocoder ------
        t0 = time.perf_counter()
   
        vc_wave = vocoder_fn(vc_target).squeeze()
        
        vocoder_time = time.perf_counter() - t0
        self.vocoder_time.append(vocoder_time)
        # ---------------------
        
        
        output_len = return_length * sr // 50
        tail_len = skip_tail * sr // 50
        
        # -------------
        # output 增加 batch-size 的兼容
        if len(vc_wave.shape) == 2:
            output = vc_wave[0, -output_len - tail_len: -tail_len]
        else:
            output = vc_wave[-output_len - tail_len: -tail_len]  # 原版的
        # -------------
        return output

    def start_vc(self):
        """推理前的相关准备
        """
        torch.cuda.empty_cache()
            
        self.cfg.samplerate = (
            self.models["mel_fn_args"]["sampling_rate"]
        )  # gui-samplerate 赋值，22050
        self.zc = self.cfg.samplerate // 50  # 44100 // 100 = 441， 代表10ms; 
                                                    # 22050//50 = 441, 代表 20ms； 
                                                    # 是一个精度因子，20ms为一个最小精度。
        self.zc_16k = 16_000 // 50 # 320，代表20ms, 添加16k精度因子
        
        self.block_frame = (
            int(
                np.round( 
                    self.cfg.block_time
                    * self.cfg.samplerate
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
                    self.cfg.crossfade_time
                    * self.cfg.samplerate
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
                    self.cfg.extra_time
                    * self.cfg.samplerate
                    / self.zc
                )
            )
            * self.zc
        )
        self.extra_frame_16k = 320 * self.extra_frame // self.zc  # 16k对应的 extra_frame, 用在包络混合
        self.extra_frame_right = (  # 同理
                int(
                    np.round(
                        self.cfg.extra_time_right
                        * self.cfg.samplerate
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
            device=self.cfg.device,
            dtype=torch.float32,
        )  # 2 * 44100 + 0.08 * 44100 + 0.01 * 44100 + 0.25 * 44100
        self.input_wav_res: torch.Tensor = torch.zeros(
            320 * self.input_wav.shape[0] // self.zc,
            device=self.cfg.device,
            dtype=torch.float32,
        )  # input wave 44100 -> 16000   # 16k对应的 input_wav
        self.rms_buffer: np.ndarray = np.zeros(4 * self.zc_16k, dtype="float32")  # 大小换成16k对应的
        self.sola_buffer: torch.Tensor = torch.zeros(
            self.sola_buffer_frame, device=self.cfg.device, dtype=torch.float32
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
                    device=self.cfg.device,
                    dtype=torch.float32,
                )
            )
            ** 2
        ) # 一个tensor，0-1的序列(共sola_buffer_frame个元素)，经过sin再经过平方，整体就是平滑的从 0 到 1。
        self.fade_out_window: torch.Tensor = 1 - self.fade_in_window  # 反向的，这样对于前面和后面的一个 fade-out，一个 fade-in
        self.resampler = tat.Resample(
            orig_freq=self.cfg.samplerate,
            new_freq=16000,
            dtype=torch.float32,
        ).to(self.cfg.device)  # 用于从 22050 降低到 16000； 更精细点是从 gui-samplerate 到 16k
                                    # 也就是说有3个samplerate，model-sampelrate, gui-samplerate, 16k
                                    # 但是一般 model和gui的相同； 那么就是两个samplerate： 22050， 16k
        if self.models["mel_fn_args"]["sampling_rate"] != self.cfg.samplerate:  # resampler2 是从 model-samplerate => gui-samplerate
            self.resampler2 = tat.Resample(
                orig_freq=self.models["mel_fn_args"]["sampling_rate"],
                new_freq=self.cfg.samplerate,
                dtype=torch.float32,
            ).to(self.cfg.device)
        else:
            self.resampler2 = None  
        # ---------------------------------
        # 与2024-11-27一致，在这个地方加入 vad
        self.vad_cache = {}
        self.vad_chunk_size = 1000 * self.cfg.block_time
        self.vad_speech_detected = False
        self.set_speech_detected_false_at_end_flag = False
        # ---------------------------------

            
    def infer(self, input_audio_data):
        """推理完整的音频
        Args:
            input_audio_data: 输入音频数据,采样率必须为16k
        """
        self.start_vc()  # 这里是初始化的函数，主要是计算一些参数
    
        num_blocks = len(input_audio_data) // self.block_frame_16k  # 这里block-frame改成16k
        total_output = []     
        for i in range(num_blocks):
            t0 = time.perf_counter()              

            block = input_audio_data[i * self.block_frame_16k: (i + 1) * self.block_frame_16k]  # 这里也切换成16k
            
            # 传递给 callback 函数处理
            output_wave = self.chunk_vc(block).reshape(-1,)  # 这里出来的是22050的音频
            total_output.append(output_wave)  # 这里是存储的地方
            
            # 转换成有效输出
            output_wave = (output_wave * 32768.0).astype(np.int16)  # 这里和最终存储音频无关，源代码也是这样，是为了转化成mp3
            wav_buffer = io.BytesIO()  # 使用 io.BytesIO 来存储 WAV 数据
            write(wav_buffer, self.cfg.samplerate, output_wave)  # 用 scipy 的 write 函数直接写入 WAV 格式
            wav_bytes = wav_buffer.getvalue()  # 获取 WAV 数据
            
            # 最后一个chunk，保存
            if i == (num_blocks - 1):
                # 输出路径的名字
                output_path = (str(Path(self.cfg.save_dir).joinpath('.'.join(Path(self.cfg.source_path).name.split('.')[:-1]))) 
                                + f"_stream_ds{self.cfg.diffusion_steps}"
                                + f"_ref-{'.'.join(Path(self.cfg.reference_audio_path).name.split('.')[:-1])}"
                                + ".wav"
                                )
                sf.write(output_path, np.concatenate(total_output), self.cfg.samplerate)
                logger.info(f"完整音频已存储:{output_path}")
                
            chunk_time = time.perf_counter() - t0
            self.chunk_time.append(chunk_time)
            # ----------------------
            yield wav_bytes
                
    def _vad(self, indata):
        """VAD函数
        
        Args:
            indata: 输入音频数据，采样率必须为16k
        """
        
        # 与新版一致，这里加入vad模块
        # 这里把vad放到预处理的后面来，为了加入降噪模块后性能更好
        # 本身vad和预处理两个就是独立的，互不影响，谁放前面都行
        # 在加入 noise_gate 之后，vad 耗时异常增加，v100上会增加到 600，700ms，这个还有待排查，先把原始的数据交给vad吧
        # 这个放在前面就正常了，应该是zc级别的精度置0给vad造成了很大的困惑
        
        # VAD first
        t0 = time.perf_counter()
        
        res = self.vad_model.generate(input=indata, cache=self.vad_cache, is_final=False, chunk_size=self.vad_chunk_size)  # ---- 改成优化后的函数
        res_value = res[0]["value"]
        if len(res_value) % 2 == 1 and not self.vad_speech_detected:
            self.vad_speech_detected = True
        elif len(res_value) % 2 == 1 and self.vad_speech_detected:
            self.set_speech_detected_false_at_end_flag = True
            
        vad_time = time.perf_counter() - t0
        self.vad_time.append(vad_time)
    
    def _noise_gate(self, indata):
        """通过分贝阈值的方式，讲低于某个分贝的音频数据置为0
        """
        if self.vad_speech_detected:  # vad 检测出来人声才会进行 noise-gate
            t0 = time.perf_counter()
            
            indata = np.append(self.rms_buffer, indata)  # rms_buffer 仅用在这个地方
            rms = librosa.feature.rms(
                y=indata, frame_length=4 * self.zc_16k, hop_length=self.zc_16k
            )[:, 2:]  # 这里丢掉了前2个frame的数据， hop_length是1个精度，所以丢掉了前 40ms 的值
            self.rms_buffer[:] = indata[-4 * self.zc_16k :]  # 替换新的 rms_buffer
            indata = indata[2 * self.zc_16k - self.zc_16k // 2 :]  # indata 切掉了 1.5个zc，也就是30ms，所以这里做了10ms的重叠？为了让声音更平滑吗？
            db_threhold = (
                librosa.amplitude_to_db(rms, ref=1.0)[0] < self.cfg.noise_gate_threshold
            )
            for i in range(db_threhold.shape[0]):
                if db_threhold[i]:
                    indata[i * self.zc_16k : (i + 1) * self.zc_16k] = 0  # 这里是以 zc 为一个窗格的，20ms
            indata = indata[self.zc_16k // 2 :]   # 这里最终输出的indata 前面贴了 2个zc，40ms 的 rms-buffer
                                                  # 这个在后面的 input_wav_res 填入的时候给平掉了
            
            noise_gate_time = time.perf_counter() - t0
            self.noise_gate_time.append(noise_gate_time)
        else:
            self.rms_buffer[:] = 0  # vad 检测不出来的时候，缓存置0
            
        return indata
    
    def _preprocessing(self, indata):
        """预处理函数
        
        尝试使用 torch.roll() 耗时反而增加
        """
        
        # 预处理直接全改，改成16k对应的预处理
        t0 = time.perf_counter()
        
        self.input_wav_res[: -self.block_frame_16k] = self.input_wav_res[
            self.block_frame_16k :
        ].clone()  # input_res 做同样的操作; # 先做平移
        self.input_wav_res[-indata.shape[0] :] = torch.from_numpy(indata).to(
            self.cfg.device
        )  # indata 进入;  # 再填值
        
        preprocess_time = time.perf_counter() - t0
        self.preprocessing_time.append(preprocess_time)
        
    def _voice_conversion(self):
        """换声模型推理
        """

        if not self.vad_speech_detected:  # 如果没有检测到说话人，则置为0
            infer_wav = torch.zeros_like(self.input_wav[self.extra_frame :])  # 这里只是取了一个维度，与里面的值无关
            
        else:  
            t0 = time.perf_counter()
            
            infer_wav = self._custom_infer(
                self.input_wav_res,  # 整个input_res 放进去了。
                self.block_frame_16k,
                self.skip_head,
                self.skip_tail,
                self.return_length,
                int(self.cfg.diffusion_steps),
                self.cfg.inference_cfg_rate,
                self.cfg.max_prompt_length,
            )
            
            if self.resampler2 is not None:
                infer_wav = self.resampler2(infer_wav)
                
            voice_conversion_time = time.perf_counter() - t0
            self.vc_time.append(voice_conversion_time)
            
        return infer_wav 
    
    def _sola(self, infer_wav):
        """SOLA算法
        """
        t0 = time.perf_counter()
        
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
                torch.ones(1, 1, self.sola_buffer_frame, device=self.cfg.device),
            )
            + 1e-8
        )   # 这里是求分母，input**2 是能量，在 sola_buffer上卷积，最终也得到 sola_search_frame + 1 的长度
        sola_offset = torch.argmax(cor_nom[0, 0] / cor_den[0, 0])  # 这里就是相似度了，找到最相似的 arg

        infer_wav = infer_wav[sola_offset:]  # 这里从最相似的部分索引出来
        infer_wav[: self.sola_buffer_frame] *= self.fade_in_window  # sola_buffer 的长度进行 fade_in
        infer_wav[: self.sola_buffer_frame] += (
            self.sola_buffer * self.fade_out_window
        )  # 之前的 sola_buffer 进行 fade_out
        self.sola_buffer[:] = infer_wav[
            self.block_frame : self.block_frame + self.sola_buffer_frame
        ]  # 这里再得到新的 sola_buffer, 从 block_frame 开始 增加 buffer_frame；相当于前一个音频片段推理输出
            # 由于下面输出的是最前面 block_frame的音频，这里就取后续的这部分留下来做 sola 和 fade
            
        sola_time = time.perf_counter() - t0
        self.sola_time.append(sola_time)
        return infer_wav
    
    def _compute_rms(self, waveform:torch.tensor, 
                     frame_length=2048, hop_length=512, center:bool=True):
        """实现libroasa.feature.rms的torch.tensor版本
        
        仅实现了 幅值到 rms 的部分，频谱到 rms 的部分没有实现
        """
        assert waveform.ndim == 1, "waveform must be 1D tensor"
        
        if center:
            # 针对 torch.nn.functional.pad 
            # 它的 pad 形式是一个 list, 从最低维度开始，每两位，代表该纬度的前后 padding 个数
            # 相对比 np.pad, np 是一个 list，里面每个维度对应一个小list，行如（before，after），而且是从最高的维度开始，也就是第一个维度
            padding = [int(frame_length // 2), int(frame_length // 2)]
            waveform = F.pad(waveform, padding, mode="constant", value=0)
            
        # 分帧
        frames = torch.nn.functional.unfold(
            waveform.reshape(1, -1, 1),
            kernel_size=(frame_length, 1),
            stride=(hop_length, 1),
        )
        
        # 计算每帧的均方根
        rms = torch.sqrt(torch.mean(frames**2, dim=-2, keepdim=True))
        return rms  # 这里输出的shape == (1,30)
        
    def _rms_mixing(self, infer_wav):
        """依据输入音频与输出音频的短时rms值进行音频融合
        
        为了进行性能加速，改为GPU上计算，而非转换到cpu上计算
        
        Args:
            infer_wav: 换声模型推理结果
        """
        
        if self.vad_speech_detected:  # 检测到人声才会进行vc，才会需要rms-mix
            t0 = time.perf_counter()
            
            input_wav = self.input_wav_res[self.extra_frame_16k :]  # rvc 和 seed-vc input_wav 组成式一样的
                                                                        # 由于输入已经改成了16k采样率，这里也要调整一下
                                                                        # 由于 seed-vc 里面增加了 extra-right 20ms
                                                                        # 所以这里 input_wav_res 相比 infer_wav 多了 20ms
                                                                        # input_wav_res 是 500ms
                                                                        # infer_wav 是 560ms
                                                                        # 不过影响很小，后面 rms 都会插值成 560ms * 22050 的长度
            # 计算 输入音频 rms
            rms_input = self._compute_rms(
                waveform = input_wav,  # 这里先不取 infer-wav.shape 了， 后面再插值
                frame_length = 4 * self.zc_16k,  # frame_length 对应 80ms
                hop_length = self.zc_16k,  # 对应 320 帧， 20ms
            )
            rms_input = F.interpolate(  # 插值函数
                rms_input.unsqueeze(0),  # 这里把 shape 转换成 (1, 1, 30)，
                size = infer_wav.shape[0] + 1,  
                mode = "linear", 
                align_corners = True,
            )[0, 0, :-1]  # 这里转换成1维
            
            # 计算 换声音频 rms
            rms_infer = self._compute_rms(
                waveform =infer_wav[:],
                frame_length=4 * self.zc,  
                hop_length=self.zc,
            )
            rms_infer = F.interpolate(
                rms_infer.unsqueeze(0),
                size=infer_wav.shape[0] + 1,
                mode="linear",
                align_corners=True,
            )[0, 0, :-1]
            rms_infer = torch.max(rms_infer, torch.zeros_like(rms_infer) + 1e-3)
            
            infer_wav *= torch.pow(
                rms_input / rms_infer, torch.tensor(1 - self.cfg.rms_mix_rate)
            )
            
            rms_mix_time = time.perf_counter() - t0
            self.rms_mix_time.append(rms_mix_time)
        else:
            rms_mix_time = None
            
        return infer_wav

    def chunk_vc(self, indata: np.ndarray):
        """chunk推理函数
        Args:
            indata: 16k 采样率的chunk 音频数据
        """
        indata = librosa.to_mono(indata.T)  # 转换完之后的indata shape: (11025,), max=1.0116995573043823, min=-1.0213052034378052
        
        # 1. vad
        self._vad(indata) 
        
        # 2. noise_gate
        if self.cfg.noise_gate and (self.cfg.noise_gate_threshold > -60):
            indata = self._noise_gate(indata)
        
        # 3. 预处理
        self._preprocessing(indata)  
        
        # 4. 换声
        vc_wav = self._voice_conversion() 
        
        # 5. rms—mix 
        if self.cfg.rms_mix_rate < 1:  
            vc_wav = self._rms_mixing(vc_wav)
        
        # 6. sola
        vc_wav = self._sola(vc_wav) 
        
        # 7. 输出 
        outdata = (
            vc_wav[: self.block_frame]  # 每次输出一个 bloack_frame
            .t()
            .cpu()
            .numpy()
        )  # outdata.shape => (11025,) 

        
        # vad 标记位
        if self.set_speech_detected_false_at_end_flag:
            self.vad_speech_detected = False
            self.set_speech_detected_false_at_end_flag = False
        
        # tracking
        self.tracking_counter += 1  # 每chunk +1 
        if self.tracking_counter >= self.cfg.max_tracking_counter:
            self._performance_report()
            self.tracking_counter = 0

        return outdata


if __name__ == "__main__":
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
        
        parser.add_argument('--crossfade_time', type=float, 
                            default=0.04, 
                            help="交叉渐变长度，单位秒，默认值为 0.04 秒")
        
        parser.add_argument('--diffusion_steps', type=int, 
                            default=10, 
                            help="扩散步骤，默认值为 3")
        
        parser.add_argument('--max_prompt_length', type=float, 
                            default=3, 
                            help="参考截断长度，单位秒，默认值为 3 秒")
        return parser.parse_args()

    args = parse_args()
    reference_audio_path = args.reference_audio_path
    file_list = args.file_list.split() if args.file_list else None
    save_dir = args.save_dir 
    block_time = args.block_time
    crossfade_time = args.crossfade_time
    diffusion_steps = args.diffusion_steps
    max_prompt_length = args.max_prompt_length
    
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
    print(f"crossfade_time: {crossfade_time}")
    print(f"diffusion_steps: {diffusion_steps}")
    print(f"max_prompt_length: {max_prompt_length}")
    print('-'*42)
    # --------------------------
    
    # 2. 对应参数赋值给cfg
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    cfg = RealtimeVoiceConversionConfig(block_time=block_time,
                              crossfade_time=crossfade_time,
                              diffusion_steps=diffusion_steps, 
                              reference_audio_path=reference_audio_path, 
                              save_dir=save_dir,
                              max_prompt_length=max_prompt_length,
                              arbitrary_types_allowed=True,  # 这里允许任意类型
                              )
    print(cfg)
    
    # 获取推理实例
    realtime_vc = RealtimeVoiceConversion(cfg=cfg)
    
    # 3. 开始VC
    print('-' * 42)
    print("准备工作完毕，开始文件夹批量换声, 请按回车继续...")
    try:
        input()
    except EOFError:
        pass  # 忽略 EOFError，直接继续
    
    for file in file_list:
            wav, _ = librosa.load(file, sr=16000, mono=True)  # source 输入统一为16k
            realtime_vc.cfg.source_path = str(file)
            for o in realtime_vc.infer(wav):
                nonsense = 42
                
    realtime_vc._performance_report()

