import os
import numpy as np
import torch
import soundfile as sf
from loguru import logger


class Session:
    """针对单通音频，流式vc过程中, 存储上下文状态类"""
    
    def __init__(self,session_id, extra_frame, crossfade_frame, sola_search_frame, 
                 block_frame, extra_frame_right, zc, 
                 sola_buffer_frame, samplerate,
                 device):
        torch.cuda.empty_cache()  
        self.sampelrate = samplerate  # 后续存储输入、输出音频用，对应common_sr
        self.session_id = session_id  # 唯一标识符
        self.input_wav_record = []
        self.output_wav_record = []
        
        # wav 相关
        self.input_wav: torch.Tensor = torch.zeros( 
            extra_frame
            + crossfade_frame
            + sola_search_frame
            + block_frame
            + extra_frame_right,
            device=device,
            dtype=torch.float32,
        )  # 2 * 44100 + 0.08 * 44100 + 0.01 * 44100 + 0.25 * 44100
        
        # vad
        self.vad_cache = {}
        self.vad_speech_detected = False
        self.set_speech_detected_false_at_end_flag = False
        
        # vc models
        begin = -sola_buffer_frame - sola_search_frame - block_frame - extra_frame_right
        end = -extra_frame_right
        self.infer_wav_zero = torch.zeros_like(self.input_wav[begin:end], 
                                               device=device)  # vc时若未检测出人声，用于填补的 zero
        
        # noise gate
        self.rms_buffer: np.ndarray = np.zeros(4 * zc, dtype="float32")  # 大小换成16k对应的; TODO 这里看下是不是可以改成 torch.tensor
        
        # sola
        self.sola_buffer: torch.Tensor = torch.zeros(
            sola_buffer_frame, device=device, dtype=torch.float32
        )
        
        # outdata
        self.out_data: np.ndarray = np.zeros(block_frame, dtype="float32")  
        
    def add_chunk_input(self, chunk:np.ndarray):
        """添加chunk到输入音频
        
        Args:
            chunk: 输入音频数据
        """
        self.input_wav_record.append(chunk)
        
    def add_chunk_output(self, chunk:np.ndarray):
        """添加chunk到输出音频
        
        Args:
            chunk: 输入音频数据
        """
        self.output_wav_record.append(chunk.copy())  # out_data是同一片段内存，不能直接append，必须copy

    def save(self, save_dir:str):
        """保存音频数据到指定目录
        
        Args:
            save_dir: 保存路径
        """
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        # 保存输入音频
        if self.input_wav_record is not None:
            input_path = os.path.join(save_dir, f"{self.session_id}_input.wav")
            sf.write(input_path, np.concatenate(self.input_wav_record), self.sampelrate)
            logger.info(f"{self.session_id} | input data 已存储: {input_path}")
        
        # 保存输出音频
        if self.output_wav_record is not None:
            output_path = os.path.join(save_dir, f"{self.session_id}_output.wav")
            sf.write(output_path, np.concatenate(self.output_wav_record), self.sampelrate)
            logger.info(f"{self.session_id} | output data 已存储: {output_path}")
            
    def cleanup(self):
        """主动释放资源
        """
        # Clear tensors on GPU
        # PyTorch tensors on GPU don't always immediately 
        # release memory when objects go out of scope. 
        # Setting tensors to None 
        # helps trigger garbage collection faster.
        self.input_wav = None
        self.sola_buffer = None
        
        # Clear VAD cache
        self.vad_cache.clear()
        
        # Clear numpy arrays
        self.rms_buffer = None
        self.out_data = None
        
        # Clear stored audio data
        self.input_wav_record.clear()
        self.output_wav_record.clear()
        
        # Force GPU memory cleanup
        torch.cuda.empty_cache()
        
    def __del__(self):
        """析构器，释放资源"""
        try:
            self.cleanup()
        except:
            pass  # Ignore errors during cleanup in destructor
        
