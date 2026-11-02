# Troubleshooting

[User documentation](../index.md) · [简体中文](../../getting-started/troubleshooting.md)

## 1. Startup and dependencies

| Symptom | What to check |
| --- | --- |
| Seed-VC module not found | Run `git submodule update --init --recursive` from the repository root |
| Opus or audio libraries fail to load | Check the system dependencies in the quick start; Python packages alone are not sufficient |
| Initial startup takes a long time | Check model download and cache logs and wait for downloads to finish; exclude the initial download from inference measurements |
| CUDA unavailable or GPU memory exhausted | Check the driver, Torch environment, device list and Worker count; each Worker loads its own model |
| Configuration seems ineffective | Pass `-c configs/prod.yaml` explicitly and inspect logs; parsing failures may fall back to class defaults |
| Reference audio or retrieval index not found | Start from the repository root; the reference path must exist, and a matching index must be prepared before enabling retrieval |

Use pyproject.toml, uv.lock, the submodule commit and model configuration to identify model and dependency versions. Avoid upgrading every dependency as a substitute for diagnosing the issue.

## 2. Clients and output

The quick start uses the simple-protocol client with PCM input and the protocol's default 16000 Hz output. Although this script has an OPUS command-line option, it omits encoding from the initial message. Selecting OPUS directly therefore conflicts with the server's default PCM interpretation. The script also writes output at a fixed 16000 Hz. This client limitation does not mean the service itself lacks Opus support.

For Opus, an explicit output sample rate or concurrent requests, use the standard client's Inputs invocation in the quick start. The default entry point in `ws_client.py` contains environment-specific input settings and is not a general-purpose demo. The documented invocation supplies repository resources explicitly.

Inspect the WAV files in the client output directory, error logs and received data, not only the Success label. The clients' current completion checks do not establish protocol completeness or audio quality.

## 3. Interfaces and measurements

- Decode output as 16-bit mono PCM at sample_rate_out.
- The simple protocol has no ready response; waiting for one will stall the client.
- End normally with the selected protocol's end message. Disconnecting directly does not guarantee that the remaining tail is processed.
- Background saving may still be pending after complete; immediately retrieving session files can fail.
- There is currently no /tools/performance-report route. Use the [offline evaluation guide](../../evaluation/README.md) (Chinese).
- With output rates other than 16 kHz, the server's timeline audio-duration statistics are inaccurate. See the [measurement limitations](../../design/数据记录与可观测性.md#5-当前测量限制) (Chinese).

## 4. Reporting an issue

Report issues through [GitHub Issues](https://github.com/Leroll/fast-vc-service/issues). Include the version or commit, model, effective configuration, hardware, audio format, reproduction steps and sanitized logs. Only attach minimal audio samples that can be published, and remove credentials, local machine paths and business data. See the [contribution guide](../../../CONTRIBUTING.md) (Chinese) for further development.
