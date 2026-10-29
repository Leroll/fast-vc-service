<p align="center">
  <img src="assets/cover.PNG" alt="Fast-VC：实时流式语音转换服务" width="80%">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL%20v3-blue.svg" alt="GPL v3"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <a href="https://github.com/Leroll/fast-vc-service/releases"><img src="https://img.shields.io/github/v/release/Leroll/fast-vc-service" alt="GitHub release"></a>
</p>

基于 Seed-VC 的实时流式语音转换服务，通过 WebSocket 将音色转换能力接入语音应用，提供音频缓冲、会话管理和多 Worker 部署支持。

[English](README.md) · 简体中文 · [快速开始](docs/getting_started/quick_started_zh.md) · [API](docs/api_docs/websocket-api-doc.md) · [全部文档](docs/README.md)

## 1. 项目用途与核心能力

Fast-VC 面向希望把持续输入的语音转换为指定参考音色、再接回语音应用的开发者。它在 Seed-VC 推理能力之上提供服务接口和流式处理流程。

- **持续收发音频**：通过 WebSocket 边发送边接收，支持标准协议和简单协议。
- **音频格式适配**：接收 PCM 或 Opus，返回单声道 16-bit PCM，可指定输出采样率。
- **流式转换链路**：音频分块、VAD、上下文保留、可选音高调整与语义检索、音量混合和 SOLA 拼接。
- **服务部署**：按配置加载模型和参考音色，支持多 Worker、设备列表与不同端口的多实例。
- **会话与分析**：保存输入/输出和时间线，提供健康检查、版本与会话数据接口，以及离线分析工具。

参考音色在服务启动时配置并由 Worker 复用，当前没有逐请求上传参考音频的接口。内部工作流程见[总体设计](docs/design/总体设计.md)。

## 2. 音频样例

仓库提供以下输入与参考音频，可用快速开始生成转换结果并对照试听：

| 角色 | 文件 |
| --- | --- |
| 源音频 | [男声样例](resources/srcs/male-0-16khz.wav) · [女声样例](resources/srcs/female-0-16khz.wav) |
| 默认参考音色 | [参考音频](resources/refs/ref-24k.wav) |
| 转换结果 | 运行下方示例后保存在 outputs/quickstart |

这里提供的是复现输入，尚未附带与当前版本绑定的转换结果合集。效果比较时应记录模型、配置和参考音频；方法见[评测指南](docs/evaluation/README.md)。

## 3. 运行要求与范围

- 快速开始采用 **Linux、NVIDIA CUDA、Python 3.10 和 uv**。历史性能报告记录了 NVIDIA GPU 结果；显存需求随模型与 Worker 数变化。
- 需要 Opus、音频文件读写等系统依赖，首次启动可能下载模型。
- 默认配置使用 cuda:0、2 个 Worker、tiny 模型和仓库参考音频。Windows 原生及 CPU 实时性能没有当前验证保证。
- 当前内置 api_key 仅检查非空；外部访问需由部署层提供认证和访问控制。默认会保存会话音频，部署时按用途配置。

详见[配置与部署](docs/getting_started/配置与部署.md)。

## 4. 快速开始

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 并准备 NVIDIA 驱动。Ubuntu / Debian：

```bash
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 libsndfile1 portaudio19-dev ffmpeg
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
uv sync --locked --python 3.10
cp .env.example .env
uv run fast-vc serve -c configs/prod.yaml
```

启动前按实际硬件调整 configs/prod.yaml 的 device 和 workers。等待模型初始化，在另一个终端进入仓库根目录：

```bash
curl http://localhost:8042/health
uv run python examples/websocket/simple_protocol_ws_client.py \
  --source-wav-path resources/srcs/male-0-16khz.wav \
  --output-wav-dir outputs/quickstart \
  --encoding PCM \
  --samplerate 16000 \
  --url ws://localhost:8042/ws
```

检查终端的 Output saved to 路径和 outputs/quickstart 中生成的 WAV。此示例使用简单协议、PCM 输入和 16000 Hz PCM 输出；需要 Opus、22050 Hz 输出或并发时，按[完整快速开始](docs/getting_started/quick_started_zh.md)使用标准客户端。

## 5. 历史性能参考

以下摘自 **v0.1.0** 报告：Seed-VC v1.0 tiny、16 kHz / 16-bit PCM、500 ms 推理块、10 个扩散步。它们不是当前版本重测结果，不能直接外推部署容量。

| GPU | 并发 | Worker | 报告中的平均 chunk 延迟（ms） | 报告中的平均 RTF |
| --- | --- | --- | --- | --- |
| RTX 4090D | 1 | 6 | 105.0 | 0.21 |
| RTX 4090D | 12 | 12 | 216.6 | 0.44 |
| GTX 1080 Ti | 1 | 6 | 252.2 | 0.50 |

原始记录：[4090D](docs/perfermance_tests/version0.1.0_4090D.md)（2025-06-15）、[1080 Ti](docs/perfermance_tests/version0.1.0_1080ti.md)（2025-06-14）、[全部报告](docs/perfermance_tests/README.md)。

模型处理耗时、首包等待、尾部收发差值和包含采集播放的端到端时延有不同含义。重新测量前请阅读[指标口径与限制](docs/evaluation/README.md)。

## 6. 使用与开发文档

| 目标 | 入口 |
| --- | --- |
| 安装并完成首次转换 | [快速开始](docs/getting_started/quick_started_zh.md) |
| 接入语音应用 | [WebSocket API](docs/api_docs/websocket-api-doc.md) · [HTTP API](docs/api_docs/http-api.md) |
| 调整模型、音色与部署 | [配置与部署](docs/getting_started/配置与部署.md) |
| 排查问题与评估效果 | [故障排查](docs/getting_started/故障排查.md) · [评测](docs/evaluation/README.md) |
| 理解实现与参与贡献 | [设计](docs/design/README.md) · [贡献指南](CONTRIBUTING.md) |
| 查看完整文档 | [文档索引](docs/README.md) |

## 7. 版本动态

仓库包版本为 **0.1.7**。该版本的主要变化包括 CFM 时间步安排、22.05 kHz 模型后处理输出及可配置的 WebSocket 输出采样率，详细内容见[版本历史](docs/changelog/releases.md)。

[GitHub Releases](https://github.com/Leroll/fast-vc-service/releases) · [每日工程变更](docs/changelog/README.md) · [已确认待办](docs/todo.md)

## 8. 问题与贡献

欢迎通过 [Issues](https://github.com/Leroll/fast-vc-service/issues) 提交可复现的问题和建议，或按[贡献指南](CONTRIBUTING.md)提交改进。报告问题时说明版本、环境、配置、输入格式与复现步骤。

## 9. 许可证与致谢

本项目代码采用 [GPL-3.0](LICENSE)。所选模型权重与音频素材的使用条件应分别查看其来源说明。

感谢 [Seed-VC](https://github.com/Plachtaa/seed-vc) 提供底层语音转换模型，以及 [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) 的流式处理工作。
