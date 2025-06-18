import os
import numpy as np
import torch
import soundfile as sf
from loguru import logger
from pathlib import Path
from datetime import datetime
import json

from fast_vc_service.tools.timeline_analyzer import TimelineAnalyzer


class Session:
    """针对单通音频，流式vc过程中, 存储上下文状态类"""
    
    def __init__(self,session_id, extra_frame, crossfade_frame, sola_search_frame, 
                 block_frame, extra_frame_right, zc, 
                 sola_buffer_frame, samplerate,
                 save_dir,
                 device):
        torch.cuda.empty_cache()  
        self.sampelrate = samplerate  # 后续存储输入、输出音频用，对应common_sr
        self.session_id = session_id  # 唯一标识符
        self.input_wav_record = []
        self.output_wav_record = []
        self.save_dir = save_dir
        self.is_saved = False  # flag to indicate if the session has been saved
        self.is_first_chunk = True 
        
        # Timeline tracking
        self.send_timeline = []  # 记录发送音频的时间线
        self.recv_timeline = []  # 记录接收音频的时间线
        self.sent_audio_ms = 0.0  # 累计发送的音频时长
        self.recv_audio_ms = 0.0  # 累计接收的音频时长
        self.stats = None  # 分析统计结果
        
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

    def record_send_event(self, chunk_duration_ms):
        """记录发送事件到时间线
        
        Args:
            chunk_duration_ms: 音频块的时长（毫秒）
        """
        self.sent_audio_ms += chunk_duration_ms
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.send_timeline.append({
            'timestamp': timestamp,
            'cumulative_ms': self.sent_audio_ms
        })
        logger.debug(f"{self.session_id} | send | {self.sent_audio_ms:.1f}ms")
        
    def record_recv_event(self, chunk_duration_ms):
        """记录接收事件到时间线
        
        Args:
            chunk_duration_ms: 音频块的时长（毫秒）
        """
        self.recv_audio_ms += chunk_duration_ms
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.recv_timeline.append({
            'timestamp': timestamp,
            'cumulative_ms': self.recv_audio_ms
        })
        logger.debug(f"{self.session_id} | recv | {self.recv_audio_ms:.1f}ms")

    def analyze_timeline(self):
        """分析时间线数据并生成统计信息"""
        if not self.send_timeline or not self.recv_timeline:
            logger.warning(f"{self.session_id} | Cannot analyze timeline: empty data")
            return
            
        try:
            self.stats = TimelineAnalyzer.calculate_latency_stats(
                session_id=self.session_id,
                send_timeline=self.send_timeline,
                recv_timeline=self.recv_timeline,
                output_dir=None  # 在save方法中统一保存
            )
            logger.info(f"{self.session_id} | Timeline analysis completed")
        except Exception as e:
            logger.error(f"{self.session_id} | Timeline analysis failed: {e}")
            self.stats = {"error": str(e)}

    def save(self):
        """save the input and output audio to files with hierarchical date structure
        """
        if self.is_saved:
            return
        
        # create herarchical directory structure based on current date
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        
        daily_save_dir = Path(self.save_dir) / year / month / day
        daily_save_dir.mkdir(parents=True, exist_ok=True)
        
        # Input audio
        if self.input_wav_record:
            input_path = daily_save_dir / f"{self.session_id}_input.wav"
            sf.write(str(input_path), np.concatenate(self.input_wav_record), self.sampelrate)
            logger.info(f"{self.session_id} | Input audio saved to : {input_path}")
        
        # Output audio
        if self.output_wav_record:
            output_path = daily_save_dir / f"{self.session_id}_output.wav"
            sf.write(str(output_path), np.concatenate(self.output_wav_record), self.sampelrate)
            logger.info(f"{self.session_id} | Output audio saved to : {output_path}")
        
        # Analyze timeline and save
        self.analyze_timeline()
        
        # Save timeline data
        if self.send_timeline or self.recv_timeline:
            timeline_data = {
                'session_id': self.session_id,
                'send_timeline': self.send_timeline,
                'recv_timeline': self.recv_timeline,
                'merged_timeline': TimelineAnalyzer.merge_timeline(
                    self.send_timeline, self.recv_timeline, self.session_id
                )
            }
            
            timeline_path = daily_save_dir / f"{self.session_id}_timeline.json"
            with open(timeline_path, 'w') as f:
                json.dump(timeline_data, f, indent=2, default=str)
            logger.info(f"{self.session_id} | Timeline data saved to: {timeline_path}")
        
        # Save stats
        if self.stats:
            stats_path = daily_save_dir / f"{self.session_id}_stats.json"
            with open(stats_path, 'w') as f:
                json.dump(self.stats, f, indent=2, default=str)
            logger.info(f"{self.session_id} | Statistics saved to: {stats_path}")
            
        self.is_saved = True
            
    def cleanup(self):
        """主动释放资源
        """
        # Clear tensors on GPU
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
        
        # Clear timeline data
        self.send_timeline.clear()
        self.recv_timeline.clear()
        self.stats = None
        
        # Force GPU memory cleanup
        torch.cuda.empty_cache()
        
    def __del__(self):
        """析构器，释放资源"""
        try:
            self.cleanup()
        except:
            pass  # Ignore errors during cleanup in destructor

