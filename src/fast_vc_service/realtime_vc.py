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
        vc_model_sr = self.models['mel_fn_args']['sampling_rate']  # vc model 的采样率，通常是22050
        assert self.cfg.SAMPLERATE_OUT == vc_model_sr, \
            f"SAMPLERATE_OUT must be equal to vc model sampling rate: {vc_model_sr}"
        self._init_realtime_parameters()  # init realtime parameters
        self.reference = self._cal_reference()
        self.instance_id = uuid.uuid4().hex
        logger.info(f"RealtimeVoiceConversion instance created with ID: {self.instance_id}, device: {self.cfg.device}")
    
    def _init_realtime_parameters(self):
        """Initialize parameters related to real-time processing"""
        
        # zc 精度
        # zc_frame_in，16k采样率对应的帧数，代表了pipeline中从开头到vc模型输入的精度，无论是 vad，rmvpe 还是 content encoder，都是16k的
        # zc_frame_out 代表从 vc 模型出来后的，模型输出采样率对应的帧数，一般为 22k，影响后续 rms-mixing, sola 模块
        self.zc_frame_in = self.cfg.SAMPLERATE_IN // self.cfg.FRAMERATE  # FRAMERATE: content encoder 的帧率
                                                                         # seed-vc: 50, rvc: 100 , 但是 rvc 对 hubert 做了插值到100
        self.zc_frame_out = self.cfg.SAMPLERATE_OUT // self.cfg.FRAMERATE
        
        # input_wav（16khz）
        self.extra_frame_ce = self.cfg.extra_time_ce * self.cfg.SAMPLERATE_IN  # extra time for content encoder
        self.extra_frame_ce = int( np.round( self.extra_frame_ce / self.zc_frame_in ) ) * self.zc_frame_in
        
        self.extra_frame_dit = self.cfg.extra_time_dit * self.cfg.SAMPLERATE_IN  # extra time for dit model
        self.extra_frame_dit = int( np.round( self.extra_frame_dit / self.zc_frame_in ) ) * self.zc_frame_in
        
        self.sola_search_frame = self.zc_frame_in  # sola_search, 16k sr
        
        self.sola_buffer_frame = self.cfg.sola_buffer_time * self.cfg.SAMPLERATE_IN 
        self.sola_buffer_frame = int( np.round( self.sola_buffer_frame / self.zc_frame_in ) ) * self.zc_frame_in
        
        self.block_frame = self.cfg.block_time * self.cfg.SAMPLERATE_IN  
        self.block_frame = int( np.round( self.block_frame / self.zc_frame_in) ) * self.zc_frame_in  
        self.block_frame_out = self.block_frame // self.zc_frame_in * self.zc_frame_out  # block frame in vc model output sr
        
        self.extra_frame_right = self.cfg.extra_time_right * self.cfg.SAMPLERATE_IN
        self.extra_frame_right = int( np.round( self.extra_frame_right / self.zc_frame_in ) ) * self.zc_frame_in
        
        self.input_wav_frame = (
            self.extra_frame_ce
            + self.sola_search_frame
            + self.sola_buffer_frame
            + self.block_frame
            + self.extra_frame_right
        )
        
        # sola (vc 模型后， 22khz), 先search，offset 对齐，再进行 crossfade
        self.sola_search_frame_out = self.zc_frame_out  # sola_search, 22k sr
        self.sola_buffer_frame_out = self.sola_buffer_frame // self.zc_frame_in * self.zc_frame_out  # sola_buffer, 22k sr
        self.fade_in_window: torch.Tensor = (
            torch.sin(
                0.5
                * np.pi
                * torch.linspace(
                    0.0,
                    1.0,
                    steps=self.sola_buffer_frame_out,
                    device=self.cfg.device,
                    dtype=torch.float32,
                )
            )
            ** 2
        ) 
        self.fade_out_window: torch.Tensor = 1 - self.fade_in_window  
        
        # vc models（22khz）
        self.ce_dit_diff_frame =  (
            self.extra_frame_ce // self.zc_frame_in
            - self.extra_frame_dit // self.zc_frame_in
        ) # content encoder 输入 和 dit model 输入的帧差，帧率是 content encoder framerate 50hz
        
        self.s_alt_target_length = (  # vc model 输入的总长度，单位是 mel 的帧数
                self.extra_frame_dit // self.zc_frame_in
            +   self.sola_buffer_frame // self.zc_frame_in
            +   self.block_frame // self.zc_frame_in
            +   self.extra_frame_right // self.zc_frame_in
        ) / self.cfg.FRAMERATE * self.cfg.SAMPLERATE_OUT // self.models["mel_fn_args"]["hop_size"]
        
        self.return_frame = (
                self.sola_search_frame_out
            +   self.sola_buffer_frame_out 
            +   self.block_frame_out
        )
        self.tail_frame = self.extra_frame_right // self.zc_frame_in * self.zc_frame_out
        
        # vad
        self.vad_chunk_size = 1000 * self.cfg.block_time  # 转换成ms
        
        # f0_extractor
        rmvpe_hop_length = 160  # 这个在RMVPE模型设置里面，hop_length设置的160
        self.f0_chunk_size = self.block_frame // rmvpe_hop_length + 1
        
        # rms-mixing
        self.return_frame_in = self.return_frame // self.zc_frame_out * self.zc_frame_in
        self.tail_frame_in = self.tail_frame // self.zc_frame_out * self.zc_frame_in
        
        
    def create_session(self, session_id):
        """创建一个新的会话"""
        return Session(session_id=session_id,
                       sr_in=self.cfg.SAMPLERATE_IN, sr_out=self.cfg.SAMPLERATE_OUT,
                       input_wav_frame=self.input_wav_frame, return_frame=self.return_frame,
                       block_frame_out=self.block_frame_out,
                       sola_buffer_frame_out=self.sola_buffer_frame_out,
                       save_dir=self.cfg.save_dir,
                       device=self.cfg.device,
                       send_slow_threshold=self.cfg.send_slow_threshold,
                       recv_slow_threshold=self.cfg.recv_slow_threshold)
    
    @torch.no_grad()
    def _cal_reference(self):
        """calculate model inputs which are related to reference wav
        
        # pipleline:
            rf_wav_16k -> [ fbank, cam++ ] -> prompt_style
            rf_wav_22050 -> [ to_mel ] -> prompt_mel
            rf_wav_16k -> [ semantic_fn, length_regulator, mel_size ] -> prompt_condition
        """
        reference_wav, _ = librosa.load(
            self.cfg.reference_wav_path, sr=self.cfg.SAMPLERATE_OUT, mono=True
        )
        
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
                  shifted_f0_alt=None,
                  chunk_time_records={}
                ):
        """vc inference
        
        input_wav -> [ semantic_fn, length_regulator ] -> cond
        prompt_condition + cond -> cat_condition
        
        cat_condition + prompt_mel + prompt_style -> vc_target
        """       
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
        S_alt = S_alt[:, self.ce_dit_diff_frame: ]  # align to dit model input 
    
        target_lengths = torch.LongTensor([self.s_alt_target_length]).to(S_alt.device)
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
            n_timesteps=self.cfg.diffusion_steps,
            inference_cfg_rate=self.cfg.inference_cfg_rate,
        )
        vc_target = vc_target[:, :, prompt_mel.size(-1) :]
        
        dit_time = time.perf_counter() - t0
        chunk_time_records["dit"] = dit_time
        
        # vocoder model
        t0 = time.perf_counter()
   
        vc_wave = vocoder_fn(vc_target).squeeze() 
        
        vocoder_time = time.perf_counter() - t0
        chunk_time_records["voc"] = vocoder_time
        
        # final output
        output = vc_wave[-self.return_frame - self.tail_frame : -self.tail_frame]  
        return output
                
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
        
        if session.vad_speech_detected:  # 检测到人声时，就正常全上下文滚动
            # 平移一个block_frame
            # 尝试使用 torch.roll() 耗时反而增加
            session.input_wav[: -self.block_frame] = session.input_wav[self.block_frame :].clone()  
        else:  # 未检测到人声时，只在return_frame + tail_frame 部分滚动，保留足够的上文，以防上文全静音，影响后续的vc效果
            session.input_wav[self.extra_frame_ce : -self.block_frame] = session.input_wav[self.extra_frame_ce + self.block_frame :].clone()   
        
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
                session.shifted_f0_alt,  # 默认是 None，兼容不取音高的模式
                session.chunk_time_records
            )
        else:
            infer_wav = session.infer_wav_zero.clone()
            
        if self.cfg.is_debug:
            import soundfile as sf
            t = time.time()
            Path("outputs/debug_vc").mkdir(parents=True, exist_ok=True)
            sf.write(f"outputs/debug_vc/{session.session_id}_{int(t*1000)}_input.wav", session.input_wav.cpu().numpy(), self.cfg.SAMPLERATE_IN)
            sf.write(f"outputs/debug_vc/{session.session_id}_{int(t*1000)}_vc.wav", infer_wav.cpu().numpy(), self.cfg.SAMPLERATE_OUT)
        
        return infer_wav 
    
    def _sola(self, infer_wav, session:Session):
        """algorithm for time-domain pitch-synchronous overlap-add
        
        infer_wav: [ sola_search + sola_buffer + block]
        """
        t0 = time.perf_counter()
        
        # SOLA algorithm from https://github.com/yxlllc/DDSP-SVC
        conv_input = infer_wav[
            None, None, : self.sola_search_frame_out + self.sola_buffer_frame_out
        ]  # sola_search + sola_buffer
        cor_nom = F.conv1d(conv_input, session.sola_buffer[None, None, :])  # sola-buffer initialized with zeros
                                                                            # dot product between the input and the buffer
                                                                            # 这里是滑动窗口 点积，每个buffer-frame的长度跟buffer点积
                                                                            # 结果是的到长度为 sola_search_frame + 1 的值
        cor_den = torch.sqrt(
            F.conv1d(
                conv_input**2,
                torch.ones(1, 1, self.sola_buffer_frame_out, device=self.cfg.device),
            )
            + 1e-8
        )   # 这里是求分母，input**2 是能量，在 sola_buffer上卷积，最终也得到 sola_search_frame + 1 的长度
        sola_offset = torch.argmax(cor_nom[0, 0] / cor_den[0, 0])  # 这里就是相似度了，找到最相似的 arg
        logger.debug(f"sola_offset: {sola_offset}, infer_wav.shape: {infer_wav.shape[0]}")

        # offset
        infer_wav = infer_wav[sola_offset:]
        
        # crossfade
        infer_wav[: self.sola_buffer_frame_out] *= self.fade_in_window  #
        infer_wav[: self.sola_buffer_frame_out] += (
            session.sola_buffer * self.fade_out_window
        )  
        
        # update sola_buffer
        session.sola_buffer[:] = infer_wav[
            self.block_frame_out : self.block_frame_out + self.sola_buffer_frame_out
        ]  # 前面 block_frame 部分会被输出，后面连贯的接下来要播放的部分更新到 buffer 中，留给下一个chunk再次 offset + crossfade
        
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
            
        # 分帧（使用 4D 输入给 F.unfold）
        frames = torch.nn.functional.unfold(
            waveform.view(1, 1, -1, 1),           # (N=1, C=1, H=T, W=1)
            kernel_size=(frame_length, 1),
            stride=(hop_length, 1),
        )  # -> (1, frame_length, num_frames)
        
        # 计算每帧的均方根
        rms = torch.sqrt(torch.mean(frames**2, dim=1, keepdim=True))  # (1,1,num_frames)
        return rms.squeeze(1)  # -> (1, num_frames)
        
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
            input_wav = session.input_wav[ -self.return_frame_in - self.tail_frame_in : -self.tail_frame_in] 
            
            # rms of input_wav
            rms_input = self._compute_rms(
                waveform=input_wav,  
                frame_length=4 * self.zc_frame_in,  
                hop_length=self.zc_frame_in,
                center=False,
            )
            rms_input = F.interpolate(
                rms_input.unsqueeze(0),            # (1,1,frames)
                size=infer_wav.shape[0] + 1,  
                mode="linear", 
                align_corners=True,
            )[0, 0, :-1]
            
            # rms of infer_wav
            rms_infer = self._compute_rms(
                waveform=infer_wav[:],
                frame_length=4 * self.zc_frame_out,  
                hop_length=self.zc_frame_out,
                center=False,
            )
            rms_infer = F.interpolate(
                rms_infer.unsqueeze(0),
                size=infer_wav.shape[0] + 1,
                mode="linear",
                align_corners=True,
            )[0, 0, :-1]
            rms_infer = torch.max(rms_infer, torch.zeros_like(rms_infer) + 1e-3)
            
            # 用标量指数避免 device 不一致
            infer_wav *= torch.pow(rms_input / rms_infer, 1.0 - self.cfg.rms_mix_rate)
            
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
        if self.cfg.is_f0 and session.vad_speech_detected:  # only extract f0 when vad detected
            self._f0_extractor(session)  # 更新 median_log_f0_alt 和 shifted_f0_alt
            
        # 4. voice conversion
        infer_wav = self._voice_conversion(session) 
        
        # 5. rms—mix
        if self.cfg.rms_mix_rate < 1:  
            infer_wav = self._rms_mixing(infer_wav, session)
            
        # 6. sola
        if self.cfg.is_sola :
            infer_wav = self._sola(infer_wav, session) 
        
        # 7. output
        session.out_data[:] = (
            infer_wav[: self.block_frame_out]  
            .t()
            .cpu()
            .numpy()
        )  # return the beginning of the output
           # add more latency include [sola_buffer + sola_search]
        
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

