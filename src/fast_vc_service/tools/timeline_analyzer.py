import json
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from loguru import logger
from fast_vc_service.config import Config


class TimelineAnalyzer:
    """音频流处理时间线分析工具"""
    
    @staticmethod
    def calculate_latency_stats(session_id, 
                                send_timeline, recv_timeline, 
                                prefill_time=None,
                                output_dir=None):
        """
        Calculate comprehensive latency and streaming performance statistics.
        
        Args:
            session_id: Session identifier
            send_timeline: List of {'timestamp': str, 'cumulative_ms': float}
            recv_timeline: List of {'timestamp': str, 'cumulative_ms': float}
            prefill_time: Prefill time in milliseconds (optional, defaults to config value)
            output_dir: Directory to save stats (optional)
        
        Returns:
            dict: Comprehensive statistics including latency, RTF, and streaming metrics
        """
        
        if not send_timeline or not recv_timeline:
            return {"error": "Empty timeline data"}
        
        # Get prefill_time from config
        if prefill_time is None:
            config = Config().get_config()
            prefill_time = config.buffer.prefill_time
        
        # Convert to DataFrames for easier processing
        send_df = pd.DataFrame(send_timeline)
        recv_df = pd.DataFrame(recv_timeline)
        recv_df['cumulative_ms'] = (recv_df['cumulative_ms'] - prefill_time).copy()  # Adjust for prefill time
        
        # Convert timestamps to datetime objects
        send_df['datetime'] = pd.to_datetime(send_df['timestamp'])
        recv_df['datetime'] = pd.to_datetime(recv_df['timestamp'])
        
        # Calculate time differences in milliseconds from start
        send_start = send_df['datetime'].iloc[0]
        recv_start = recv_df['datetime'].iloc[0]
        
        send_df['elapsed_ms'] = (send_df['datetime'] - send_start).dt.total_seconds() * 1000
        recv_df['elapsed_ms'] = (recv_df['datetime'] - recv_start).dt.total_seconds() * 1000
        
        stats = {}
        
        # 1. First Token Latency (首包延迟)
        first_send_time = send_df['elapsed_ms'].iloc[0]
        first_recv_time = recv_df['elapsed_ms'].iloc[0]
        stats['first_token_latency_ms'] = first_recv_time - first_send_time
        
        # 2. End-to-End Latency (端到端延迟)
        last_send_time = send_df['elapsed_ms'].iloc[-1]
        last_recv_time = recv_df['elapsed_ms'].iloc[-1]
        stats['end_to_end_latency_ms'] = last_recv_time - last_send_time
        
        # 3. Audio-based Latency Analysis (基于音频时长的延迟分析)
        chunk_latencies = []
        
        for _, recv_row in recv_df.iterrows():
            recv_audio_ms = recv_row['cumulative_ms']
            recv_time = recv_row['elapsed_ms']
            
            # Find the send event that corresponds to this audio duration
            corresponding_send = send_df[send_df['cumulative_ms'] >= recv_audio_ms]
            
            if not corresponding_send.empty:
                send_time = corresponding_send.iloc[0]['elapsed_ms']
                latency = recv_time - send_time
                chunk_latencies.append({
                    'audio_ms': recv_audio_ms,
                    'latency_ms': latency,
                    'send_time': send_time,
                    'recv_time': recv_time
                })
        
        if chunk_latencies:
            latency_values = [item['latency_ms'] for item in chunk_latencies]
            stats['chunk_latency_stats'] = {
                'mean_ms': np.mean(latency_values),
                'median_ms': np.median(latency_values),
                'min_ms': np.min(latency_values),
                'max_ms': np.max(latency_values),
                'std_ms': np.std(latency_values),
                'p95_ms': np.percentile(latency_values, 95),
                'p99_ms': np.percentile(latency_values, 99)
            }
            
            # 4. Jitter (延迟抖动)
            stats['jitter_ms'] = np.std(latency_values)
        
        # 5. Real-time Factor (RTF) Analysis
        if chunk_latencies:
            chunk_rtfs = []
            
            for i, latency_info in enumerate(chunk_latencies):
                if i == 0:
                    chunk_audio_duration = latency_info['audio_ms']
                else:
                    chunk_audio_duration = latency_info['audio_ms'] - chunk_latencies[i-1]['audio_ms']
                
                chunk_processing_time = latency_info['latency_ms']
                
                if chunk_audio_duration > 0:
                    chunk_rtf = chunk_processing_time / chunk_audio_duration
                    chunk_rtfs.append(chunk_rtf)
            
            if chunk_rtfs:
                stats['real_time_factor'] = {
                    'mean': np.mean(chunk_rtfs),
                    'median': np.median(chunk_rtfs),
                    'min': np.min(chunk_rtfs),
                    'max': np.max(chunk_rtfs),
                    'std': np.std(chunk_rtfs),
                    'p95': np.percentile(chunk_rtfs, 95),
                    'p99': np.percentile(chunk_rtfs, 99)
                }
                stats['is_real_time'] = stats['real_time_factor']['mean'] <= 1.0
        
        # 6. Send Timing Analysis (发送时序分析)
        if len(send_df) > 1:
            send_timing_analysis = []
            actual_intervals = []
            
            for i in range(1, len(send_df)):
                actual_interval = send_df.iloc[i]['elapsed_ms'] - send_df.iloc[i-1]['elapsed_ms']
                actual_intervals.append(actual_interval)
                
                expected_audio_interval = send_df.iloc[i]['cumulative_ms'] - send_df.iloc[i-1]['cumulative_ms']
                
                send_delay = actual_interval - expected_audio_interval
                send_timing_analysis.append({
                    'chunk_index': i,
                    'expected_interval_ms': expected_audio_interval,
                    'actual_interval_ms': actual_interval,
                    'send_delay_ms': send_delay,
                    'delay_ratio': send_delay / expected_audio_interval if expected_audio_interval > 0 else 0
                })
            
            if send_timing_analysis:
                send_delays = [item['send_delay_ms'] for item in send_timing_analysis]
                delay_ratios = [item['delay_ratio'] for item in send_timing_analysis]
                
                stats['send_timing_analysis'] = {
                    'total_chunks': len(send_timing_analysis),
                    'send_delay_stats': {
                        'mean_ms': np.mean(send_delays),
                        'median_ms': np.median(send_delays),
                        'min_ms': np.min(send_delays),
                        'max_ms': np.max(send_delays),
                        'std_ms': np.std(send_delays),
                        'p95_ms': np.percentile(send_delays, 95),
                        'p99_ms': np.percentile(send_delays, 99)
                    },
                    'delay_ratio_stats': {
                        'mean': np.mean(delay_ratios),
                        'median': np.median(delay_ratios),
                        'min': np.min(delay_ratios),
                        'max': np.max(delay_ratios),
                        'std': np.std(delay_ratios),
                        'p95': np.percentile(delay_ratios, 95),
                        'p99': np.percentile(delay_ratios, 99)
                    },
                    'timing_quality': {
                        'chunks_with_positive_delay': sum(1 for d in send_delays if d > 0),
                        'chunks_with_significant_delay': sum(1 for d in send_delays if d > 10),
                        'max_consecutive_delays': TimelineAnalyzer._calculate_max_consecutive_delays(send_delays),
                        'is_sending_stable': np.std(send_delays) < 5.0
                    }
                }
        
        # 7. Timeline Summary
        total_audio_duration_ms = send_df['cumulative_ms'].iloc[-1]
        total_processing_time_ms = recv_df['elapsed_ms'].iloc[-1] - send_df['elapsed_ms'].iloc[0]
        stats['timeline_summary'] = {
            'total_send_events': len(send_timeline),
            'total_recv_events': len(recv_timeline),
            'send_duration_ms': total_audio_duration_ms,
            'recv_duration_ms': recv_df['cumulative_ms'].iloc[-1] if len(recv_df) > 0 else 0,
            'processing_start_to_end_ms': total_processing_time_ms
        }
        
        # Save stats to file if output directory is provided
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            stats_file = output_dir / f"{session_id}_stats.json"
            with open(stats_file, 'w') as f:
                json.dump(stats, f, indent=2, default=str)
            logger.info(f"Saved latency stats for session {session_id} to {stats_file}")
        
        return stats
    
    @staticmethod
    def _calculate_max_consecutive_delays(send_delays, threshold_ms=5):
        """计算连续延迟的最大长度"""
        consecutive_delays = 0
        max_consecutive = 0
        for delay in send_delays:
            if delay > threshold_ms:
                consecutive_delays += 1
                max_consecutive = max(max_consecutive, consecutive_delays)
            else:
                consecutive_delays = 0
        return max_consecutive
    
    @staticmethod
    def merge_timeline(send_timeline, recv_timeline, session_id):
        """合并发送和接收时间线"""
        merged_timeline = []
        
        # 添加 send 事件
        for event in send_timeline:
            merged_timeline.append({
                'timestamp': event['timestamp'],
                'cumulative_ms': event['cumulative_ms'],
                'event_type': 'send',
                'session_id': session_id
            })
        
        # 添加 receive 事件
        for event in recv_timeline:
            merged_timeline.append({
                'timestamp': event['timestamp'],
                'cumulative_ms': event['cumulative_ms'],
                'event_type': 'recv',
                'session_id': session_id
            })
        
        # 按时间戳排序
        merged_timeline.sort(key=lambda x: x['timestamp'])
        return merged_timeline