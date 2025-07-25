# Quick Start

## Installation

### Using uv (Recommended)
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 opus-tools

# Clone project
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
cp .env.example .env  # Configure environment variables

# Install uv (if not already installed)
pip install uv

# Sync dependencies and create virtual environment
uv sync
```

When running for the first time, models will be automatically downloaded to the model path configured in .env (default checkpoints).  
If you encounter network issues, you can uncomment the `HF_ENDPOINT` variable in the `.env` file to use domestic mirror sources for accelerated model downloads.

### Method 2: Using Poetry
```bash
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
cp .env.example .env  # Configure environment variables
poetry install  # Install dependencies
```

### Method 3: Using Existing Conda Environment
```bash
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
cp .env.example .env  # Configure environment variables

# Activate existing conda environment (Python 3.10+)
conda activate your_env_name

# Use Poetry (disable virtual environment)
poetry config virtualenvs.create false
poetry install
```

### Replace Poetry Source (if needed)
```
poetry source remove aliyun
poetry source add new_name https://xx/pypi/simple --priority=primary
rm poetry.lock  # Delete lock file and regenerate
poetry lock 
poetry install  
```

## Start Service
```bash
# Start service
fast-vc serve  # Default startup using env_profile in .env
nohup fast-vc serve > /dev/null 2>&1 &  # Run service in background

# Using uv
uv run fast-vc serve
```

<!-- Add service startup demonstration -->
<p align="center">
    <img src="https://github.com/Leroll/fast-vc-service/releases/download/v0.0.1/fast-vc-serve.gif" alt="Service Startup Demo" width="800">
    <br>
    <em>🚀 Service Startup Process</em>
</p>

## Service Management
```bash
# Check service status
fast-vc status

# Stop service (graceful shutdown)
fast-vc stop
fast-vc stop --force   # Force stop

# Clean log files
fast-vc clean
fast-vc clean -y  # Skip confirmation

# View version information
fast-vc version
```

### Service Management Description
- `serve`: Start FastAPI server
- `status`: Check service running status and process information
- `stop`: Gracefully shutdown service (send SIGINT signal)
- `stop --force`: Force shutdown service (send SIGTERM signal)
- `clean`: Clean log files in logs/ directory
- `clean -y`: Clean log files, skip confirmation prompt
- `version`: Display service version information

Service information is automatically saved to the project's `temp/` directory, supporting process status checking and automatic cleanup.

<p align="center">
    <img src="https://github.com/Leroll/fast-vc-service/releases/download/v0.0.1/fast-vc-command.gif" alt="Command Demo" width="800">
    <br>
    <em>🚀 Command Demonstration</em>
</p>

# Quick Testing

**For detailed WebSocket API specifications, please refer to**: [WebSocket API Specification](docs/api_docs/websocket-api-doc.md)  
**Supported Formats**: PCM | OPUS  

## WebSocket Real-time Voice Conversion
```bash
python examples/websocket/ws_client.py \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
    --encoding OPUS
```

## Batch File Testing (for validating voice conversion effects, no need to start service)
```bash
python examples/file_conversion/file_vc.py \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
```

## Concurrent Performance Testing

### Multi-client Concurrent Testing
Use concurrent WebSocket clients to test server processing capabilities:

```bash
# Start 5 concurrent clients, begin simultaneously with no delay
python examples/websocket/concurrent_ws_client.py \
    --num-clients 5 \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
    --encoding OPUS

# Start 10 clients, launching one every 2 seconds
python examples/websocket/concurrent_ws_client.py \
    --num-clients 10 \
    --delay-between-starts 2.0 \
    --max-workers 4 \
    --timeout 600

# Test different audio formats
python examples/websocket/concurrent_ws_client.py \
    --num-clients 3 \
    --encoding PCM \
    --chunk-time 40 \
    --real-time
```

### Test Parameter Description
- `--num-clients`: Number of concurrent clients (default: 5)
- `--delay-between-starts`: Client startup interval in seconds (default: 0.0, start simultaneously)
- `--max-workers`: Maximum worker processes (default: min(8, num_clients))
- `--timeout`: Single client timeout in seconds (default: 420)
- `--chunk-time`: Audio chunk time in milliseconds (default: 20ms)
- `--encoding`: Audio encoding format, PCM or OPUS (default: PCM)
- `--real-time`: Enable real-time audio sending simulation
- `--no-real-time`: Disable real-time simulation, send as fast as possible

### Performance Metrics Analysis

After testing completes, a detailed performance analysis report is automatically generated, including:

#### 🕐 Latency Metrics
- **First Token Latency**: Processing latency of the first audio packet
- **End-to-End Latency**: Complete audio stream processing latency
- **Chunk Latency Statistics**: Latency distribution for each audio chunk (mean, median, P95, P99, etc.)
- **Latency Jitter**: Standard deviation of latency, measuring latency stability

#### ⚡ Real-time Metrics
- **Real-time Factor (RTF)**: Ratio of processing time/audio duration
  - RTF < 1.0: Meets real-time processing requirements
  - RTF > 1.0: Processing speed cannot keep up with audio playback speed
- **RTF Statistics**: Includes mean, median, P95, P99 and other distribution information

#### 📊 Send Timing Analysis
- **Send Latency Statistics**: Actual send interval vs expected audio interval
- **Timing Quality Assessment**: Send stability and continuous latency detection

#### 📈 Example Output
```json
{
  "first_token_latency_ms": 285.3,
  "end_to_end_latency_ms": 1247.8,
  "chunk_latency_stats": {
    "mean_ms": 312.5,
    "median_ms": 298.1,
    "p95_ms": 456.7,
    "p99_ms": 523.2
  },
  "real_time_factor": {
    "mean": 0.87,
    "median": 0.85,
    "p95": 1.12
  },
  "is_real_time": true,
  "timeline_summary": {
    "total_send_events": 156,
    "total_recv_events": 148,
    "send_duration_ms": 3120,
    "processing_start_to_end_ms": 3368
  }
}
```

### Result Files Description
After testing completes, the following files will be generated in the `outputs/concurrent_ws_client/` directory:
- `clientX_result.json`: Complete result data for each client
- `clientX_stats.json`: Performance statistics analysis for each client
- `clientX_output.wav`: Converted audio file (if saving is