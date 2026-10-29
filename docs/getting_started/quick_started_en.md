# Quick start

## 1. Environment and installation

This guide targets Linux, NVIDIA CUDA and Python 3.10. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and an NVIDIA driver compatible with your Torch environment first. Historical reports contain NVIDIA GPU results; a complete cross-platform validation matrix is not available.

Install system dependencies on Ubuntu / Debian and clone:

```bash
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 libsndfile1 portaudio19-dev ffmpeg
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
uv sync --locked --python 3.10
cp .env.example .env
```

For an existing clone, run `git submodule update --init --recursive`. Dependencies and pinned versions are maintained in pyproject.toml and uv.lock. Optional GPU quality-evaluation dependencies are described in the [evaluation guide](../evaluation/README.md) (Chinese).

Run all following commands from the repository root.

## 2. Configure and start

.env.example selects configs/prod.yaml, which uses cuda:0, two Workers and resources/refs/ref-24k.wav as the reference voice. Adjust device and workers for your hardware. Initial startup may download models; wait for model and reference initialization.

```bash
uv run fast-vc serve -c configs/prod.yaml
```

In another terminal at the repository root:

```bash
curl http://localhost:8042/health
curl http://localhost:8042/version
```

Health should return `{"status":"healthy"}`; this checks HTTP request handling, not an inference. Reference conditions load when each Worker starts. Restart after changing the reference configuration; there is no per-request reference-upload field.

## 3. Convert your first audio file

Use the bundled sample and simple-protocol client to send PCM at a simulated real-time pace:

```bash
uv run python examples/websocket/simple_protocol_ws_client.py \
  --source-wav-path resources/srcs/male-0-16khz.wav \
  --output-wav-dir outputs/quickstart \
  --encoding PCM \
  --samplerate 16000 \
  --url ws://localhost:8042/ws
```

The client receives mono PCM at the protocol's default 16000 Hz and saves a WAV file. Check the Output saved to path, the audio in outputs/quickstart and error logs, then compare the result with the [source](../../resources/srcs/male-0-16khz.wav) and [reference](../../resources/refs/ref-24k.wav). A Success label alone does not establish complete or good-quality audio.

This client omits encoding in its initial message and writes output at a fixed 16000 Hz. The example deliberately uses PCM / 16000 Hz output; do not simply change its encoding argument to OPUS. For other encodings or output rates, use the standard client below.

## 4. Standard protocol and concurrent requests

Configure the standard client through Inputs. Explicit source paths avoid the environment-specific configuration in ws_client.py's default entry point:

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

Results are saved in outputs/ws_client; save_timeline also saves a session timeline. Use src_wavs, max_workers and worker_delay to schedule multiple requests. Each list entry creates one request; increasing max_workers with a single file does not generate extra requests.

For Opus input, set `encoding="OPUS"` and select an input rate and frame duration supported by the [API](../api_docs/websocket-api-doc_EN.md). Output remains PCM. The client's samplerate_out maps to the protocol's sample_rate_out.

## 5. Management and further reading

```bash
uv run fast-vc status -p 8042
uv run fast-vc stop -p 8042
```

Without a port or configuration, stop operates on all instances recorded by the CLI. Clean requires --logs or --outputs and interactive confirmation; there is no -y option.

The current api_key check is a placeholder and the default configuration records session audio. Configure access controls and recording policy before external integration; see [configuration and deployment](配置与部署.md) (Chinese).

- [WebSocket API](../api_docs/websocket-api-doc_EN.md) / [HTTP API](../api_docs/http-api.md)
- [Troubleshooting](故障排查.md) (Chinese)
- [Performance and quality evaluation](../evaluation/README.md) (Chinese)
- [Design](../design/README.md) (Chinese) / [Contributing](../../CONTRIBUTING.md)
- [简体中文](quick_started_zh.md)
