import asyncio
import concurrent.futures
import argparse
import time
import json
import sys
from pathlib import Path
from datetime import datetime
import uuid
from loguru import logger
import os
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from examples.websocket.ws_client import send_audio_file


def run_single_client(client_id, client_config):
    """
    Run a single client in its own process
    
    Args:
        client_id: Unique identifier for this client
        client_config: Configuration dictionary for the client
        
    Returns:
        dict: Result dictionary with client timeline metrics
    """
    try:
        logger.info(f"Starting client {client_id} in process {os.getpid()}")
        
        # Generate unique session ID for this client
        session_id = f"client{client_id}_{uuid.uuid4().hex[:8]}"
        
        # Run the async client function in a new event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                send_audio_file(
                    websocket_url=client_config['websocket_url'],
                    api_key=client_config['api_key'],
                    audio_path=client_config['audio_path'],
                    real_time_simulation=client_config['real_time_simulation'],
                    session_id=session_id,
                    save_output=client_config['save_output'],
                    output_wav_dir=client_config['output_wav_dir'],
                    encoding=client_config['encoding'],
                    chunk_time_ms=client_config['chunk_time_ms'],
                    bitrate=client_config['bitrate'],
                    frame_duration_ms=client_config['frame_duration_ms']
                )
            )
        finally:
            loop.close()
        
        # Only keep client_id and timeline data
        filtered_result = {
            'client_id': client_id,
            'success': result.get('success', False),
            'send_timeline': result.get('send_timeline', []),
            'recv_timeline': result.get('recv_timeline', []),
            'process_id': os.getpid()
        }
        
        # Add error if not successful
        if not result.get('success', False):
            filtered_result['error'] = result.get('error', 'Unknown error')
        
        if result.get('success', False):
            logger.info(f"Client {client_id} completed successfully")
        else:
            logger.error(f"Client {client_id} failed: {result.get('error', 'Unknown error')}")
            
        return filtered_result
        
    except Exception as e:
        import traceback
        error_msg = f"Client {client_id} crashed: {traceback.format_exc()}"
        logger.error(error_msg)
        return {
            'client_id': client_id,
            'success': False,
            'error': error_msg,
            'send_timeline': [],
            'recv_timeline': [],
            'process_id': os.getpid()
        }


def run_multi_client_with_delay(max_workers, client_config, args):
    # Sequential start with delay
    logger.info(f"Starting clients with delay between each: {args.delay_between_starts}s")
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit clients one by one with delay
        futures = []
        for client_id in range(args.num_clients):
            future = executor.submit(run_single_client, client_id, client_config)
            futures.append((client_id, future))
            
            if client_id < args.num_clients - 1:  # Don't delay after the last client
                time.sleep(args.delay_between_starts)
        
        # Collect results as they complete
        for client_id, future in futures:
            try:
                result = future.result(timeout=args.timeout)
                results.append(result)
            except concurrent.futures.TimeoutError:
                logger.error(f"Client {client_id} timed out after {args.timeout}s")
                results.append({
                    'client_id': client_id,
                    'success': False,
                    'error': f'Timeout after {args.timeout}s',
                    'send_timeline': [],
                    'recv_timeline': [],
                    'process_id': None
                })
            except Exception as e:
                logger.error(f"Client {client_id} failed with exception: {e}")
                results.append({
                    'client_id': client_id,
                    'success': False,
                    'error': str(e),
                    'send_timeline': [],
                    'recv_timeline': [],
                    'process_id': None
                })
    return results


def run_multi_client(max_workers, client_config, args):
    # Parallel start (all at once)
    logger.info("Starting all clients simultaneously")
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all clients at once
        future_to_client = {
            executor.submit(run_single_client, client_id, client_config): client_id 
            for client_id in range(args.num_clients)
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_client, timeout=args.timeout):
            client_id = future_to_client[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(f"Client {client_id} got result.")
            except Exception as e:
                logger.error(f"Client {client_id} failed with exception: {e}")
                results.append({
                    'client_id': client_id,
                    'success': False,
                    'error': str(e),
                    'send_timeline': [],
                    'recv_timeline': [],
                    'process_id': None
                })
    return results


def calculate_latency_stats(client_id, 
                            send_timeline, recv_timeline, 
                            output_dir,
                            prefill_time=375):
    """
    Calculate comprehensive latency and streaming performance statistics.
    
    Args:
        send_timeline: List of {'timestamp': str, 'cumulative_ms': float}
        recv_timeline: List of {'timestamp': str, 'cumulative_ms': float}
        prefill_time: Time in ms to consider as prefill (default: 375ms)
    
    Returns:
        dict: Comprehensive statistics including latency, RTF, and streaming metrics
    """
    
    if not send_timeline or not recv_timeline:
        return {"error": "Empty timeline data"}
    
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
    # For each received audio segment, find the corresponding sent segment
    chunk_latencies = []
    
    for _, recv_row in recv_df.iterrows():
        recv_audio_ms = recv_row['cumulative_ms']
        recv_time = recv_row['elapsed_ms']
        
        # Find the send event that corresponds to this audio duration
        # We look for the send event where cumulative_ms >= recv_audio_ms
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
        # RTF = processing_time / audio_duration
        # for streaming, we calculate RTF for each chunk and average them
        chunk_rtfs = []
        
        for i, latency_info in enumerate(chunk_latencies):
            if i == 0:
                # 第一个chunk的音频时长
                chunk_audio_duration = latency_info['audio_ms']
            else:
                # 后续chunk的音频时长 = 当前累积时长 - 前一个累积时长
                chunk_audio_duration = latency_info['audio_ms'] - chunk_latencies[i-1]['audio_ms']
            
            # chunk的处理时间就是其延迟
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
        else:
            stats['real_time_factor'] = {'error': 'No valid chunk RTF data'}
            stats['is_real_time'] = False
    
    # 6. Send Timing Analysis (发送时序分析)
    send_timing_analysis = []
    expected_intervals = []
    actual_intervals = []
    
    for i in range(1, len(send_df)):
        # 计算实际发送时间间隔
        actual_interval = send_df.iloc[i]['elapsed_ms'] - send_df.iloc[i-1]['elapsed_ms']
        actual_intervals.append(actual_interval)
        
        # 计算期望的音频时间间隔
        expected_audio_interval = send_df.iloc[i]['cumulative_ms'] - send_df.iloc[i-1]['cumulative_ms']
        expected_intervals.append(expected_audio_interval)
        
        # 计算发送延迟：实际间隔 vs 期望间隔
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
                'chunks_with_significant_delay': sum(1 for d in send_delays if d > 10),  # >10ms delay
                'max_consecutive_delays': 0,  # 计算连续延迟的最大长度
                'is_sending_stable': np.std(send_delays) < 5.0  # 发送是否稳定（标准差<5ms）
            }
        }
        
        # 计算连续延迟的最大长度
        consecutive_delays = 0
        max_consecutive = 0
        for delay in send_delays:
            if delay > 5:  # 认为>5ms为延迟
                consecutive_delays += 1
                max_consecutive = max(max_consecutive, consecutive_delays)
            else:
                consecutive_delays = 0
        stats['send_timing_analysis']['timing_quality']['max_consecutive_delays'] = max_consecutive
    
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
    
    # Save stats to JSON file in the same directory as audio files
    stats_file = output_dir / f"client{client_id}_stats.json"
    with open(stats_file, 'w') as f:
        json.dump(stats, f, indent=2, default=str)
    
    logger.info(f"Saved latency stats for client {client_id} to {stats_file}")


def parse_args():
    parser = argparse.ArgumentParser(description="Concurrent WebSocket client for voice conversion load testing")
    
    # Concurrency parameters
    parser.add_argument("-c", "--num-clients", 
                        type=int,
                        default=5,
                        help="Number of concurrent clients to run (default: 5)")
    
    parser.add_argument("-w", "--max-workers",
                        type=int,
                        default=None,
                        help="Maximum number of worker processes (default: min(8, num_clients))")
    
    parser.add_argument("-d", "--delay-between-starts",
                        type=float,
                        default=0.0,
                        help="Delay in seconds between starting each client (default: 0.0)")
    
    parser.add_argument("-t", "--timeout",
                        type=int,
                        default=420,
                        help="Timeout in seconds for each client (default: 420)")
    
    # Client parameters
    parser.add_argument("--source-wav-path", 
                        default="wavs/sources/low-pitched-male-24k.wav", 
                        help="Path to source audio file")
    
    parser.add_argument("--output-wav-dir", 
                        default="outputs/concurrent_ws_client", 
                        help="Base directory to save output audio files")
    
    parser.add_argument("--url", 
                        default="ws://localhost:8042/ws", 
                        help="WebSocket URL")
    
    parser.add_argument("--api-key", 
                        default="test-key", 
                        help="API key for authentication")
    
    parser.add_argument("--chunk-time", 
                        type=int, 
                        default=20, 
                        help="Chunk time in ms for sending audio (default: 20ms)")
    
    parser.add_argument("--real-time", 
                        action="store_true", 
                        help="Simulate real-time audio sending")
    
    parser.add_argument("--no-real-time", 
                        action="store_true", 
                        help="Disable real-time simulation (send audio as fast as possible)")
    
    parser.add_argument("--encoding",
                       choices=["PCM", "OPUS"],
                       default="PCM",
                       help="Audio encoding format (PCM or OPUS)")
    
    parser.add_argument("--bitrate",
                       type=int,
                       default=128000,
                       help="Bitrate for OPUS encoding (default: 128000)")
    
    parser.add_argument("--frame-duration",
                       type=int,
                       default=20,
                       help="Frame duration in ms for OPUS encoding (default: 20)")
    
    parser.add_argument("--no-save-output",
                        action="store_true",
                        help="Disable saving the output audio files")
    
    args = parser.parse_args()
    
    # Create unique output directory with timestamp and client count
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = f"{timestamp}_clients{args.num_clients}_delay{args.delay_between_starts}s"
    output_dir = Path(args.output_wav_dir) / session_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Output directory: {output_dir}")
    
    # Prepare client configuration
    client_config = {
        'websocket_url': args.url,
        'api_key': args.api_key,
        'audio_path': args.source_wav_path,
        'real_time_simulation': not args.no_real_time,
        'save_output': not args.no_save_output,
        'output_wav_dir': str(output_dir),  # Use the session-specific directory
        'encoding': args.encoding,
        'chunk_time_ms': args.chunk_time,
        'bitrate': args.bitrate,
        'frame_duration_ms': args.frame_duration
    }
    
    logger.info(f"Configuration: {json.dumps(client_config, indent=2)}")
    logger.info(f"Concurrent clients: {args.num_clients}")
    
    # Determine max workers
    max_workers = args.max_workers or min(8, args.num_clients)
    logger.info(f"Max workers: {max_workers}")
    
    return max_workers, output_dir, client_config, args


def setup_logging():
    """
    Setup logging configuration with colors and standardized time format
    """
    logger.remove()  # Remove default logger
    
    # Define custom format with colors
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level}</level> | "
        "<cyan>{name}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Add console logger with colors
    logger.add(
        sys.stdout, 
        level="INFO", 
        format=console_format,
        filter=lambda record: "main" in record["name"] or "concurrent_ws_client" in record["name"],
        colorize=True,
        enqueue=True  # Make it thread-safe
    )
    
    # Define file format without colors
    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level} | "
        "{name} | "
        "{message}"
    )
    
    # Add file logger
    log_file = PROJECT_ROOT / "logs" / "concurrent_ws_client.log"
    log_file.parent.mkdir(exist_ok=True)  # Ensure logs directory exists
    
    logger.add(
        log_file, 
        level="DEBUG", 
        format=file_format, 
        rotation="10 MB",
        retention="7 days",  # Keep logs for 7 days
        compression="zip",   # Compress old logs
        filter=lambda record: "main" in record["name"] or "concurrent_ws_client" in record["name"],
        enqueue=True
    )
    
    logger.info("Logging setup complete")


def main():
    setup_logging()
    max_workers, output_dir, client_config, args = parse_args()

    t0 = time.perf_counter()    
    # Create and submit tasks
    if args.delay_between_starts > 0:
        results = run_multi_client_with_delay(max_workers, client_config, args)
    else:
        results = run_multi_client(max_workers, client_config, args)
    total_test_time = time.perf_counter() - t0
    
    # Calculate latency stats for each successful client and save to files
    successful_count = 0
    for result in results:
        client_id = result['client_id']
        
        result_file = output_dir / f"client{client_id}_result.json"
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        
        if result.get('success', False):
            calculate_latency_stats(
                client_id=client_id,
                send_timeline=result.get('send_timeline', []),
                recv_timeline=result.get('recv_timeline', []),
                output_dir=output_dir
            )
            successful_count += 1
    
    # Print summary
    failed = len(results) - successful_count
    logger.info(f"{'='*42}")
    logger.info(f"CONCURRENT CLIENT TEST SUMMARY: ")
    logger.info(f"Total clients: {args.num_clients}")
    logger.info(f"Successful: {successful_count}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Success rate: {successful_count/args.num_clients*100:.1f}%")
    logger.info(f"Total test time: {total_test_time:.2f}s")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"{'='*42}")


if __name__ == "__main__":
    main()