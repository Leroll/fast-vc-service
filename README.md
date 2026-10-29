# Fast-VC

<p align="center">
  <img src="assets/cover.PNG" alt="Fast-VC: real-time streaming voice conversion service" width="80%">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL%20v3-blue.svg" alt="GPL v3"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <a href="https://github.com/Leroll/fast-vc-service/releases"><img src="https://img.shields.io/github/v/release/Leroll/fast-vc-service" alt="GitHub release"></a>
</p>

A real-time streaming voice conversion service built on Seed-VC. Integrate voice conversion into speech applications over WebSocket, with audio buffering, session management and multi-Worker deployment.

English · [简体中文](README_ZH.md) · [Quick start](docs/getting_started/quick_started_en.md) · [API](docs/api_docs/websocket-api-doc_EN.md) · [Documentation](docs/README.md)

## 1. Purpose and capabilities

Fast-VC is for developers who want to convert a continuous speech stream to a configured reference voice and feed the result back into an application. It adds service interfaces and streaming orchestration around Seed-VC inference.

- **Bidirectional audio streaming** over WebSocket, with standard and simple protocols.
- **Audio adaptation**: PCM or Opus input, mono 16-bit PCM output with a configurable output sample rate.
- **Streaming conversion**: chunking, VAD, retained context, optional pitch adjustment and semantic retrieval, RMS mixing and SOLA stitching.
- **Service deployment**: configured models and reference voices, multiple Workers, device lists and separate service ports.
- **Sessions and analysis**: audio/timeline recording, health/version/session endpoints and offline analysis tools.

Reference conditions are loaded at service startup and reused by Workers; there is no per-request reference-upload interface. See the [architecture](docs/design/总体设计.md) (Chinese).

## 2. Audio samples

Use the bundled source and reference files to generate a converted result with the quick start:

| Role | File |
| --- | --- |
| Source | [Male sample](resources/srcs/male-0-16khz.wav) · [Female sample](resources/srcs/female-0-16khz.wav) |
| Default reference voice | [Reference audio](resources/refs/ref-24k.wav) |
| Converted result | Generated in outputs/quickstart by the example below |

These files provide reproducible inputs; a collection of converted outputs tied to the current version is not bundled. Record the model, configuration and reference when comparing quality. See the [evaluation guide](docs/evaluation/README.md) (Chinese).

## 3. Requirements and scope

- The quick start targets **Linux, NVIDIA CUDA, Python 3.10 and uv**. Historical reports contain NVIDIA GPU results; memory needs vary by model and Worker count.
- System audio libraries are required. Initial startup may download model files.
- The default configuration uses cuda:0, two Workers, the tiny model and a bundled reference. Native Windows support and real-time CPU performance have not been established by current validation.
- The built-in api_key check only checks for a nonempty value. Supply authentication and access controls at the deployment layer. Session audio is recorded by default; configure recording for your use case.

See [configuration and deployment](docs/getting_started/配置与部署.md) (Chinese).

## 4. Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and prepare an NVIDIA driver. On Ubuntu / Debian:

```bash
sudo apt-get update
sudo apt-get install -y libopus-dev libopus0 libsndfile1 portaudio19-dev ffmpeg
git clone --recursive https://github.com/Leroll/fast-vc-service.git
cd fast-vc-service
uv sync --locked --python 3.10
cp .env.example .env
uv run fast-vc serve -c configs/prod.yaml
```

Adjust device and workers in configs/prod.yaml for your hardware before starting. After model initialization, open another terminal at the repository root:

```bash
curl http://localhost:8042/health
uv run python examples/websocket/simple_protocol_ws_client.py \
  --source-wav-path resources/srcs/male-0-16khz.wav \
  --output-wav-dir outputs/quickstart \
  --encoding PCM \
  --samplerate 16000 \
  --url ws://localhost:8042/ws
```

Check the Output saved to path and the generated WAV in outputs/quickstart. This example uses the simple protocol with PCM input and 16000 Hz PCM output. For Opus input, 22050 Hz output or concurrent requests, use the standard client in the [full quick start](docs/getting_started/quick_started_en.md).

## 5. Historical performance

The following results are from **v0.1.0**: Seed-VC v1.0 tiny, 16 kHz / 16-bit PCM, 500 ms inference blocks and 10 diffusion steps. They are not fresh measurements of the current version or a deployment-capacity guarantee.

| GPU | Concurrency | Workers | Reported average chunk latency (ms) | Reported average RTF |
| --- | --- | --- | --- | --- |
| RTX 4090D | 1 | 6 | 105.0 | 0.21 |
| RTX 4090D | 12 | 12 | 216.6 | 0.44 |
| GTX 1080 Ti | 1 | 6 | 252.2 | 0.50 |

Original reports: [4090D](docs/perfermance_tests/version0.1.0_4090D.md) (2025-06-15), [1080 Ti](docs/perfermance_tests/version0.1.0_1080ti.md) (2025-06-14), [all reports](docs/perfermance_tests/README.md).

Model processing time, first-chunk wait, final send/receive gap and capture-to-playback latency are different measurements. Review [metric definitions and limitations](docs/evaluation/README.md) (Chinese) before measuring again.

## 6. Documentation

| Goal | Entry |
| --- | --- |
| Install and convert your first file | [Quick start](docs/getting_started/quick_started_en.md) |
| Integrate a speech application | [WebSocket API](docs/api_docs/websocket-api-doc_EN.md) · [HTTP API](docs/api_docs/http-api.md) |
| Configure models, voices and deployment | [Deployment guide](docs/getting_started/配置与部署.md) (Chinese) |
| Troubleshoot and evaluate | [Troubleshooting](docs/getting_started/故障排查.md) · [Evaluation](docs/evaluation/README.md) (Chinese) |
| Understand and contribute | [Design](docs/design/README.md) (Chinese) · [Contributing](CONTRIBUTING.md) |
| Browse everything | [Documentation index](docs/README.md) (Chinese) |

## 7. Version updates

The repository package version is **0.1.7**. Its main changes include CFM time-step scheduling, 22.05 kHz model post-processing output and configurable WebSocket output sample rates. See the [release history](docs/changelog/releases_en.md).

[GitHub Releases](https://github.com/Leroll/fast-vc-service/releases) · [Daily engineering changes](docs/changelog/README.md) · [Confirmed tasks](docs/todo.md)

## 8. Help and contributions

Report reproducible bugs and proposals through [Issues](https://github.com/Leroll/fast-vc-service/issues), or follow the [contribution guide](CONTRIBUTING.md). Include the version, environment, configuration, input format and reproduction steps.

## 9. License and acknowledgements

This project's code is licensed under [GPL-3.0](LICENSE). Consult the respective sources for the terms of model weights and audio assets.

Thanks to [Seed-VC](https://github.com/Plachtaa/seed-vc) for the underlying conversion model and [RVC](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) for its streaming-processing work.
