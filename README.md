<p align="center">
    <img src="https://raw.githubusercontent.com/Leroll/fast-vc-service/main/assets/cover.PNG" alt="repo cover" width=80%>
</p>

<div align="center">
  <img alt="GitHub stars" src="https://img.shields.io/github/stars/Leroll/fast-vc-service?style=social">
  <img alt="Github downloads" src="https://img.shields.io/github/downloads/Leroll/fast-vc-service/total?style=flat-square">
  <img alt="GitHub release" src="https://img.shields.io/github/v/release/Leroll/fast-vc-service?style=flat-square">
  <a href="https://github.com/Leroll/fast-vc-service/commits/main">
    <img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/Leroll/fast-vc-service">
  </a>
  <img alt="License" src="https://img.shields.io/badge/License-GPL%20v3-blue.svg">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10+-blue.svg">
</div>

<div align="center">
  <h3>Real-time voice conversion service based on Seed-VC, providing WebSocket voice conversion with PCM and Opus audio format support</h3>
</div> 

<div align="center">
  English | <a href="README_ZH.md">简体中文</a>
</div>
<br>

> Features are continuously being updated. Stay tuned for our latest developments... ✨

Fast-VC-Service aims to build a high-performance real-time streaming voice conversion cloud service designed for production environments. Based on the Seed-VC model, it supports WebSocket protocol and PCM/OPUS audio encoding formats.

<div align="center">

[Core Features](#-core-features) | [Quick Start](#-quick-start) | [Performance](#-performance) | [Version Updates](#-version-updates) | [TODO](#-todo) | [Acknowledgements](#-acknowledgements)

</div>

# ✨ Core Features

- **Real-time Conversion**: Low-latency streaming voice conversion based on Seed-VC
- **WebSocket API**: Support for PCM and OPUS audio formats
- **Performance Monitoring**: Complete real-time performance metrics statistics
- **High Concurrency**: Multi-Worker concurrent processing, supporting production environments
- **Easy Deployment**: Simple configuration, one-click startup


# 🚀 Quick Start

## 📦 One-click Installation
```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 opus-tools

# Clone project
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service

# Configure environment
cp .env.example .env

# Install dependencies (using uv)
uv sync

# Start service
fast-vc serve
```

## 🧪 Quick Testing
```bash
# WebSocket real-time voice conversion
python examples/websocket/ws_client.py \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
    --encoding PCM
```

> For detailed installation and usage guide, please refer to [Quick Start](docs/getting_started/quick_started_en.md) documentation.



# 📈 Performance

<div align="center">

|GPU |Concurrency |Worker |Chunk time |First Token Latency |End-to-End Latency |Avg Chunk Latency |Avg RTF | Median RTF | P95 RTF |
|-----|----|--------|----------|-------------|----------|-------------|---------|----------|---------|
|4090D  |1  |6      |500       |136.0        |143.0     |105.0        |0.21     |0.22      |0.24     |
|4090D  |12 |12     |500       |140.1        |256.6     |216.6        |0.44     |0.45      |0.51     |
|1080TI |1  |6      |500       |157.0        |272.0     |252.2        |0.50     |0.51      |0.61     |
|1080TI |3  |6      |500       |154.3        |261.3     |304.9        |0.61     |0.62      |0.73     |

</div>

- Time unit: milliseconds (ms)
- View detailed test report: 
    - [Performance-Report_4090D](docs/perfermance_tests/version0.1.0_4090D.md)
    - [Performance-Report_1080ti](docs/perfermance_tests/version0.1.0_1080ti.md)


# 📝 Version Updates
<!-- don't forget to change version in __init__ and toml -->

**2025-07-24 - v0.1.5**: Pitch Adaptive Matching Support and Real-time Monitoring Optimization

  - Real-time monitoring optimization:
    - Optimized timeline_lognize, added delay items statistics for same event types
    - Added SLOW tags to logs for monitoring receive intervals, send intervals, and VC-E2E latency
  - Support for pitch adaptive matching with reference audio to improve conversion quality
    - Added pitch analysis script providing audio analysis tools
    - Added pitch adaptive matching functionality with corresponding toggle configuration
  - Other optimizations
    - Changed UID generation method to time-based generation for easier experimentation and testing
    - Optimized session tool's file naming mechanism
    - Added config and model path options, support NAS configuration files, enable simpler cloud host deployment

**2025-07-02 - v0.1.3**: Added Process and Instance Level Concurrency Monitoring  

  - Added PID record to logs for easier instance tracking
  - Added instance concurrency monitoring feature for real-time concurrency viewing
  - Optimized performance analysis interface to reduce impact on real-time performance

**2025-06-26 - v0.1.2**: Persistent Storage Optimization   

  - Optimized session persistent storage module with asynchronous processing
  - Separated time-consuming timeline statistical analysis module to improve response speed
  - Optimized timeline recording mechanism to reduce storage overhead


<details>
<summary>View Historical Versions</summary>

**2025-06-19 - v0.1.1**: First Packet Performance Optimization   

  - Added performance monitoring API endpoint /tools/performance-report for real-time performance metrics
  - Enhanced timing logs for better performance bottleneck analysis
  - Mitigated delay issue caused by first audio packet model invocation

**2025-06-15 - v0.1.0**: Basic Service Framework   

  Completed the core framework construction of real-time voice conversion service based on Seed-VC, implementing WebSocket streaming inference, performance monitoring, multi-format audio support and other complete basic functions.   

  - Real-time streaming voice conversion service
  - WebSocket API support for PCM and Opus formats
  - Complete performance monitoring and statistics system
  - Flexible configuration management and environment variable support 
  - Multi-Worker concurrent processing capability
  - Concurrent performance testing framework
  
</details>



# 🚧 TODO
- [ ] tag - v0.2 - Improve inference efficiency, reduce RTF - v2025-xx
    - [x] Switch project management to uv
    - [x] Fix send_slow false delay Warning
    - [x] Add VC evaluation tool tools/eval.py
    - [x] Allow multiple instances to start simultaneously with different configuration files on different ports
    - [x] Support custom model address configuration
    - [x] Support multi-GPU multi-instance deployment
    - [x] Optimize VAD model parameters for better noise filtering
    - [x] Add semantic feature retrieval module to enhance voice similarity
    - [ ] Train models to optimize voice conversion quality
    - [ ] Improve model effectiveness for noisy data
        - Distinguish different noise types
    - [ ] Server send/recv event definitions should match roles
    - [ ] Model acceleration optimization:
        - [ ] Change VAD to use ONNX-GPU to improve inference speed
        - [ ] Explore solutions to reduce model inference latency (e.g., new model architectures, quantization, etc.)
    - [ ] Create Docker image and AutoDL image for one-click deployment

# 🙏 Acknowledgements
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - Provides powerful underlying voice conversion model
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - Provides basic streaming voice conversion pipeline