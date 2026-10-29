# 快速开始

## 1. 环境与安装

本指南使用 Linux、NVIDIA CUDA 和 Python 3.10；需已安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和与 Torch 环境兼容的 NVIDIA 驱动。历史性能报告记录了 NVIDIA GPU 结果，当前没有完整的跨平台验证矩阵。

在 Ubuntu / Debian 安装系统依赖并克隆仓库：

```bash
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 libsndfile1 portaudio19-dev ffmpeg
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
uv sync --locked --python 3.10
cp .env.example .env
```

已有克隆可执行 `git submodule update --init --recursive` 补齐子模块。项目依赖与版本锁定分别在 pyproject.toml 和 uv.lock；GPU 效果评测的可选依赖见[评测指南](../evaluation/README.md)。

后续命令均从仓库根目录运行。

## 2. 配置与启动

.env.example 默认指定 configs/prod.yaml。该配置使用 cuda:0、2 个 Worker 和仓库内参考音频 resources/refs/ref-24k.wav。启动前按实际硬件调整 device 与 workers；首次运行可能下载模型，需要等待模型和参考条件初始化完成。

```bash
uv run fast-vc serve -c configs/prod.yaml
```

另开终端，在同一仓库根目录检查服务：

```bash
curl http://localhost:8042/health
curl http://localhost:8042/version
```

health 应返回 `{"status":"healthy"}`，只检查 HTTP 请求处理，不执行一次推理。参考音色在 Worker 启动时加载，修改参考音频配置后重启；协议没有逐请求上传参考音频的字段。

## 3. 完成第一次转换

使用仓库样例和现有简单协议客户端，按实时节奏发送 PCM：

```bash
uv run python examples/websocket/simple_protocol_ws_client.py \
  --source-wav-path resources/srcs/male-0-16khz.wav \
  --output-wav-dir outputs/quickstart \
  --encoding PCM \
  --samplerate 16000 \
  --url ws://localhost:8042/ws
```

客户端接收默认 16000 Hz 的单声道 PCM 并保存为 WAV。检查终端的 Output saved to 路径、outputs/quickstart 中的音频文件和错误日志，再对照[源音频](../../resources/srcs/male-0-16khz.wav)与[参考音频](../../resources/refs/ref-24k.wav)试听。Success 字样不能单独证明音频完整或音质合格。

该客户端的首条消息未传递 encoding，输出保存固定为 16000 Hz。因此这里明确使用 PCM / 16000 Hz 输出，不直接将命令改为 OPUS。需要其他输入编码或输出采样率时，使用下一节的标准客户端。

## 4. 标准协议与并发调用

标准客户端通过 Inputs 配置。显式提供源文件，避免依赖 ws_client.py 默认入口中的环境相关目录：

```bash
uv run python - <<'PY'
import asyncio
from examples.websocket.ws_client import Inputs, multi_ws_clients

inputs = Inputs(
    url="ws://localhost:8042/ws",
    api_key="example-key",
    src_wavs=["resources/srcs/male-0-16khz.wav"],
    encoding="PCM",
    samplerate_out=22050,
    max_workers=1,
    worker_delay=0.0,
    save_timeline=True,
)
asyncio.run(multi_ws_clients(inputs))
PY
```

结果位于 outputs/ws_client；save_timeline 会额外保存会话时间线。调整 src_wavs 列表、max_workers 和 worker_delay 可运行多个请求；每个列表元素对应一次请求，只有一个文件时不会因增加 max_workers 自动产生多请求。

需要 Opus 输入时设置 `encoding="OPUS"`，并按 [API](../api_docs/websocket-api-doc.md)选择输入采样率与帧长。服务返回仍为 PCM。标准客户端的 samplerate_out 对应协议字段 sample_rate_out。

## 5. 管理与后续阅读

```bash
uv run fast-vc status -p 8042
uv run fast-vc stop -p 8042
```

stop 不带端口或配置会操作 CLI 记录的全部实例。clean 需指定 --logs 或 --outputs，并交互确认删除；没有 -y 选项。

当前 api_key 仅为占位校验，默认配置会保存会话音频。对外接入前按[配置与部署](配置与部署.md)设置访问控制及保存策略。

- [WebSocket API](../api_docs/websocket-api-doc.md) / [HTTP API](../api_docs/http-api.md)
- [故障排查](故障排查.md)
- [性能与效果评测](../evaluation/README.md)
- [当前设计](../design/README.md) / [贡献指南](../../CONTRIBUTING.md)
- [English](quick_started_en.md)
