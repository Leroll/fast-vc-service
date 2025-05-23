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

# 🛠️ Installation
```
# Clone the repository
git clone https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (optional)
cp .env.example .env
# Edit the .env file to configure relevant parameters
```

# 🔧 Usage
**1. Batch audio file streaming voice conversion, used for streaming effect testing**
```
python file_vc.py --reference_audio_path "wavs/references/your_ref.wav" \
                 --wav_files "input1.wav input2.wav" \
                 --block_time 0.5 \
                 --diffusion_steps 10 \
                 --rms_mix_rate 0.8
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
    - [ ] Complete WS service code
    - [ ] Support webRTC
    - [ ] Crop cover image
    - [ ] Fix file_vc for the last block issue
    - [ ] Handle exceptional cases, e.g., when a chunk converts with rta>1, what processing solutions exist?
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

# 🙏 Acknowledgements
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - Provides powerful underlying voice conversion model
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - Provides basic streaming voice conversion pipeline