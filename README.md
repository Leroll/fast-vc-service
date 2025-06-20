<p align="center">
    <img src="https://raw.githubusercontent.com/Leroll/fast-vc-service/main/asserts/cover.PNG" alt="repo cover" width=80%>
</p>

<div align="center">
  <img alt="GitHub stars" src="https://img.shields.io/github/stars/Leroll/fast-vc-service?style=social">
  <img alt="Github downloads" src="https://img.shields.io/github/downloads/Leroll/fast-vc-service/total?style=flat-square">
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
# Clone project
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service

# Configure environment
cp .env.example .env

# Install dependencies (Poetry recommended)
poetry install

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

# 🚧 TODO
- [ ] tag - v0.1.2 - Add adaptive pitch extraction in streaming scenarios - v2025-06-26
    - [ ] Change VAD to use ONNX-GPU to improve inference speed
    - [ ] Add adaptive pitch extraction functionality with corresponding toggle switch
    - [ ] Complete support for seed-vc V2.0 model
- [ ] tag - v0.2 - Improve inference efficiency, reduce RTF - v2025-xx
    - [ ] Explore solutions to reduce model inference latency (e.g., new model architectures, quantization, etc.)
    - [ ] Use torchaudio to directly read reference audio to GPU, eliminating transfer steps
    - [ ] Fix file_vc issue with the last block
    - [ ] Create Docker images for easy deployment
    - [ ] Create AutoDL images

# 🙏 Acknowledgements
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - Provides powerful underlying voice conversion model
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - Provides basic streaming voice conversion pipeline