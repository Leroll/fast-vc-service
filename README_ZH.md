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
# 安装系统依赖（Ubuntu/Debian）
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 opus-tools

# 克隆项目
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service

# 配置环境
cp .env.example .env

# 安装依赖（使用 uv）
uv sync

# 启动服务
uv run fast-vc serve
```

## 🧪 快速测试
```bash
# WebSocket 实时语音转换
uv run examples/websocket/ws_client.py 
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

**2025-10-16 - v0.1.6**: 多卡多实例部署，语义特征检索，uv包管理

  - 部署与并发
    - 支持自定义模型与配置文件路径，支持多实例部署，按配置与端口隔离
    - 支持单实例多卡部署，提升并发处理能力
  - 质量与效果
    - 新增语义特征检索模块，提升音色相似度与鲁棒性
    - 优化 VAD 参数，降低噪声与静音误触发
  - 工程化
    - 包管理迁移至 uv，安装与启动更快
    - 修复 send_slow 假延迟告警问题
    - 新增 VC 效果评测工具 tools/eval.py

**2025-07-24 - v0.1.5**: 支持音高自适应匹配与实时性监控优化

  - 实时性监控优化:
    - 优化timeline_lognize，添加同类event延迟项统计
    - 日志新增SLOW标签，针对收包间隔、发包间隔以及VC-E2E耗时进行标记
  - 支持音高自适应匹配参考音频，提升转换效果
    - 新增音高分析脚本，提供音频分析工具
    - 增加音高自适应匹配功能，并添加对应开关配置
  - 其他优化
    - 更改uid生成方式，改为基于时间的生成方式，便于实验与测试
    - 优化session tool的文件命名机制
    - 增加config与model路径选项，支持nas配置文件，支持更简洁的云主机部署

**2025-07-02 - v0.1.3**: 增加进程与实例级别并发监控  

  - 日志新增PID记录，便于追踪实例
  - 增加实例并发监控功能，支持实时查看当前并发量
  - 优化性能分析接口，减少对实时性的影响


<details>
<summary>查看历史版本</summary>

**2025-06-26 - v0.1.2**: 持久化存储优化   

  - 优化session持久化存储模块，改为异步处理
  - 分离耗时的时间线统计分析模块，提升响应速度
  - 优化时间线记录机制，减少存储开销

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
  
</details>



# 🚧 TODO 
- [ ] tag - v0.2 - 提升推理时效，降低RTF - v2025-xx
    - [x] 新增t_span_schedule参数，支持余弦重排，同样的步数可以有更好的音质表现
    - [x] 删除realtimevc中的性能追踪模块，删除file-vc脚本, 删除噪声门模块，减轻代码冗余程度
    - [x] vad 配置增加到配置文件中
    - [x] 各模块的 time_records 转移到 session 中统一管理
    - [x] realtime_vc输出固定为模型采样率（22k），以保证更高输出音质。
    - [x] 静音过长时，保留足够有声上文，以提升合成效果
    - [x] 修复上游意外断联而导致的音频无法正常存储的bug
    - [x] websocket协议新增输出采样率参数，据此输出对应采样率音频
    - [ ] 兼容 fp16 推理模式
    - [ ] 更新文档，以适应最新的代码
    - [ ] 训练模型，优化换声品质
    - [ ] 提升针对噪声数据的模型效果
        - 区分不同的噪声类型
    - [ ] 服务器的send recv 等事件定义应该符合角色
    - [ ] 模型加速优化: 
        - [ ] vad 改用 onnx-gpu, 以提升推理速度
        - [ ] 探索降低模型推理时延的方案（比如新的模型架构、量化等）
    - [ ] 制作镜像，以及AutoDL镜像，一键可用。


# 🙏 致谢 
- [Seed-VC](https://github.com/Plachtaa/seed-vc) - 提供了强大的底层变声模型
- [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) - 提供了基础的流式语音转换pipeline
