<p align="center">
    <img src="https://raw.githubusercontent.com/Leroll/fast-vc-service/main/asserts/cover.PNG" alt="repo cover" width=80%>
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
  <h3>基于 Seed-VC 的实时语音转换服务，提供 WebSocket 接口，支持 PCM 和 Opus 音频格式</h3>
</div> 

<div align="center">
  <a href="README.md">English</a> | 简体中文
</div>
<br>

> 功能持续迭代更新中。欢迎关注我们的最新进展... ✨

Fast-VC-Service 旨在打造一款专为生产环境设计的，高性能实时流式语音转换云服务。基于 Seed-VC 模型实现，支持 WebSocket 协议，PCM与OPUS音频编码类型。

<div align="center">

[核心特性](#-核心特性) | [快速开始](#-快速开始) | [性能表现](#-性能表现) | [版本更新](#-版本更新) | [TODO](#-TODO) | [致谢](#-致谢)

</div>

# ✨ 核心特性

- **实时转换**: 基于 Seed-VC 的低延迟流式语音转换
- **WebSocket API**: 支持 PCM 和 OPUS 音频格式
- **性能监控**: 完整的实时性能指标统计
- **高并发**: 多Worker并发处理，支持生产环境
- **易部署**: 简单配置，一键启动


# 🚀 快速开始 

## 📦 一键安装
```bash
# 克隆项目
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service

# 配置环境
cp .env.example .env

# 安装依赖（推荐使用 Poetry）
poetry install

# 启动服务
fast-vc serve
```

## 🧪 快速测试
```bash
# WebSocket 实时语音转换
python examples/websocket/ws_client.py \
    --source-wav-path "wavs/sources/low-pitched-male-24k.wav" \
    --encoding PCM
```

> 详细安装使用指南请参看 [快速开始](docs/getting_started/quick_started.md) 文档。


# 📈 性能表现 

<div align="center">

| GPU | 并发| Worker | 音频块时长 | 首token延迟 | 端到端延迟 | 平均chunk延迟 | 平均RTF | 中位数RTF | P95 RTF |
|-----|----|--------|----------|-------------|----------|-------------|---------|----------|---------|
|4090D  |1  |6      |500       |136.0        |143.0     |105.0        |0.21     |0.22      |0.24     |
|4090D  |12 |12     |500       |140.1        |256.6     |216.6        |0.44     |0.45      |0.51     |
|1080TI |1  |6      |500       |157.0        |272.0     |252.2        |0.50     |0.51      |0.61     |
|1080TI |3  |6      |500       |154.3        |261.3     |304.9        |0.61     |0.62      |0.73     |

</div>

- 时间单位为: 毫秒(ms)
- 查看详细的测试报告: 
    - [性能测试报告_4090D](docs/perfermance_tests/version0.1.0_4090D.md)
    - [性能测试报告_1080ti](docs/perfermance_tests/version0.1.0_1080ti.md)


# 📝 版本更新 
<!-- don't forget to change version in __init__ and toml -->

**2025-06-19 - v0.1.1**: 首包性能优化   

  - 新增查询性能监控接口 /tools/performance-report，支持查询实时性能指标
  - 细化耗时日志，便于分析性能瓶颈
  - 缓解人声首包调用模型导致的延迟问题

**2025-06-15 - v0.1.0**: 基础服务框架   

  完成了基于 Seed-VC 的实时语音转换服务的核心框架搭建，实现了 WebSocket 流式推理、性能监控、多格式音频支持等完整的基础功能。   

  - 实时流式语音转换服务
  - WebSocket API 支持 PCM 和 Opus 格式
  - 完整的性能监控和统计系统
  - 灵活的配置管理和环境变量支持 
  - 多Worker并发处理能力
  - 并发性能测试框架

# 🚧 TODO 
- [ ] tag - v0.1.2 - 添加流式场景下，音高自适应提取功能 -  v2025-06-26
    - [ ] vad 改用 onnx, 以提升推理速度； 同时对比 vad onnx放在cpu和gpu推理，对整体性能和并发的影响
    - [ ] 增加音高自适应提取功能，并添加对应开关
    - [ ] 完成对seed-vc V2.0 模型支持
    - [ ] 制作镜像，方便部署
- [ ] tag - v0.2 - 提升推理时效，降低RTF - v2025-xx
    - [ ] 探索降低模型推理时延的方案（比如新的模型架构、量化等）
    - [ ] reference 使用torchaudio 直接读取到GPU中，省去转移的步骤。
    - [ ] file_vc，针对最后一个block的问题
    - [ ] 制作AutoDL镜像

# 🙏 致谢 
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - 提供了强大的底层变声模型
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - 提供了基础的流式语音转换pipeline