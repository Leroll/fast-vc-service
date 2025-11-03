import os
import numpy as np
import torch
import soundfile as sf
from loguru import logger
from pathlib import Path
from datetime import datetime
import json
import traceback
import asyncio
import concurrent.futures
from enum import Enum
import time

from fast_vc_service.tools.timeline_analyzer import TimelineAnalyzer


class EventType(Enum):
    """事件类型枚举"""
    SEND = "send"
    RECV = "recv"


class Session:
    """针对单通音频，流式vc过程中, 存储上下文状态类"""
    
    def __init__(self,session_id, 
                 sr_in, sr_out,
                 input_wav_frame, return_frame,
                 block_frame_out,
                 sola_buffer_frame_out,
                 save_dir,
                 device,
                 send_slow_threshold, recv_slow_threshold):
        torch.cuda.empty_cache()  
        self.sr_in = sr_in  # 后续存储输入音频用
        self.sr_out = sr_out  # 后续存储输出音频用
        self.session_id = session_id  # 唯一标识符
        self.input_wav_record = []
        self.output_wav_record = []
        self.save_dir = save_dir
        self.is_saved = False  # flag to indicate if the session has been saved
        self.is_first_chunk = True  # 是否是第一个chunk，第一次收到音频包会调用模型，把延迟放在这里
        
        # f0 extractor
        self.voiced_log_f0_alt = []  # 存储用于计算median_log_f0_alt的音高
        self.current_num_f0_blocks = 0  # 当前累计的音高块数
        self.median_log_f0_alt = None  # 最终用于计算的中位数音高
        self.shifted_f0_alt = None  # 当前chunk的input_wav对应转换音高
        
        # SLOW tracking
        self.sent_slow_threshold = send_slow_threshold  # 两个客户段发送过来的音频包之间的间隔，认定SLOW的阈值， 单位ms
        self.recv_slow_threshold = recv_slow_threshold  # 两个客户段收到的音频包之间的间隔，认定SLOW的阈值， 单位ms
        self.last_send_time = None  # 服务侧上一个接受到客户端发送的包的时间 （send是基于客户端角度来讲的）
        self.last_recv_time = None  # 服务侧上一个换声后的chunk发送给客户段的时间 （recv是基于客户端角度来讲的）
        
        # Timeline tracking 
        self.timeline = []  # 统一记录所有事件的时间线
        self.sent_audio_ms = 0.0  # 累计发送的音频时长，这里的发送接受是基于客户端的角色来定的，客户端发送了多少
        self.recv_audio_ms = 0.0  # 累计接收的音频时长，这里的发送接受是基于客户端的角色来定的，服务端换声了多少
        
        # chunk time cost records
        self.chunk_time_records = {}  # 记录每个chunk在各个环节的时间消耗情况
        
        # wav 相关
        self.input_wav: torch.Tensor = torch.zeros( 
            input_wav_frame,
            device=device,
            dtype=torch.float32,
        )  # 默认：2.5s(extra) + 0.02s(sola_search) + 0.04s(sola_buffer) + 0.5s(block) + 0.02(extra_right) 
        
        # vad
        self.vad_cache = {}
        self.vad_speech_detected = False
        self.set_speech_detected_false_at_end_flag = False
        
        # vc models
        self.infer_wav_zero = torch.zeros(
            return_frame,
            device=device,
            dtype=torch.float32,
        ) # vc时若未检测出人声，用于填补的 zero
        
        # sola
        self.sola_buffer: torch.Tensor = torch.zeros(
            sola_buffer_frame_out, 
            device=device, 
            dtype=torch.float32
        )
        
        # outdata
        self.out_data: np.ndarray = np.zeros(block_frame_out, dtype="float32")  
        
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

    def record_event(self, event_type: EventType, chunk_duration_ms):
        """记录事件到统一时间线
        
        Args:
            event_type: 事件类型 (EventType.SEND 或 EventType.RECV)
            chunk_duration_ms: 音频块的时长（毫秒）
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        cur_time = time.perf_counter()
        
        if event_type == EventType.SEND:
            self.sent_audio_ms += chunk_duration_ms
            cumulative_ms = self.sent_audio_ms
            
            if self.last_send_time and self.last_recv_time:
                interval = (cur_time - self.last_send_time) * 1000
                c1 = interval > self.sent_slow_threshold
                c2 = self.last_send_time >= self.last_recv_time  # last_send_time 晚于 last_recv_time
                                                                # 排除受vc阻塞而导致的假延迟
                if c1 and c2:
                    logger.warning(f"{self.session_id} | [SEND_SLOW]: {interval:.2f} ms")
                self.last_send_time = cur_time 
            
        elif event_type == EventType.RECV:
            self.recv_audio_ms += chunk_duration_ms
            cumulative_ms = self.recv_audio_ms
            
            interval = (cur_time - self.last_recv_time) * 1000 if self.last_recv_time is not None else 0
            self.last_recv_time = cur_time
            if interval > self.recv_slow_threshold:
                logger.warning(f"{self.session_id} | [RECV_SLOW]: {interval:.2f} ms")
            
        else:
            raise ValueError(f"Unknown event type: {event_type}")
        
        self.timeline.append({
            'timestamp': timestamp,
            'cumulative_ms': cumulative_ms,
            'event_type': event_type.value,
            'session_id': self.session_id
        })

    async def async_save_and_cleanup(self):
        """异步版本的保存和清理方法"""
        try:
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, self.save_and_cleanup)
        except Exception as e:
            logger.error(f"{self.session_id} | Error in async save and cleanup: {traceback.format_exc()}")

    def save_and_cleanup(self):
        """保存和清理"""
        try:
            self.save()
            logger.info(f"{self.session_id} | Session data saved successfully")
        except Exception as e:
            logger.error(f"{self.session_id} | Error saving session data: {e}")
        finally:
            try:
                self.cleanup()
                logger.info(f"{self.session_id} | Session cleanup completed")
            except Exception as cleanup_error:
                logger.error(f"{self.session_id} | Error during cleanup: {traceback.format_exc()}")

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
            sf.write(str(input_path), np.concatenate(self.input_wav_record), self.sr_in)
            logger.info(f"{self.session_id} | Input audio saved to : {input_path}")
        
        # Output audio
        if self.output_wav_record:
            output_path = daily_save_dir / f"{self.session_id}_output.wav"
            sf.write(str(output_path), np.concatenate(self.output_wav_record), self.sr_out)
            logger.info(f"{self.session_id} | Output audio saved to : {output_path}")
        
        
        # Save timeline data (simplified format)
        if self.timeline:
            timeline_data = {
                'session_id': self.session_id,
                'merged_timeline': self.timeline
            }
            
            timeline_path = daily_save_dir / f"{self.session_id}_timeline.json"
            with open(timeline_path, 'w') as f:
                json.dump(timeline_data, f, indent=2, default=str)
            logger.info(f"{self.session_id} | Timeline data saved to: {timeline_path}")
            
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
        self.timeline.clear()
        
        # Force GPU memory cleanup
        torch.cuda.empty_cache()
        
    def __del__(self):
        """析构器，释放资源"""
        try:
            self.cleanup()
        except:
            pass  # Ignore errors during cleanup in destructor

