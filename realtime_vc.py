from dotenv import load_dotenv
load_dotenv()

import librosa
import time
import torch
import torch.nn.functional as F
import torchaudio
import torchaudio.transforms as tat
import numpy as np
from pathlib import Path
import json
from pydantic import BaseModel
from collections import deque
from loguru import logger
from pathlib import Path

from models import models
from session import Session


class RealtimeVoiceConversionConfig(BaseModel):
    """换声服务配置类"""
    
    # 设备
    device: str = str(torch.device("cuda" if torch.cuda.is_available() else "cpu"))
    
    # wav 相关
    reference_audio_path: str = "testsets/000042.wav"
    save_dir: str = "wavs/output/"  # 存储
    save_input: bool = True  # is to save input wav
    save_output: bool = True  # is to save output wav
    
    # realtime 
    SAMPLERATE: float = 16_000  # also called common_sr
                                # 音频流在vc过程中基础采样率
                                # 不可修改，需要保证为 16k，vad，senmantic 都是 16k 模型
                                # 某些环节采样率会改变，比如dit model会更改为22050，需要再次转换回来
    
    zc_framerate: int = 50  # zc = samplerate // zc_framerate, rvc:100, seed-vc: 50
    block_time: float = 0.5  # 0.5 ；这里的 block time 是 0.5s                    
    crossfade_time: float = 0.04  # 0.04 ；用于平滑过渡的交叉渐变长度，这里设定为 0.04 秒。交叉渐变通常用于避免声音中断或“断层”现象。
    extra_time: float = 2.5  # 2.5；  附加时间，设置为 0.5秒。可能用于在处理音频时延长或平滑过渡的时间。
                             # 原本默认0.5，后面更新成2.5了，放在音频的前面
    extra_time_right: float = 0.02  # 0.02；

    # noise_gata
    noise_gate: bool = True  # 是否使用噪声门
    noise_gate_threshold: float = -60  # 噪声门的阈值，单位是分贝，-60dB
    
    # vc models
    diffusion_steps: int = 10  # 10；                    
    inference_cfg_rate: float = 0.7  # 0.7
    max_prompt_length: float = 3.0 # 3； 
    ce_dit_difference: float = 2  # 2 seconds， content encoder ?
    
    # rms_mix
    rms_mix_rate: float = 0    # 0.25； 这个参数是用来控制 RMS 混合的比例，
                               # 范围是 0 到 1。
                               # 0 表示完全使用 Input 的包络，1 表示完全使用 Infer 包络。
                               
    # 辅助参数
    max_tracking_counter: int = 10_000  # 用于记录单chunk推理时间损耗的最大记录数量


class RealtimeVoiceConversion:
    """流式换声服务核心类"""

    def __init__(self, cfg:RealtimeVoiceConversionConfig) -> None:
        self.cfg = cfg
        self.models = models
        self._init_performance_tracking()  # 初始化耗时记录
        self._init_realtime_parameters()  # 初始化实时推理相关参数
        self.reference = self._update_reference()
    
    def _init_performance_tracking(self):
        """init performance tracking
        
        1. time cost in every module        
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
            "VC Models Overall": self.vc_time,
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
    
    def _init_realtime_parameters(self):
        """初始化实时推理服务相关参数"""
        
        self.zc = self.cfg.SAMPLERATE // self.cfg.zc_framerate  # precision factor
                                                                # seed-vc is // 50
                                                                # rvc is // 100
        # wav 相关
        self.block_frame = self.cfg.block_time * self.cfg.SAMPLERATE  # block_frame 代表的是 0.5s 的音频片段，单位是帧数
        self.block_frame = int( np.round( self.block_frame / self.zc) ) * self.zc  # 规范化, n倍zc
        
        self.crossfade_frame = self.cfg.crossfade_time * self.cfg.SAMPLERATE 
        self.crossfade_frame = int( np.round( self.crossfade_frame / self.zc ) ) * self.zc 
    
        self.extra_frame = self.cfg.extra_time * self.cfg.SAMPLERATE 
        self.extra_frame = int( np.round( self.extra_frame / self.zc ) ) * self.zc 
        
        self.extra_frame_right = self.cfg.extra_time_right * self.cfg.SAMPLERATE
        self.extra_frame_right = int( np.round( self.extra_frame_right / self.zc ) ) * self.zc
        
        # vad
        self.vad_chunk_size = 1000 * self.cfg.block_time
        
        # sola
        self.sola_buffer_frame = min( self.crossfade_frame, 4 * self.zc ) # 80ms帧 和 crossfade帧(默认40ms)中的小数
        self.sola_search_frame = self.zc  # sola_search 
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
        
        
        # vc models
        self.skip_head = self.extra_frame // self.zc  # after // zc , it independent of sr, n zcs.
        self.skip_tail = self.extra_frame_right // self.zc  
        self.return_length = (
            self.block_frame + self.sola_buffer_frame + self.sola_search_frame
        ) // self.zc
        
        model_samplerate = self.models["mel_fn_args"]["sampling_rate"]
        if model_samplerate != self.cfg.SAMPLERATE:  
            self.resampler_model_to_common = tat.Resample(
                orig_freq=model_samplerate,
                new_freq=self.cfg.SAMPLERATE,
                dtype=torch.float32,
            ).to(self.cfg.device)  # 模型的采样率 到 通用采样率
        else:
            self.resampler_model_to_common = None 
            
        # rms-mixing
        
        # original code in rvc is: [self.extra_frame: ]
        # their has changed in seed-vc, using the same region of vc model final output 
        self.region_start = - ( self.return_length * self.zc ) - ( self.skip_tail * self.zc )
        self.region_end = - ( self.skip_tail * self.zc )
        
        
    def create_session(self, unique_id):
        """创建一个新的会话"""
        return Session(unique_id=unique_id,
                       extra_frame=self.extra_frame, 
                       crossfade_frame=self.crossfade_frame, 
                       sola_search_frame=self.sola_search_frame, 
                       block_frame=self.block_frame, 
                       extra_frame_right=self.extra_frame_right, 
                       zc=self.zc, 
                       sola_buffer_frame=self.sola_buffer_frame,
                       samplerate=self.cfg.SAMPLERATE,
                       device=self.cfg.device)
    
    def _update_reference(self):
        """读取reference音频，并计算相关的模型输入
        """
        reference_wav = self._load_reference_wav()
        reference = self._cal_reference(reference_wav=reference_wav)
        return reference
        
    def _load_reference_wav(self):
        """load reference wav
        
        sample rate of reference wav should be 22050, to cal prompt_mel
        """
        reference_wav, _ = librosa.load(
                self.cfg.reference_audio_path, sr=self.models["mel_fn_args"]["sampling_rate"]  # 22050
        )
        return reference_wav
    
    @torch.no_grad()
    def _cal_reference(self, reference_wav):
        """calculate model inputs which are related to reference wav
        
        # pipleline:
            rf_wav_16k -> [ fbank, cam++ -> prompt_style
            rf_wav_22050 -> [ to_mel ] -> prompt_mel
            rf_wav_16k -> [ semantic_fn, length_regulator, mel_size ] -> prompt_condition
        """
        
        # acquire models
        model = self.models['dit_model']
        semantic_fn = self.models['semantic_fn']
        campplus_model = self.models['campplus_model']
        to_mel = self.models['to_mel']
        mel_fn_args = self.models['mel_fn_args']
        
        # calculate
        sr = mel_fn_args["sampling_rate"]  # sr of reference_wav is determined by mel_fn_args
        reference_wav = reference_wav[:int(sr * self.cfg.max_prompt_length)]  # Truncate reference_wav if it exceeds max_prompt_length
        reference_wav_tensor = torch.from_numpy(reference_wav).to(self.cfg.device)

        ori_waves_16k = torchaudio.functional.resample(reference_wav_tensor, sr, 16000)  
        S_ori = semantic_fn(ori_waves_16k.unsqueeze(0))  # Whisper, Wav2Vec, and HuBERT all have a downsampling factor of 320x
                                                         # equivalent to 50 frames per second
        feat2 = torchaudio.compliance.kaldi.fbank(
            ori_waves_16k.unsqueeze(0), num_mel_bins=80, dither=0, sample_frequency=16000
        )  # 16k mel
        feat2 = feat2 - feat2.mean(dim=0, keepdim=True)  # mean normalization
        prompt_style = campplus_model(feat2.unsqueeze(0))  # cam++ using fbank feature

        prompt_mel = to_mel(reference_wav_tensor.unsqueeze(0))  # using 22.05k sr, hop_length=256, means 256x downsampling
                                                          # equivalent to 86 frames per second
        target2_lengths = torch.LongTensor([prompt_mel.size(2)]).to(prompt_mel.device)
        prompt_condition = model.length_regulator(
            S_ori, ylens=target2_lengths, n_quantizers=3, f0=None
        )[0]  # samplerate aligned to mel

        reference = {
            "wav": reference_wav,  # not using
            "prompt_condition": prompt_condition, 
            "prompt_mel": prompt_mel,  # need 22.05k sr, related to hop_length, win_length
                           # parameter of it is complicated, let it be for now  
            "prompt_style": prompt_style, 
        }
        return reference

    @torch.no_grad()
    def _vc_infer(self,
                  input_wav,  # 16k sr
                  skip_head,
                  skip_tail,
                  return_length,
                  diffusion_steps,
                  inference_cfg_rate,
                ):
        """vc inference
        
        input_wav -> [ semantic_fn, length_regulator ] -> cond
        prompt_condition + cond -> cat_condition
        
        cat_condition + prompt_mel + prompt_style -> vc_target
        """        

        # 获取 前global参数
        ce_dit_difference = self.cfg.ce_dit_difference  
        
        # 获取 reference 相关
        prompt_condition = self.reference["prompt_condition"]
        prompt_mel = self.reference["prompt_mel"]
        prompt_style = self.reference["prompt_style"]
        
        # 获取各 model
        model = self.models['dit_model']
        semantic_fn = self.models['semantic_fn']
        dit_fn = self.models['dit_fn']  
        vocoder_fn = self.models['vocoder_fn']
        mel_fn_args = self.models['mel_fn_args']
        
        sr = mel_fn_args["sampling_rate"]
        hop_length = mel_fn_args["hop_size"]
        
        
        # get cat_condition
        t0 = time.perf_counter()
        S_alt = semantic_fn(input_wav.unsqueeze(0))
        S_alt = S_alt[:, ce_dit_difference * 50:]  # 16k sr with 320x downsampling of senmantic(whisper, wav2vec, hubert)
                                                   # 50 frames per second
                                                   
                                                   # The first portion of its output 
                                                   # can contain initialization artifacts 
                                                   # or less reliable features.
        
        # skip_head, return_length and skip_tail are unrelated to common_sr
        # using mel's sr and hop_length to make target_length consistent with the reference part
        target_lengths = torch.LongTensor([(skip_head + return_length + skip_tail - ce_dit_difference * 50) / 50 * sr // hop_length]).to(S_alt.device)
        cond = model.length_regulator(
            S_alt, ylens=target_lengths , n_quantizers=3, f0=None
        )[0]
        cat_condition = torch.cat([prompt_condition, cond], dim=1)
        
        senmantic_time = time.perf_counter() - t0  # which includes semantic and length_regulator
        self.senmantic_time.append(senmantic_time) 
        
        
        # dit model
        t0 = time.perf_counter()
        
        vc_target = dit_fn(
            cat_condition,
            torch.LongTensor([cat_condition.size(1)]).to(prompt_mel.device),
            prompt_mel,
            prompt_style,
            None,
            n_timesteps=diffusion_steps,
            inference_cfg_rate=inference_cfg_rate,
        )
        vc_target = vc_target[:, :, prompt_mel.size(-1) :]
        
        dit_time = time.perf_counter() - t0
        self.dit_time.append(dit_time)
        
        # vocoder model
        t0 = time.perf_counter()
   
        vc_wave = vocoder_fn(vc_target).squeeze()  # vc_wave sr = 22050?
        
        vocoder_time = time.perf_counter() - t0
        self.vocoder_time.append(vocoder_time)
        
        # final output
        output_len = return_length * ( sr // self.cfg.zc_framerate )  # sola_buffer + sola_search + block
        tail_len = skip_tail * ( sr // self.cfg.zc_framerate )  # extra_right
        
        # input_wav = extra + crossfade + sola_search + block + extra_right
        # -> x = input_wav[ ce_dit_difference: ]
        # -> x = x[ ( -sola_buffer - sola_search - block ) - extra_right: -extra_right ]
        # -> output = sola_buffer + sola_search + block
        output = vc_wave[-output_len - tail_len: -tail_len]  
        return output
    
    def file_vc(self, wav_path:str):
        """读取wav文件并进行流式推理，用于批量测试效果
        
        Args:
            wav_path: 输入音频文件路径
        """
        wav_data, _ = librosa.load(wav_path, sr=self.cfg.SAMPLERATE, mono=True) 
        unique_id = Path(wav_path).name  # 针对文件使用文件名作为 unique_id 
        session = self.create_session(unique_id=unique_id) 
        
        num_blocks = len(wav_data) // self.block_frame  # TODO 后续把结尾的block补上，padding 防止丢失
        for i in range(num_blocks):           
            block_data = wav_data[i * self.block_frame: (i + 1) * self.block_frame]
            self.chunk_vc(block_data, session)

        session.save(self.cfg.save_dir)  # save wav
        session.cleanup()  # clear session data
                
    def _vad(self, indata, session):
        """VAD函数
        
        Args:
            indata: 输入音频数据，采样率必须为16k
            session: 会话对象
        """
        
        # vad 放在 noise_gate 之后的话，vad 耗时异常增加，v100上会增加到 600，700ms
        # vad 放在前面就正常了，应该是zc级别的精度置0给vad造成了很大的困惑
        
        t0 = time.perf_counter()
        
        vad_model = self.models["vad_model"]
        res = vad_model.generate(input=indata, cache=session.vad_cache, is_final=False, chunk_size=self.vad_chunk_size)  # ---- 改成优化后的函数
        res_value = res[0]["value"]
        if len(res_value) % 2 == 1 and not session.vad_speech_detected:
            session.vad_speech_detected = True
        elif len(res_value) % 2 == 1 and session.vad_speech_detected:
            session.set_speech_detected_false_at_end_flag = True
            
        vad_time = time.perf_counter() - t0
        self.vad_time.append(vad_time)
    
    def _noise_gate(self, indata, session):
        """通过分贝阈值的方式，讲低于某个分贝的音频数据置为0
        """
        if session.vad_speech_detected:  # vad 检测出来人声才会进行 noise-gate
            t0 = time.perf_counter()
            
            indata = np.append(session.rms_buffer, indata)  # rms_buffer 仅用在这个地方
            rms = librosa.feature.rms(
                y=indata, frame_length=4 * self.zc, hop_length=self.zc
            )[:, 2:]  # 这里丢掉了前2个frame的数据， hop_length是1个精度，所以丢掉了前 40ms 的值
            session.rms_buffer[:] = indata[-4 * self.zc :]  # 替换新的 rms_buffer
            indata = indata[2 * self.zc - self.zc // 2 :]  # indata 切掉了 1.5个zc，也就是30ms，所以这里做了10ms的重叠？为了让声音更平滑吗？
            db_threhold = (
                librosa.amplitude_to_db(rms, ref=1.0)[0] < self.cfg.noise_gate_threshold
            )
            for i in range(db_threhold.shape[0]):
                if db_threhold[i]:
                    indata[i * self.zc : (i + 1) * self.zc] = 0  # 这里是以 zc 为一个窗格的，20ms
            indata = indata[self.zc // 2 :]   # 这里最终输出的indata 前面贴了 2个zc，40ms 的 rms-buffer
                                                  # 这个在后面的 input_wav_res 填入的时候给平掉了
            
            noise_gate_time = time.perf_counter() - t0
            self.noise_gate_time.append(noise_gate_time)
        else:
            session.rms_buffer[:] = 0  # vad 检测不出来的时候，缓存置0
            
        return indata
    
    def _preprocessing(self, indata, session):
        """预处理函数
        
        平移input_wav，填入新chunk
        """
        t0 = time.perf_counter()
        
        # 平移一个block_frame
        # 尝试使用 torch.roll() 耗时反而增加
        session.input_wav[: -self.block_frame] = session.input_wav[self.block_frame :].clone()  
        
        # 整体填入 indata (可能大于block_frame)，但是核心内容是 block_frame大小
        # new block will be put at the end of input_wav
        session.input_wav[-indata.shape[0] :] = torch.from_numpy(indata).to(
            self.cfg.device
        )
        
        preprocess_time = time.perf_counter() - t0
        self.preprocessing_time.append(preprocess_time)
        
    def _voice_conversion(self, session) -> torch.Tensor:
        """vc inference 
        
        Returns:
            infer_wav: 推理后的音频数据, torch.tensor, device=self.cfg.device
        """
        if not session.vad_speech_detected:  # if don't detect speech, set to zero
            infer_wav = session.infer_wav_zero 
        else:  
            t0 = time.perf_counter()
            
            infer_wav = self._vc_infer(
                session.input_wav,
                self.skip_head,
                self.skip_tail,
                self.return_length,
                int(self.cfg.diffusion_steps),
                self.cfg.inference_cfg_rate,
            )
            
            # model sr != common sr 的话，会 resample 到 common sr
            if self.resampler_model_to_common is not None:  
                logger.debug(f"before resample: {infer_wav.shape}")
                infer_wav = self.resampler_model_to_common(infer_wav)
                logger.debug(f"after resample: {infer_wav.shape}, theroy_length: 8800")
                
            voice_conversion_time = time.perf_counter() - t0
            self.vc_time.append(voice_conversion_time)
            
        return infer_wav 
    
    def _sola(self, infer_wav, session:Session):
        """algorithm for time-domain pitch-synchronous overlap-add
        
        infer_wav: [sola_buffer + sola_search + block]
        """
        t0 = time.perf_counter()
        
        # SOLA algorithm from https://github.com/yxlllc/DDSP-SVC
        conv_input = infer_wav[
            None, None, : self.sola_buffer_frame + self.sola_search_frame 
        ]  # sola_buffer + sola_search
           # None， None is to expand the dimension of the tensor
        cor_nom = F.conv1d(conv_input, session.sola_buffer[None, None, :])  # sola-buffer initialized with zeros
                                                                            # dot product between the input and the buffer
                                                                            # 这里是滑动窗口 点积，每个buffer-frame的长度跟buffer点积
                                                                            # 结果是的到长度为 sola_search_frame + 1 的值
        cor_den = torch.sqrt(
            F.conv1d(
                conv_input**2,
                torch.ones(1, 1, self.sola_buffer_frame, device=self.cfg.device),
            )
            + 1e-8
        )   # 这里是求分母，input**2 是能量，在 sola_buffer上卷积，最终也得到 sola_search_frame + 1 的长度
        sola_offset = torch.argmax(cor_nom[0, 0] / cor_den[0, 0])  # 这里就是相似度了，找到最相似的 arg
        logger.debug(f"sola_offset: {sola_offset}, infer_wav.shape: {infer_wav.shape[0]}")

        infer_wav = infer_wav[sola_offset:]  # 这里从最相似的部分索引出来
        infer_wav[: self.sola_buffer_frame] *= self.fade_in_window  # sola_buffer 的长度进行 fade_in
        infer_wav[: self.sola_buffer_frame] += (
            session.sola_buffer * self.fade_out_window
        )  # 之前的 sola_buffer 进行 fade_out
        
        # set new sola_buffer
        session.sola_buffer[:] = infer_wav[
            self.block_frame : self.block_frame + self.sola_buffer_frame
        ]
        # Index(block_frame + sola_buffer_frame) = Index(- sola_search)
        # this chunk: new_sola_buffer + sola_search + extra_right
        # add new chunk: new_sola_buffer + sola_search + extra_right + block
        # new infer wav: new_sola_buffer + sola_search + block
        # the new sola_buffer is the same wav_area as the next infer_wav[：sola_buffer_frame]
        # it means that sola_buffer is the area to smoothing between two chunks
    
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
        
    def _rms_mixing(self, infer_wav, session:Session):
        """Audio fusion based on short-time RMS values 
           of input and output audio
        
        - For performance acceleration, 
          calculations that were originally performed on CPU 
          have been moved to GPU.
        
        Args:
            infer_wav: output of vc model, sr = common_sr
            session: context of the current session
        """
        
        if session.vad_speech_detected:  # only do rms-mixing when vad detected
            t0 = time.perf_counter()
            
            # original code in rvc is: [self.extra_frame: ]
            # their has changed in seed-vc, using the same region of vc model final output 
            input_wav = session.input_wav[ self.region_start : self.region_end] 
            
            # rms of input_wav
            rms_input = self._compute_rms(
                waveform = input_wav,  
                frame_length = 4 * self.zc,  
                hop_length = self.zc,
            )
            rms_input = F.interpolate(  # interpolation function
                rms_input.unsqueeze(0),  # reshape to  (1, 1, 30)，
                size = infer_wav.shape[0] + 1,  
                mode = "linear", 
                align_corners = True,
            )[0, 0, :-1]  # turn to 1 dimension
            
            # rms of infer_wav
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

    def chunk_vc(self, in_data: np.ndarray, session: Session) -> None:
        """chunk推理函数
        
        Args:
            indata: self.cfg.samplerate 采样率的音频数据, pcm格式, channel=1
        """
        t0 = time.perf_counter()
        
        logger.debug(f"in_data.max: {in_data.max()}, in_data.min: {in_data.min()}")
        if self.cfg.save_input:  # save input chunk
            session.add_chunk_input(in_data)
        
        in_data = librosa.to_mono(in_data.T)  # 转换完之后的indata shape: (11025,), max=1.0116995573043823, min=-1.0213052034378052
        
        # 1. vad
        self._vad(in_data, session) 
        
        # 2. noise_gate
        if self.cfg.noise_gate and (self.cfg.noise_gate_threshold > -60):
            in_data = self._noise_gate(in_data)
        
        # 3. preprocessing
        self._preprocessing(in_data, session)  
        
        # 4. voice conversion
        infer_wav = self._voice_conversion(session) 
        
        # 5. rms—mix
        if self.cfg.rms_mix_rate < 1:  
            infer_wav = self._rms_mixing(infer_wav, session)
        
        # 6. sola
        infer_wav = self._sola(infer_wav, session) 
        
        # 7. output
        session.out_data[:] = (
            infer_wav[: self.block_frame]  
            .t()
            .cpu()
            .numpy()
        )  # return the beginning of the output
           # add more latency include [sola_buffer + sola_search]
        logger.debug(f"session.out_data.max: {session.out_data.max()}, session.out_data.min: {session.out_data.min()}")
        
        # system latency:
        # new chunk append to the end of input_wav
        # but return [-block - latency : -latency]
        # where latency = sola_buffer + sola_search + extra_right
        # 40ms + 10ms + 20ms = 70ms  if zc_duration = 10ms
        # 80ms + 20ms + 20ms = 120ms if zc_duration = 20ms
        
        # vad flag
        if session.set_speech_detected_false_at_end_flag:
            session.vad_speech_detected = False
            session.set_speech_detected_false_at_end_flag = False
        
        if self.cfg.save_output:  # save output chunk
            session.add_chunk_output(session.out_data)
        
        # tracking
        chunk_time = time.perf_counter() - t0
        self.chunk_time.append(chunk_time)
        
        self.tracking_counter += 1  # 每chunk +1 
        if self.tracking_counter >= self.cfg.max_tracking_counter:
            self._performance_report()
            self.tracking_counter = 0

