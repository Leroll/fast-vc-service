"""
Timeline Analyzer - Analyze send/recv events with latency calculation
"""

import pandas as pd
import json
import argparse
from datetime import datetime
import sys


def analyze_timeline(json_path, use_colors=True, prefill_time=375, send_slow_threshold=100, recv_slow_threshold=700, latency_slow_threshold=350):
    """
    Analyze timeline data from JSON file
    
    Args:
        json_path: Path to the JSON file
        use_colors: Whether to use ANSI color codes for output
        prefill_time: Time correction in ms to apply to recv events (default: 375)
        send_slow_threshold: Threshold for slow send events in ms (default: 100)
        recv_slow_threshold: Threshold for slow recv events in ms (default: 700)
        latency_slow_threshold: Threshold for slow latency in ms (default: 350)
    """
    try:
        # Load JSON data
        with open(json_path, "r") as f:
            data = json.load(f)
        timeline = pd.DataFrame(data["merged_timeline"])
    except FileNotFoundError:
        print(f"Error: File '{json_path}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in '{json_path}'.")
        sys.exit(1)
    except KeyError:
        print(f"Error: 'merged_timeline' key not found in JSON data.")
        sys.exit(1)

    # Color codes
    if use_colors:
        RED = "\033[91m"
        GREEN = "\033[92m"
        BLUE = "\033[94m"
        YELLOW = "\033[93m"
        CYAN = "\033[96m"
        RESET = "\033[0m"
    else:
        RED = GREEN = BLUE = YELLOW = CYAN = RESET = ""

    # Create a list to store send events with their cumulative times
    send_events = []
    
    # List to store latency measurements for statistics
    latency_measurements = []
    
    # List to store send event delay measurements for statistics
    send_delay_measurements = []
    
    # List to store recv event delay measurements for statistics
    recv_delay_measurements = []
    
    # Counters for slow events
    send_slow_1_count = 0  # SEND_SLOW_1 count
    send_slow_2_count = 0  # SEND_SLOW_2 count
    recv_slow_count = 0    # RECV_SLOW count
    vc_slow_count = 0      # VC_SLOW count
    
    # Variable to track previous send event timestamp for interval calculation
    previous_send_time = None
    
    # Variable to track previous recv event timestamp for interval calculation
    previous_recv_time = None
    
    # Variable to track previous event type for send slow marking
    previous_event_type = None

    # First pass: collect all send events
    for idx, row in timeline.iterrows():
        if row['event_type'] == 'send':
            send_events.append({
                'cumulative_ms': row['cumulative_ms'],
                'timestamp': row['timestamp']
            })

    # Sort send events by cumulative time
    send_events.sort(key=lambda x: x['cumulative_ms'])

    # Second pass: process and print all events
    for idx, row in timeline.iterrows():
        event_type = row['event_type']
        cumulative_ms = row['cumulative_ms']
        
        # Apply prefill_time correction for recv events
        if event_type == 'recv':
            cumulative_ms = cumulative_ms - prefill_time
        
        if event_type == 'send':
            # Calculate interval from previous send event
            interval_info = ""
            current_send_time = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            
            if previous_send_time is not None:
                interval_ms = (current_send_time - previous_send_time).total_seconds() * 1000
                send_delay_measurements.append(interval_ms)
                
                # Different slow marks based on previous event type
                if interval_ms > send_slow_threshold:
                    if previous_event_type == 'recv':
                        slow_mark = f" {CYAN}[SEND_SLOW_1]{RESET}"
                        send_slow_1_count += 1
                    else:  # previous_event_type == 'send'
                        slow_mark = f" {RED}[SEND_SLOW_2]{RESET}"
                        send_slow_2_count += 1
                else:
                    slow_mark = ""
                
                interval_info = f" | {interval_ms:.0f}ms{slow_mark}"
            else:
                interval_info = f" | first"
            
            # Update previous send time
            previous_send_time = current_send_time
            
            # Default color for send events
            print(f"{row['timestamp']} | {row['event_type']} | {cumulative_ms} | {row['session_id']}{interval_info}")
        elif event_type == 'recv':
            # Calculate interval from previous recv event
            recv_interval_info = ""
            current_recv_time = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
            
            if previous_recv_time is not None:
                recv_interval_ms = (current_recv_time - previous_recv_time).total_seconds() * 1000
                recv_delay_measurements.append(recv_interval_ms)
                if recv_interval_ms > recv_slow_threshold:
                    slow_mark = f" {RED}[RECV_SLOW]{RESET}"
                    recv_slow_count += 1
                else:
                    slow_mark = ""
                recv_interval_info = f" | {GREEN}{recv_interval_ms:.0f}ms{RESET}{slow_mark}"
            else:
                recv_interval_info = f" | {GREEN}first{RESET}"
            
            # Update previous recv time
            previous_recv_time = current_recv_time
            
            # Find the first send event with cumulative_ms >= corrected recv time
            latency_info = ""
            corresponding_send = None
            for send_event in send_events:
                if send_event['cumulative_ms'] >= cumulative_ms:
                    corresponding_send = send_event
                    break
            
            if corresponding_send:
                # Calculate latency using timestamps
                recv_time = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
                send_time = datetime.fromisoformat(corresponding_send['timestamp'].replace('Z', '+00:00'))
                latency_ms = (recv_time - send_time).total_seconds() * 1000
                latency_measurements.append(latency_ms)
                if latency_ms > latency_slow_threshold:
                    slow_mark = f" {RED}[VC_SLOW]{RESET}"
                    vc_slow_count += 1
                else:
                    slow_mark = ""
                latency_info = f" | {GREEN}{latency_ms:.0f}ms{RESET}{slow_mark}"
            
            # Green color for recv events
            print(f"{GREEN}{row['timestamp']} | {row['event_type']} | {cumulative_ms} | {row['session_id']}{RESET}{recv_interval_info}{latency_info}")
        else:
            # Default color for other event types
            print(f"{row['timestamp']} | {row['event_type']} | {cumulative_ms} | {row['session_id']}")
        
        # Update previous event type
        previous_event_type = event_type
    
    # Calculate and display send event delay statistics
    if send_delay_measurements:
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}Send Event Delay Statistics:{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")
        
        # Convert to pandas Series for easier statistics calculation
        send_delay_series = pd.Series(send_delay_measurements)
        
        print(f"{YELLOW}Total measurements: {len(send_delay_measurements)}{RESET}")
        print(f"{YELLOW}Average delay: {send_delay_series.mean():.2f} ms{RESET}")
        print(f"{YELLOW}Median delay: {send_delay_series.median():.2f} ms{RESET}")
        print(f"{YELLOW}Min delay: {send_delay_series.min():.2f} ms{RESET}")
        print(f"{YELLOW}Max delay: {send_delay_series.max():.2f} ms{RESET}")
        print(f"{YELLOW}Standard deviation: {send_delay_series.std():.2f} ms{RESET}")
        
        # Percentiles
        print(f"{YELLOW}P50 (median): {send_delay_series.quantile(0.5):.2f} ms{RESET}")
        print(f"{YELLOW}P90: {send_delay_series.quantile(0.9):.2f} ms{RESET}")
        print(f"{YELLOW}P95: {send_delay_series.quantile(0.95):.2f} ms{RESET}")
        print(f"{YELLOW}P99: {send_delay_series.quantile(0.99):.2f} ms{RESET}")
        
        # Send event delay distribution
        print(f"\n{BLUE}Send Event Delay Distribution:{RESET}")
        bins = [0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 1000, float('inf')]
        labels = ['0-50ms', '50-100ms', '100-200ms', '200-300ms', '300-400ms', 
                  '400-500ms', '500-600ms', '600-700ms', '700-800ms', '800-1000ms', '>1000ms']
        
        for i, (lower, upper) in enumerate(zip(bins[:-1], bins[1:])):
            if upper == float('inf'):
                count = sum(1 for x in send_delay_measurements if x >= lower)
            else:
                count = sum(1 for x in send_delay_measurements if lower <= x < upper)
            percentage = (count / len(send_delay_measurements)) * 100
            print(f"{YELLOW}{labels[i]}: {count} ({percentage:.1f}%){RESET}")
        
        # Send slow events summary
        total_send_events = len(send_delay_measurements)
        send_slow_1_pct = (send_slow_1_count / total_send_events) * 100
        send_slow_2_pct = (send_slow_2_count / total_send_events) * 100
        total_send_slow = send_slow_1_count + send_slow_2_count
        total_send_slow_pct = (total_send_slow / total_send_events) * 100
        
        print(f"\n{BLUE}Send Slow Events Summary:{RESET}")
        print(f"{YELLOW}[SEND_SLOW_1] (After RECV): {send_slow_1_count} ({send_slow_1_pct:.1f}%){RESET}")
        print(f"{RED}[SEND_SLOW_2] (After SEND): {send_slow_2_count} ({send_slow_2_pct:.1f}%){RESET}")
        print(f"{YELLOW}[SEND_SLOW_TOTAL]: {total_send_slow} ({total_send_slow_pct:.1f}%){RESET}")
        
        print(f"{BLUE}{'='*60}{RESET}")
    else:
        print(f"\n{YELLOW}No send event delay measurements found{RESET}")
    
    # Calculate and display recv event delay statistics
    if recv_delay_measurements:
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}Recv Event Delay Statistics:{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")
        
        # Convert to pandas Series for easier statistics calculation
        recv_delay_series = pd.Series(recv_delay_measurements)
        
        print(f"{YELLOW}Total measurements: {len(recv_delay_measurements)}{RESET}")
        print(f"{YELLOW}Average delay: {recv_delay_series.mean():.2f} ms{RESET}")
        print(f"{YELLOW}Median delay: {recv_delay_series.median():.2f} ms{RESET}")
        print(f"{YELLOW}Min delay: {recv_delay_series.min():.2f} ms{RESET}")
        print(f"{YELLOW}Max delay: {recv_delay_series.max():.2f} ms{RESET}")
        print(f"{YELLOW}Standard deviation: {recv_delay_series.std():.2f} ms{RESET}")
        
        # Percentiles
        print(f"{YELLOW}P50 (median): {recv_delay_series.quantile(0.5):.2f} ms{RESET}")
        print(f"{YELLOW}P90: {recv_delay_series.quantile(0.9):.2f} ms{RESET}")
        print(f"{YELLOW}P95: {recv_delay_series.quantile(0.95):.2f} ms{RESET}")
        print(f"{YELLOW}P99: {recv_delay_series.quantile(0.99):.2f} ms{RESET}")
        
        # Recv event delay distribution
        print(f"\n{BLUE}Recv Event Delay Distribution:{RESET}")
        bins = [0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 1000, float('inf')]
        labels = ['0-50ms', '50-100ms', '100-200ms', '200-300ms', '300-400ms', 
                  '400-500ms', '500-600ms', '600-700ms', '700-800ms', '800-1000ms', '>1000ms']
        
        for i, (lower, upper) in enumerate(zip(bins[:-1], bins[1:])):
            if upper == float('inf'):
                count = sum(1 for x in recv_delay_measurements if x >= lower)
            else:
                count = sum(1 for x in recv_delay_measurements if lower <= x < upper)
            percentage = (count / len(recv_delay_measurements)) * 100
            print(f"{YELLOW}{labels[i]}: {count} ({percentage:.1f}%){RESET}")
        
        # Recv slow events summary
        total_recv_events = len(recv_delay_measurements)
        recv_slow_pct = (recv_slow_count / total_recv_events) * 100
        
        print(f"\n{BLUE}Recv Slow Events Summary:{RESET}")
        print(f"{RED}[RECV_SLOW]: {recv_slow_count} ({recv_slow_pct:.1f}%){RESET}")
        
        print(f"{BLUE}{'='*60}{RESET}")
    else:
        print(f"\n{YELLOW}No recv event delay measurements found{RESET}")

    # Calculate and display latency statistics
    if latency_measurements:
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}Latency Statistics:{RESET}")
        print(f"{BLUE}{'='*60}{RESET}")
        
        # Convert to pandas Series for easier statistics calculation
        latency_series = pd.Series(latency_measurements)
        
        print(f"{YELLOW}Total measurements: {len(latency_measurements)}{RESET}")
        print(f"{YELLOW}Average latency: {latency_series.mean():.2f} ms{RESET}")
        print(f"{YELLOW}Median latency: {latency_series.median():.2f} ms{RESET}")
        print(f"{YELLOW}Min latency: {latency_series.min():.2f} ms{RESET}")
        print(f"{YELLOW}Max latency: {latency_series.max():.2f} ms{RESET}")
        print(f"{YELLOW}Standard deviation: {latency_series.std():.2f} ms{RESET}")
        
        # Percentiles
        print(f"{YELLOW}P50 (median): {latency_series.quantile(0.5):.2f} ms{RESET}")
        print(f"{YELLOW}P90: {latency_series.quantile(0.9):.2f} ms{RESET}")
        print(f"{YELLOW}P95: {latency_series.quantile(0.95):.2f} ms{RESET}")
        print(f"{YELLOW}P99: {latency_series.quantile(0.99):.2f} ms{RESET}")
        
        # Latency distribution
        print(f"\n{BLUE}Latency Distribution:{RESET}")
        bins = [0, 50, 100, 200, 300, 400, 500, 600, 700, 800, 1000, float('inf')]
        labels = ['0-50ms', '50-100ms', '100-200ms', '200-300ms', '300-400ms', 
                  '400-500ms', '500-600ms', '600-700ms', '700-800ms', '800-1000ms', '>1000ms']
        
        for i, (lower, upper) in enumerate(zip(bins[:-1], bins[1:])):
            if upper == float('inf'):
                count = sum(1 for x in latency_measurements if x >= lower)
            else:
                count = sum(1 for x in latency_measurements if lower <= x < upper)
            percentage = (count / len(latency_measurements)) * 100
            print(f"{YELLOW}{labels[i]}: {count} ({percentage:.1f}%){RESET}")
        
        # VC slow events summary
        total_latency_events = len(latency_measurements)
        vc_slow_pct = (vc_slow_count / total_latency_events) * 100
        
        print(f"\n{BLUE}Latency Slow Events Summary:{RESET}")
        print(f"{RED}[VC_SLOW]: {vc_slow_count} ({vc_slow_pct:.1f}%){RESET}")
        
        print(f"{BLUE}{'='*60}{RESET}")
    else:
        print(f"\n{YELLOW}No latency measurements found (no recv events with corresponding send events){RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze timeline JSON data with send/recv events and calculate latency"
    )
    parser.add_argument(
        "json_path", 
        help="Path to the JSON file containing timeline data"
    )
    parser.add_argument(
        "--no-color", 
        action="store_true", 
        help="Disable colored output"
    )
    parser.add_argument(
        "--prefill-time", 
        type=float,
        default=375,
        help="Prefill time correction in ms to apply to recv events (default: 375)"
    )
    parser.add_argument(
        "--send-slow-threshold", 
        type=float,
        default=100,
        help="Threshold for slow send events in ms (default: 100)"
    )
    parser.add_argument(
        "--recv-slow-threshold", 
        type=float,
        default=700,
        help="Threshold for slow recv events in ms (default: 700)"
    )
    parser.add_argument(
        "--latency-slow-threshold", 
        type=float,
        default=350,
        help="Threshold for slow latency in ms (default: 350)"
    )
    
    args = parser.parse_args()
    
    # Use colors unless --no-color is specified
    use_colors = not args.no_color
    
    analyze_timeline(args.json_path, use_colors, args.prefill_time, args.send_slow_threshold, args.recv_slow_threshold, args.latency_slow_threshold)


if __name__ == "__main__":
    """
    example usage:
        python timeline_lognize.py path/to/timeline.json > output.txt
        python timeline_lognize.py path/to/timeline.json --no-color
        python timeline_lognize.py path/to/timeline.json --prefill-time 375
        python timeline_lognize.py path/to/timeline.json --send-slow-threshold 100 --recv-slow-threshold 700 --latency-slow-threshold 350
    """
    main()