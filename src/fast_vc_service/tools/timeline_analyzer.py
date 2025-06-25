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
        
        send_df['elapsed_ms'] = (send_df['datetime'] - send_start).dt.total_seconds() * 1000
        recv_df['elapsed_ms'] = (recv_df['datetime'] - send_start).dt.total_seconds() * 1000  # 改为使用 send_start
        
        stats = {}
        
        # 1. First Token Latency (首包延迟)
        first_send_time = send_df['elapsed_ms'].iloc[0]
        first_recv_time = recv_df['elapsed_ms'].iloc[0]
        stats['first_token_latency_ms'] = round(first_recv_time - first_send_time, 2)
        
        # 2. End-to-End Latency (端到端延迟)
        last_send_time = send_df['elapsed_ms'].iloc[-1]
        last_recv_time = recv_df['elapsed_ms'].iloc[-1]
        stats['end_to_end_latency_ms'] = round(last_recv_time - last_send_time, 2)
        
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
                'mean_ms': round(np.mean(latency_values), 2),
                'median_ms': round(np.median(latency_values), 2),
                'min_ms': round(np.min(latency_values), 2),
                'max_ms': round(np.max(latency_values), 2),
                'std_ms': round(np.std(latency_values), 2),
                'p95_ms': round(np.percentile(latency_values, 95), 2),
                'p99_ms': round(np.percentile(latency_values, 99), 2)
            }
            
            # 4. Jitter (延迟抖动)
            stats['jitter_ms'] = round(np.std(latency_values), 2)
        
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
                    'mean': round(np.mean(chunk_rtfs), 2),
                    'median': round(np.median(chunk_rtfs), 2),
                    'min': round(np.min(chunk_rtfs), 2),
                    'max': round(np.max(chunk_rtfs), 2),
                    'std': round(np.std(chunk_rtfs), 2),
                    'p95': round(np.percentile(chunk_rtfs, 95), 2),
                    'p99': round(np.percentile(chunk_rtfs, 99), 2)
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
                        'mean_ms': round(np.mean(send_delays), 2),
                        'median_ms': round(np.median(send_delays), 2),
                        'min_ms': round(np.min(send_delays), 2),
                        'max_ms': round(np.max(send_delays), 2),
                        'std_ms': round(np.std(send_delays), 2),
                        'p95_ms': round(np.percentile(send_delays, 95), 2),
                        'p99_ms': round(np.percentile(send_delays, 99), 2)
                    },
                    'delay_ratio_stats': {
                        'mean': round(np.mean(delay_ratios), 2),
                        'median': round(np.median(delay_ratios), 2),
                        'min': round(np.min(delay_ratios), 2),
                        'max': round(np.max(delay_ratios), 2),
                        'std': round(np.std(delay_ratios), 2),
                        'p95': round(np.percentile(delay_ratios, 95), 2),
                        'p99': round(np.percentile(delay_ratios, 99), 2)
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
            'send_duration_ms': round(total_audio_duration_ms, 2),
            'recv_duration_ms': round(recv_df['cumulative_ms'].iloc[-1] if len(recv_df) > 0 else 0, 2),
            'processing_start_to_end_ms': round(total_processing_time_ms, 2)
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
    
    @staticmethod
    def calculate_average_stats(stats_list):
        """
        Calculate average statistics from multiple concurrent sessions.
        
        Args:
            stats_list: List of stats dictionaries from multiple sessions
            
        Returns:
            dict: Averaged statistics representing overall concurrent performance
        """
        if not stats_list:
            return {"error": "Empty stats list"}
        
        # Filter out error entries
        valid_stats = [stats for stats in stats_list if "error" not in stats]
        if not valid_stats:
            return {"error": "No valid stats found"}
        
        n_sessions = len(valid_stats)
        averaged_stats = {
            "concurrent_sessions_count": n_sessions,
            "concurrent_analysis": True
        }
        
        # 1. Average First Token Latency
        first_token_latencies = [stats.get('first_token_latency_ms', 0) for stats in valid_stats if 'first_token_latency_ms' in stats]
        if first_token_latencies:
            averaged_stats['first_token_latency_ms'] = {
                'mean': round(np.mean(first_token_latencies), 2),
                'median': round(np.median(first_token_latencies), 2),
                'min': round(np.min(first_token_latencies), 2),
                'max': round(np.max(first_token_latencies), 2),
                'std': round(np.std(first_token_latencies), 2)
            }
        
        # 2. Average End-to-End Latency
        e2e_latencies = [stats.get('end_to_end_latency_ms', 0) for stats in valid_stats if 'end_to_end_latency_ms' in stats]
        if e2e_latencies:
            averaged_stats['end_to_end_latency_ms'] = {
                'mean': round(np.mean(e2e_latencies), 2),
                'median': round(np.median(e2e_latencies), 2),
                'min': round(np.min(e2e_latencies), 2),
                'max': round(np.max(e2e_latencies), 2),
                'std': round(np.std(e2e_latencies), 2)
            }
        
        # 3. Average Chunk Latency Stats
        chunk_stats_keys = ['mean_ms', 'median_ms', 'min_ms', 'max_ms', 'std_ms', 'p95_ms', 'p99_ms']
        chunk_latency_stats = {}
        
        for key in chunk_stats_keys:
            values = [stats.get('chunk_latency_stats', {}).get(key, 0) 
                     for stats in valid_stats 
                     if 'chunk_latency_stats' in stats and key in stats['chunk_latency_stats']]
            if values:
                chunk_latency_stats[key] = round(np.mean(values), 2)
        
        if chunk_latency_stats:
            averaged_stats['chunk_latency_stats'] = chunk_latency_stats
        
        # 4. Average Jitter
        jitter_values = [stats.get('jitter_ms', 0) for stats in valid_stats if 'jitter_ms' in stats]
        if jitter_values:
            averaged_stats['jitter_ms'] = {
                'mean': round(np.mean(jitter_values), 2),
                'median': round(np.median(jitter_values), 2),
                'min': round(np.min(jitter_values), 2),
                'max': round(np.max(jitter_values), 2),
                'std': round(np.std(jitter_values), 2)
            }
        
        # 5. Average Real-time Factor
        rtf_keys = ['mean', 'median', 'min', 'max', 'std', 'p95', 'p99']
        rtf_stats = {}
        
        for key in rtf_keys:
            values = [stats.get('real_time_factor', {}).get(key, 0) 
                     for stats in valid_stats 
                     if 'real_time_factor' in stats and key in stats['real_time_factor']]
            if values:
                rtf_stats[key] = round(np.mean(values), 2)
        
        if rtf_stats:
            averaged_stats['real_time_factor'] = rtf_stats
            
        # Real-time performance summary
        real_time_sessions = [stats.get('is_real_time', False) for stats in valid_stats if 'is_real_time' in stats]
        if real_time_sessions:
            averaged_stats['real_time_performance'] = {
                'sessions_real_time': sum(real_time_sessions),
                'total_sessions': len(real_time_sessions),
                'real_time_ratio': round(sum(real_time_sessions) / len(real_time_sessions), 2)
            }
        
        # 6. Average Send Timing Analysis
        if any('send_timing_analysis' in stats for stats in valid_stats):
            send_timing_stats = {}
            
            # Average delay stats
            delay_keys = ['mean_ms', 'median_ms', 'min_ms', 'max_ms', 'std_ms', 'p95_ms', 'p99_ms']
            delay_stats = {}
            
            for key in delay_keys:
                values = [stats.get('send_timing_analysis', {}).get('send_delay_stats', {}).get(key, 0)
                         for stats in valid_stats 
                         if 'send_timing_analysis' in stats and 
                            'send_delay_stats' in stats['send_timing_analysis'] and
                            key in stats['send_timing_analysis']['send_delay_stats']]
                if values:
                    delay_stats[key] = round(np.mean(values), 2)
            
            if delay_stats:
                send_timing_stats['send_delay_stats'] = delay_stats
            
            # Average delay ratio stats
            ratio_stats = {}
            for key in ['mean', 'median', 'min', 'max', 'std', 'p95', 'p99']:
                values = [stats.get('send_timing_analysis', {}).get('delay_ratio_stats', {}).get(key, 0)
                         for stats in valid_stats 
                         if 'send_timing_analysis' in stats and 
                            'delay_ratio_stats' in stats['send_timing_analysis'] and
                            key in stats['send_timing_analysis']['delay_ratio_stats']]
                if values:
                    ratio_stats[key] = round(np.mean(values), 2)
            
            if ratio_stats:
                send_timing_stats['delay_ratio_stats'] = ratio_stats
            
            # Timing quality aggregation
            total_chunks = sum([stats.get('send_timing_analysis', {}).get('total_chunks', 0) 
                               for stats in valid_stats if 'send_timing_analysis' in stats])
            
            positive_delays = sum([stats.get('send_timing_analysis', {}).get('timing_quality', {}).get('chunks_with_positive_delay', 0)
                                  for stats in valid_stats 
                                  if 'send_timing_analysis' in stats and 'timing_quality' in stats['send_timing_analysis']])
            
            significant_delays = sum([stats.get('send_timing_analysis', {}).get('timing_quality', {}).get('chunks_with_significant_delay', 0)
                                     for stats in valid_stats 
                                     if 'send_timing_analysis' in stats and 'timing_quality' in stats['send_timing_analysis']])
            
            stable_sessions = sum([stats.get('send_timing_analysis', {}).get('timing_quality', {}).get('is_sending_stable', False)
                                  for stats in valid_stats 
                                  if 'send_timing_analysis' in stats and 'timing_quality' in stats['send_timing_analysis']])
            
            max_consecutive_delays = [stats.get('send_timing_analysis', {}).get('timing_quality', {}).get('max_consecutive_delays', 0)
                                     for stats in valid_stats 
                                     if 'send_timing_analysis' in stats and 'timing_quality' in stats['send_timing_analysis']]
            
            timing_quality = {
                'total_chunks_all_sessions': total_chunks,
                'chunks_with_positive_delay_all_sessions': positive_delays,
                'chunks_with_significant_delay_all_sessions': significant_delays,
                'sessions_with_stable_sending': stable_sessions,
                'stable_sending_ratio': round(stable_sessions / n_sessions, 2) if n_sessions > 0 else 0
            }
            
            if max_consecutive_delays:
                timing_quality['avg_max_consecutive_delays'] = round(np.mean(max_consecutive_delays), 2)
                timing_quality['max_consecutive_delays_across_sessions'] = max(max_consecutive_delays)
            
            send_timing_stats['timing_quality'] = timing_quality
            send_timing_stats['total_chunks'] = total_chunks
            
            if send_timing_stats:
                averaged_stats['send_timing_analysis'] = send_timing_stats
        
        # 7. Timeline Summary Aggregation
        timeline_summaries = [stats.get('timeline_summary', {}) for stats in valid_stats if 'timeline_summary' in stats]
        if timeline_summaries:
            total_send_events = sum([summary.get('total_send_events', 0) for summary in timeline_summaries])
            total_recv_events = sum([summary.get('total_recv_events', 0) for summary in timeline_summaries])
            
            send_durations = [summary.get('send_duration_ms', 0) for summary in timeline_summaries]
            recv_durations = [summary.get('recv_duration_ms', 0) for summary in timeline_summaries]
            processing_times = [summary.get('processing_start_to_end_ms', 0) for summary in timeline_summaries]
            
            averaged_stats['timeline_summary'] = {
                'total_sessions': n_sessions,
                'total_send_events_all_sessions': total_send_events,
                'total_recv_events_all_sessions': total_recv_events,
                'avg_send_duration_ms': round(np.mean(send_durations), 2) if send_durations else 0,
                'avg_recv_duration_ms': round(np.mean(recv_durations), 2) if recv_durations else 0,
                'avg_processing_time_ms': round(np.mean(processing_times), 2) if processing_times else 0,
                'total_send_duration_ms': round(sum(send_durations), 2),
                'total_recv_duration_ms': round(sum(recv_durations), 2)
            }
        
        return averaged_stats
    
    @staticmethod
    def analyze_from_timeline_file(timeline_json_path, prefill_time=375):
        """
        从timeline.json文件中读取数据并计算延迟统计信息，保存到timeline文件所在目录
        
        Args:
            timeline_json_path: timeline.json文件路径
            prefill_time: Prefill时间（毫秒），可选，默认使用配置文件中的值
        """
        try:
            timeline_path = Path(timeline_json_path)
            if not timeline_path.exists():
                logger.error(f"Timeline file not found: {timeline_json_path}")
                return
            
            # 读取timeline.json文件
            with open(timeline_path, 'r') as f:
                timeline_data = json.load(f)
            
            # 检查必要字段
            if 'merged_timeline' not in timeline_data:
                logger.error(f"No merged_timeline found in the timeline file: {timeline_json_path}")
                return
            
            if 'session_id' not in timeline_data:
                logger.error(f"No session_id found in the timeline file: {timeline_json_path}")
                return
            
            session_id = timeline_data['session_id']
            merged_timeline = timeline_data['merged_timeline']
            
            # 从merged_timeline中分离send和recv事件
            send_timeline = []
            recv_timeline = []
            
            for event in merged_timeline:
                event_data = {
                    'timestamp': event['timestamp'],
                    'cumulative_ms': event['cumulative_ms']
                }
                
                if event['event_type'] == 'send':
                    send_timeline.append(event_data)
                elif event['event_type'] == 'recv':
                    recv_timeline.append(event_data)
            
            # 检查是否有足够的数据
            if not send_timeline or not recv_timeline:
                logger.error(f"Insufficient timeline data - send events: {len(send_timeline)}, recv events: {len(recv_timeline)}")
                return
            
            logger.info(f"Analyzing timeline for session {session_id} from {timeline_path}")
            logger.info(f"Found {len(send_timeline)} send events and {len(recv_timeline)} recv events")
            
            # 获取timeline文件所在目录作为输出目录
            output_dir = timeline_path.parent
            
            # 调用原有的统计函数，利用其保存功能
            TimelineAnalyzer.calculate_latency_stats(
                session_id=session_id,
                send_timeline=send_timeline,
                recv_timeline=recv_timeline,
                prefill_time=prefill_time,
                output_dir=output_dir
            )
            
            logger.info(f"Timeline analysis completed and saved for session {session_id}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON file {timeline_json_path}: {e}")
        except Exception as e:
            logger.error(f"Error analyzing timeline from file {timeline_json_path}: {e}")

    @staticmethod
    def batch_analyze_timeline_files(timeline_dir, file_pattern="*_timeline.json", prefill_time=375):
        """
        批量分析目录中的timeline文件，保存到各自的timeline文件夹
        
        Args:
            timeline_dir: 包含timeline文件的目录路径
            file_pattern: 文件名匹配模式，默认为"*_timeline.json"
            prefill_time: Prefill时间（毫秒），可选
        """
        timeline_dir = Path(timeline_dir)
        if not timeline_dir.exists():
            logger.error(f"Directory not found: {timeline_dir}")
            return
        
        timeline_files = list(timeline_dir.glob(file_pattern))
        if not timeline_files:
            logger.error(f"No timeline files found in {timeline_dir} with pattern {file_pattern}")
            return
        
        logger.info(f"Found {len(timeline_files)} timeline files to analyze")
        
        successful_analyses = 0
        failed_analyses = 0
        
        for timeline_file in timeline_files:
            logger.info(f"Analyzing {timeline_file.name}")
            
            try:
                TimelineAnalyzer.analyze_from_timeline_file(
                    timeline_json_path=timeline_file,
                    prefill_time=prefill_time
                )
                successful_analyses += 1
                logger.info(f"Successfully analyzed {timeline_file.name}")
            except Exception as e:
                failed_analyses += 1
                logger.error(f"Failed to analyze {timeline_file.name}: {e}")
        
        logger.info(f"Batch analysis completed: {successful_analyses} successful, {failed_analyses} failed")

    
if __name__ == "__main__":
    # 分析单个文件
    stats = TimelineAnalyzer.analyze_from_timeline_file(
        timeline_json_path="/path/to/session_123_timeline.json"
    )

    # 批量分析目录中的所有timeline文件
    # results = TimelineAnalyzer.batch_analyze_timeline_files(
    #     timeline_dir="/path/to/timeline/files"
    # )