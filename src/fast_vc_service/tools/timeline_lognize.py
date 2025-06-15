"""
Timeline Analyzer - Analyze send/recv events with latency calculation
"""

import pandas as pd
import json
import argparse
from datetime import datetime
import sys


def analyze_timeline(json_path, use_colors=True, prefill_time=375):
    """
    Analyze timeline data from JSON file
    
    Args:
        json_path: Path to the JSON file
        use_colors: Whether to use ANSI color codes for output
        prefill_time: Time correction in ms to apply to recv events (default: 375)
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
        RESET = "\033[0m"
    else:
        RED = GREEN = BLUE = YELLOW = RESET = ""

    # Create a list to store send events with their cumulative times
    send_events = []
    
    # List to store latency measurements for statistics
    latency_measurements = []

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
            # Red color for send events
            print(f"{RED}{row['timestamp']} | {row['event_type']} | {cumulative_ms} | {row['session_id']}{RESET}")
        elif event_type == 'recv':
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
                latency_info = f" | {GREEN}{latency_ms:.0f}ms{RESET}"
            
            # Green color for recv events
            print(f"{GREEN}{row['timestamp']} | {row['event_type']} | {cumulative_ms} | {row['session_id']}{RESET}{latency_info}")
        else:
            # Default color for other event types
            print(f"{row['timestamp']} | {row['event_type']} | {cumulative_ms} | {row['session_id']}")
    
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
        bins = [0, 50, 100, 200, 500, 1000, float('inf')]
        labels = ['0-50ms', '50-100ms', '100-200ms', '200-500ms', '500-1000ms', '>1000ms']
        
        for i, (lower, upper) in enumerate(zip(bins[:-1], bins[1:])):
            if upper == float('inf'):
                count = sum(1 for x in latency_measurements if x >= lower)
            else:
                count = sum(1 for x in latency_measurements if lower <= x < upper)
            percentage = (count / len(latency_measurements)) * 100
            print(f"{YELLOW}{labels[i]}: {count} ({percentage:.1f}%){RESET}")
        
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
    
    args = parser.parse_args()
    
    # Use colors unless --no-color is specified
    use_colors = not args.no_color
    
    analyze_timeline(args.json_path, use_colors, args.prefill_time)


if __name__ == "__main__":
    """
    example usage:
        python timeline_lognize.py path/to/timeline.json --prefill-time 375
    """
    main()