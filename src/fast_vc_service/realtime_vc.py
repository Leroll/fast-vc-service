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
import uuid

from fast_vc_service.models import ModelFactory
from fast_vc_service.session import Session
from fast_vc_service.utils import Singleton
from fast_vc_service.config import RealtimeVoiceConversionConfig, ModelConfig


@Singleton
class RealtimeVoiceConversion:
    """流式语音转换服务核心类"""

    def __init__(self, cfg:RealtimeVoiceConversionConfig, model_cfg: ModelConfig) -> None:
        self.cfg = cfg 
        self.models = ModelFactory(model_config=model_cfg, 
                                   is_f0=self.cfg.is_f0, 
                                   device=self.cfg.device).get_models()  # initialize models
        self._init_realtime_parameters()  # init realtime parameters
        self.reference = self._update_reference()
        self.instance_id = uuid.uuid4().hex
        logger.info(f"RealtimeVoiceConversion instance created with ID: {self.instance_id}, device: {self.cfg.device}")
    
    def _init_realtime_parameters(self):
        """Initialize parameters related to real-time processing"""
        
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
        self.vad_chunk_size = 1000 * self.cfg.block_time  # 转换成ms
        
        # f0_extractor
        rmvpe_hop_length = 160  # 这个在RMVPE模型设置里面，hop_length设置的160，没有取，而是写死了。
        self.f0_chunk_size = self.block_frame // rmvpe_hop_length + 1
        
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
        
        
    def create_session(self, session_id):
        """创建一个新的会话"""
        return Session(session_id=session_id,
                       extra_frame=self.extra_frame, 
                       crossfade_frame=self.crossfade_frame, 
                       sola_search_frame=self.sola_search_frame, 
                       block_frame=self.block_frame, 
                       extra_frame_right=self.extra_frame_right, 
                       zc=self.zc, 
                       sola_buffer_frame=self.sola_buffer_frame,
                       samplerate=self.cfg.SAMPLERATE,
                       save_dir=self.cfg.save_dir,
                       device=self.cfg.device,
                       send_slow_threshold=self.cfg.send_slow_threshold,
                       recv_slow_threshold=self.cfg.recv_slow_threshold)
    
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
                self.cfg.reference_wav_path, sr=self.models["mel_fn_args"]["sampling_rate"]  # 22050
        )
        return reference_wav
    
    @torch.no_grad()
    def _cal_reference(self, reference_wav):
        """calculate model inputs which are related to reference wav
        
        # pipleline:
            rf_wav_16k -> [ fbank, cam++ ] -> prompt_style
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
        
        # f0 extraction
        if self.cfg.is_f0:
            f0_ori = self.models['f0_fn'](ori_waves_16k, thred=0.03)
            f0_ori = torch.from_numpy(f0_ori).to(self.cfg.device)[None]
            
            voiced_f0_ori = f0_ori[f0_ori > 1]
            voiced_log_f0_ori = torch.log(voiced_f0_ori + 1e-5)
            median_log_f0_ori = torch.median(voiced_log_f0_ori)
        else:
            f0_ori = None  # 获取 prompt_condition 时需要
            median_log_f0_ori = None  # 后续实时过程中chunk数据需要用
        
        # semantic
        S_ori = semantic_fn(ori_waves_16k.unsqueeze(0))  # Whisper, Wav2Vec, and HuBERT all have a downsampling factor of 320x
                                                         # equivalent to 50 frames per second
        # timbre 
        feat2 = torchaudio.compliance.kaldi.fbank(
            ori_waves_16k.unsqueeze(0), num_mel_bins=80, dither=0, sample_frequency=16000
        )  # 16k mel
        feat2 = feat2 - feat2.mean(dim=0, keepdim=True)  # mean normalization
        prompt_style = campplus_model(feat2.unsqueeze(0))  # cam++ using fbank feature

        # mel & prompt_condition
        prompt_mel = to_mel(reference_wav_tensor.unsqueeze(0))  # using 22.05k sr, hop_length=256, means 256x downsampling
                                                          # equivalent to 86 frames per second
        target2_lengths = torch.LongTensor([prompt_mel.size(2)]).to(prompt_mel.device)
        prompt_condition = model.length_regulator(
            S_ori, ylens=target2_lengths, n_quantizers=3, f0=f0_ori
        )[0]  # samplerate aligned to mel

        reference = {
            "wav": reference_wav,  # not using
            "prompt_condition": prompt_condition,  # semantic_feat with length aligned to mel
            "prompt_mel": prompt_mel,  # need 22.05k sr, related to hop_length, win_length
                           # parameter of it is complicated, let it be for now  
            "prompt_style": prompt_style, 
            "median_log_f0_ori": median_log_f0_ori,  # median log f0 of reference wav
                                                     # has value only when is_f0 is True
        }
        return reference
    
    def _retrieval(self, S_alt):
        if self.models['retrieval_fn'] is None:
            return S_alt
        
        index = self.models['retrieval_fn']['index']
        big_npy = self.models['retrieval_fn']['big_npy']
        index_rate = self.models['retrieval_fn']['index_rate']
        
        npy = S_alt.squeeze(0).cpu().numpy().astype("float32")
        score, ix = index.search(npy, k=8)
        weight = np.square(1 / score)
        weight /= weight.sum(axis=1, keepdims=True)
        npy = np.sum(big_npy[ix] * np.expand_dims(weight, axis=2), axis=1)

        searched_feat = torch.from_numpy(npy).unsqueeze(0).to(S_alt.device)
        searched_feat = searched_feat * index_rate + S_alt * (1 - index_rate)
    
        return searched_feat

    @torch.no_grad()
    def _vc_infer(self,
                  input_wav,  # 16k sr
                  skip_head,
                  skip_tail,
                  return_length,
                  diffusion_steps,
                  inference_cfg_rate,
                  shifted_f0_alt=None,
                  chunk_time_records={}
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
        S_alt = self._retrieval(S_alt)  # apply retrieval if enabled
        S_alt = S_alt[:, int(ce_dit_difference * 50):]  # 16k sr with 320x downsampling of senmantic(whisper, wav2vec, hubert)
                                                   # 50 frames per second
                                                   
                                                   # The first portion of its output 
                                                   # can contain initialization artifacts 
                                                   # or less reliable features.
        
        # skip_head, return_length and skip_tail are unrelated to common_sr
        # using mel's sr and hop_length to make target_length consistent with the reference part
        # the second  50 = 16000 / self.zc = 16000 / 320
        # skip_head 这些是 16khz 下的，然后 * self.zc 还原为采样点数，再除以 16000 得到对应的时间， * sr 得到 22050 对应的长度, //hop_length 得到 mel 长度
        target_lengths = torch.LongTensor([(skip_head + return_length + skip_tail - ce_dit_difference * 50) / 50 * sr // hop_length]).to(S_alt.device)
        cond = model.length_regulator(
            S_alt, ylens=target_lengths , n_quantizers=3, f0=shifted_f0_alt
        )[0]
        cat_condition = torch.cat([prompt_condition, cond], dim=1)
        
        senmantic_time = time.perf_counter() - t0  # which includes semantic and length_regulator
        chunk_time_records["sem"] = senmantic_time
        
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
        chunk_time_records["dit"] = dit_time
        
        # vocoder model
        t0 = time.perf_counter()
   
        vc_wave = vocoder_fn(vc_target).squeeze()  # vc_wave sr = 22050?
        
        vocoder_time = time.perf_counter() - t0
        chunk_time_records["voc"] = vocoder_time
        
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
        unique_id = Path(wav_path).name + "_file-vc" # 针对文件使用文件名作为 unique_id 
        session = self.create_session(session_id=unique_id) 
        
        num_blocks = len(wav_data) // self.block_frame  # TODO 后续把结尾的block补上，padding 防止丢失
        for i in range(num_blocks):           
            block_data = wav_data[i * self.block_frame: (i + 1) * self.block_frame]
            self.chunk_vc(block_data, session)

        session.save()  # save wav
        session.cleanup()  # clear session data
                
    def _vad(self, indata, session: Session):
        """VAD函数
        
        Args:
            indata: 输入音频数据，采样率必须为16k
            session: 会话对象
        """
        t0 = time.perf_counter()
        
        vad_model = self.models["vad_model"]
        res = vad_model.generate(input=indata, cache=session.vad_cache, is_final=False, chunk_size=self.vad_chunk_size, disable_pbar=True)  # ---- 改成优化后的函数
        res_value = res[0]["value"]
        if len(res_value) % 2 == 1 and not session.vad_speech_detected:
            session.vad_speech_detected = True
        elif len(res_value) % 2 == 1 and session.vad_speech_detected:
            session.set_speech_detected_false_at_end_flag = True
            
        vad_time = time.perf_counter() - t0
        session.chunk_time_records["vad"] = vad_time
    
    def _preprocessing(self, indata, session: Session):
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
        session.chunk_time_records["pre"] = preprocess_time
        
    def _f0_extractor(self, session:Session):
        """音高提取函数
        
        1. 提取音高
        2. 更新 median_log_f0_alt
        3. 更新 shifted_f0_alt
        """
        if session.vad_speech_detected:  # only extract f0 when vad detected
            t0 = time.perf_counter()
            
            f0_alt = self.models['f0_fn'](session.input_wav, thred=0.03)  # 计算当前音频片段的f0
            
            if session.current_num_f0_blocks < self.cfg.total_block_for_f0:  # 累计计算当前通话的 median_log_f0_alt
                # median_log_f0_alt
                chunk_f0_alt = f0_alt[ -self.f0_chunk_size: ]  # 只累计当前chunk，而不加入上下文，以免重复加入
                chunk_voiced_f0_alt = chunk_f0_alt[ chunk_f0_alt > 1 ]
                chunk_voiced_log_f0_alt = np.log(chunk_voiced_f0_alt + 1e-5)
                session.voiced_log_f0_alt.extend(chunk_voiced_log_f0_alt)
                session.current_num_f0_blocks += 1
                session.median_log_f0_alt = torch.tensor(np.median(session.voiced_log_f0_alt)).to(self.cfg.device)
                logger.info(f"{session.session_id} | median_log_f0_alt: {session.median_log_f0_alt.item():.2f} | current_num_f0_blocks: {session.current_num_f0_blocks}")
                
            # shifted_f0_alt
            f0_alt = torch.from_numpy(f0_alt).to(self.cfg.device)[None]
            log_f0_alt = torch.log(f0_alt + 1e-5)
            shifted_log_f0_alt = log_f0_alt.clone()
            shifted_log_f0_alt[f0_alt > 1] = log_f0_alt[f0_alt > 1] - session.median_log_f0_alt + self.reference['median_log_f0_ori']
            session.shifted_f0_alt = torch.exp(shifted_log_f0_alt)
            
            f0_extractor_time = time.perf_counter() - t0
            session.chunk_time_records["f0"] = f0_extractor_time
        
    def _voice_conversion(self, session: Session) -> torch.Tensor:
        """vc inference 
        
        Returns:
            infer_wav: 推理后的音频数据, torch.tensor, device=self.cfg.device
        """
        if session.vad_speech_detected or session.is_first_chunk:  # if don't detect speech, set to zero
            infer_wav = self._vc_infer(
                session.input_wav,
                self.skip_head,
                self.skip_tail,
                self.return_length,
                int(self.cfg.diffusion_steps),
                self.cfg.inference_cfg_rate,
                session.shifted_f0_alt,  # 默认是 None，兼容不取音高的模式
                session.chunk_time_records
            )
            
            # model sr != common sr 的话，会 resample 到 common sr
            if self.resampler_model_to_common is not None:  
                logger.debug(f"before resample: {infer_wav.shape}")
                infer_wav = self.resampler_model_to_common(infer_wav)
                logger.debug(f"after resample: {infer_wav.shape}, theroy_length: 8800")
        else:
            infer_wav = session.infer_wav_zero.clone()
        
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
        session.chunk_time_records["sola"] = sola_time
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
        
        if session.vad_speech_detected or session.is_first_chunk:  # only do rms-mixing when vad detected
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
            
            rms_mixing_time = time.perf_counter() - t0
            session.chunk_time_records["rms_m"] = rms_mixing_time
            
        return infer_wav

    def chunk_vc(self, in_data: np.ndarray, session: Session) -> None:
        """chunk推理函数
        
        Args:
            indata: self.cfg.samplerate 采样率的音频数据, pcm格式, channel=1
        """
        start_time = time.perf_counter()
        session.chunk_time_records = {}
        
        logger.debug(f"in_data.max: {in_data.max()}, in_data.min: {in_data.min()}")
        if self.cfg.save_input:  # save input chunk
            session.add_chunk_input(in_data)
        
        in_data = librosa.to_mono(in_data.T)  # 转换完之后的indata shape: (11025,), max=1.0116995573043823, min=-1.0213052034378052
        
        # 1. vad
        self._vad(in_data, session) 
        
        # 2. preprocessing
        self._preprocessing(in_data, session) 
        
        
        # 3. F0 extraction
        if self.cfg.is_f0:  # only extract f0 when vad detected
            self._f0_extractor(session)  # 更新 median_log_f0_alt 和 shifted_f0_alt
            
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
        is_speech_detected = "Y" if session.vad_speech_detected else "N"
        if session.set_speech_detected_false_at_end_flag:
            session.vad_speech_detected = False
            session.set_speech_detected_false_at_end_flag = False
        
        if self.cfg.save_output:  # save output chunk
            session.add_chunk_output(session.out_data)
            
        if session.is_first_chunk: 
            session.is_first_chunk = False
        
        # tracking
        chunk_time = time.perf_counter() - start_time
        time_msg = " | ".join([f"{k}: {v*1000:0.1f}" for k, v in session.chunk_time_records.items()])
        time_msg = f"{is_speech_detected} | chunk: {chunk_time*1000:0.1f} | " + time_msg
            
        return time_msg

