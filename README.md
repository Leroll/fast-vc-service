<p align="center">
    <img src="https://raw.githubusercontent.com/Leroll/fast-vc-service/main/asserts/cover.PNG" alt="repo cover" width=80%>
</p>

<div align="center">
  <img alt="GitHub stars" src="https://img.shields.io/github/stars/Leroll/fast-vc-service?style=social">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-blue.svg">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8+-blue.svg">
</div>

<div align="center">
  <h3>Industrial-grade streaming voice conversion service designed for cloud deployment, from Git repository to private API platform</h3>
</div> 

<div align="center">
  English | <a href="README_ZH.md">简体中文</a>
</div>
<br>

> Features are continuously being updated. Stay tuned for our latest developments... ✨

# 🚀 Quick Start

## Environment Setup
```bash
git clone https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
pip install -r requirements.txt
cp .env.example .env  # Optional: Edit configuration parameters
```

## Start Service
```bash
./scripts/start.sh     # 🟢 Start service
./scripts/shutdown.sh  # 🔴 Stop service
```

# 📡 Real-time Streaming Voice Conversion

## WebSocket Connection Flow
```mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    
    C->>S: Configuration request
    S->>C: Ready confirmation ✅
    
    loop Real-time audio stream
        C->>S: 🎤 Audio chunk
        S->>C: 🔊 Converted audio
    end
    
    C->>S: End signal
    S->>C: Completion status ✨
```

**For detailed WebSocket API specification, please refer to**: [WebSocket API Specification](docs/%E6%8E%A5%E5%8F%A3%E6%96%87%E6%A1%A3/WebSocket%20API%E8%A7%84%E8%8C%83.md)  
**Supported Formats**: PCM | OPUS  

## 🔥 Quick Test

### WebSocket Real-time Conversion
```bash
python client/ws_client.py \
    --source-wav-path "input.wav" \
    --encoding OPUS
```

### Batch File Testing
```bash
python client/file_vc.py \
    --source-wav-path "input1.wav input2.wav" \
    --reference-wav-path ""wavs/references/ref.wav"" \
    --block-time 0.5 \
    --diffusion-steps 10
```


# 🚧 Under Construction...TODO
- [ ] tag - v0.1 - Basic Service - v2025-xx
    - [x] Complete initial version of streaming inference code
    - [x] Add .env for storing source and related variables
    - [x] Split streaming inference modules
    - [x] Add performance tracking statistics module
    - [x] Add opus encoding/decoding module
    - [x] Add asgi app service and log system, resolve conflicts between uvicorn and loguru
    - [x] Convert output to 16k before outputting, using slice assignment
    - [x] Add session class for context storage during streaming inference
    - [x] Clean up redundant code, remove unnecessary logic
    - [x] Complete pipeline reconstruction of each module
    - [x] Complete session replacement improvements
    - [ ] Add configuration information
    - [x] Improve log system
    - [x] Complete WS service code + PCM
    - [x] Complete WS + Opus
    - [ ] Add a setting for the audio sample rate in the WebSocket client.
    - [x] Add WebSocket support description to the README, then draw a process flowchart.
    - [ ] Support webRTC
    - [ ] Crop cover image
    - [ ] Fix file_vc for the last block issue
    - [ ] Handle exceptional cases, e.g., when a chunk converts with rta>1, what processing solutions exist?
    - [ ] ✨Optimizing Package Management for Better Usability and Stability
- [ ] tag - v0.2 - Audio Quality - v2025-xx
    - [ ] Investigate chunk size issue in infer_wav, 8781 after vcmodel, 9120 without it [sola module record]
    - [ ] Investigate potential sound jitter issues
    - [ ] Add pitch extraction functionality in streaming scenarios for male deep voice conversion issues
    - [ ] Complete support for seed-vc V2.0 model
- [ ] tag - v0.3 - Service Flexibility and Stability - v2025-xx
    - [ ] Use torchaudio to read references directly to GPU, saving transfer steps
    - [ ] Configure startup of different model instances as different microservices
    - [ ] Create AutoDL image for one-click deployment
    - [ ] Add encrypted wav return for GET requests
    - [ ] add support for wss
    - [ ] Implement JWT token-based authentication

# 🙏 Acknowledgements
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - Provides powerful underlying voice conversion model
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - Provides basic streaming voice conversion pipeline