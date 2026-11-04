# Configuration and deployment

[User documentation](../index.md) · [简体中文](../../zh/getting-started/configuration.md)

## 1. Commands and configuration sources

Run commands from the repository root. Follow the [quick start](quick-start.md) to install dependencies and initialize submodules first.

Configuration precedence is CLI `--config / -c` → the `CONFIG_PATH` environment variable → Python configuration class defaults. .env.example selects `configs/prod.yaml`. If reading or parsing a configuration file fails, the current implementation logs the failure and falls back to class defaults. Check the loaded path and effective settings in the startup logs.

```bash
uv run fast-vc serve -c configs/prod.yaml
uv run fast-vc status -p 8042
uv run fast-vc version
```

Class defaults differ from prod.yaml, including pitch adjustment, diffusion steps, RMS mixing and the reference audio path. See [config.py](../../../src/fast_vc_service/config.py) for field definitions and [prod.yaml](../../../configs/prod.yaml) for example deployment values.

## 2. Common settings

The following values come from prod.yaml. They are not universal recommendations for every model.

| Setting | Example value | Description |
| --- | --- | --- |
| app.host / port / workers | 0.0.0.0 / 8042 / 2 | Listen address and number of Uvicorn processes |
| app.receive_timeout | 120 | Timeout for each receive after initialization, in seconds |
| buffer.prefill_time | 375 | Silence prefill for the first inference block, in milliseconds |
| buffer.opus_frame_duration | 20 | Opus frame duration when omitted from the request, in milliseconds |
| realtime_vc.device | [cuda:0] | Worker device list |
| realtime_vc.reference_wav_path | resources/refs/ref-24k.wav | Reference audio loaded at Worker startup |
| realtime_vc.block_time | 0.5 | Inference block duration, in seconds |
| realtime_vc.SAMPLERATE_IN / SAMPLERATE_OUT | 16000 / 22050 | Model front-end and post-processing sample rates |
| realtime_vc.extra_time_ce / extra_time_dit | 4.5 / 1.5 | Encoder and DiT left context, in seconds |
| realtime_vc.sola_buffer_time / extra_time_right | 0.04 / 0.02 | Stitching region and right context, in seconds |
| realtime_vc.is_f0 | false | Adaptive pitch adjustment |
| realtime_vc.diffusion_steps / inference_cfg_rate | 5 / 0.7 | Diffusion steps and guidance rate |
| realtime_vc.max_prompt_length | 5.0 | Maximum reference audio duration used, in seconds |
| realtime_vc.rms_mix_rate / is_sola | 0.9 / true | Volume envelope mixing and stitching |
| realtime_vc.save_input / save_output / save_dir | true / true / outputs/ | Audio recording switches and directory |
| models.is_retrieval / index_rate | false / 1.0 | Semantic retrieval switch and mixing ratio |
| models.t_span_schedule | cosine | CFM time-step schedule |
| models.speech_noise_thres / decibel_thres | 0.8 / -50 | VAD parameters |
| models.defalut_original_model | tiny | Model selected when a complete custom model path pair is not provided |

Provide `models.dit_checkpoint_path` and `models.dit_config_path` together. When retrieval is enabled, `models.index_path` must point to an existing, matching index. The retrieval index referenced by prod.yaml is not bundled with the repository.

Use the request's `sample_rate_out` to control the output rate sent to the client; see the [API](../api/voice-conversion.md). Do not change the model sample rate just to adjust network output.

## 3. Environment, models and reference voice

.env.example provides CONFIG_PATH, HF_HUB_CACHE and MODELSCOPE_CACHE. The model factory resolves relative cache paths against the repository root. Other relative audio, output and log paths are generally resolved against the process working directory. Starting from the repository root reduces ambiguity.

Python version requirements are in pyproject.toml; the quick start uses 3.10. The default configuration uses NVIDIA CUDA. Historical reports contain NVIDIA GPU results but do not preserve a complete software environment. The code includes a CPU fallback, which does not establish validated real-time CPU performance. Native Windows operation is also limited by Unix dependencies such as fcntl.

The reference voice is fixed by the service configuration. Restart the instance after changing the file or configuration. Initial startup downloads models; confirm that downloads have finished before sending requests or measuring performance.

## 4. Multiple Workers, devices and instances

Workers are assigned to devices in round-robin order, and each process loads its own model. Measure with low concurrency before adding Workers; GPU memory usage and throughput require measurement.

To add an instance, copy the configuration and change the port, device, reference voice, log directory and output directory:

```bash
cp configs/prod.yaml configs/voice-b.yaml
# Edit voice-b.yaml: use port 8043 and separate log/output paths.
uv run fast-vc serve -c configs/voice-b.yaml
```

Connection statistics currently use a shared file within the working directory. Use separate repository clones and distinct ports when runtime files need to be independent. Different ports alone do not isolate all data.

## 5. Service management and access

Stop a service by its target port:

```bash
uv run fast-vc stop -p 8042
```

Without a port or configuration, stop attempts to stop all instances recorded by the CLI. Clean requires an explicit `--logs` or `--outputs` option and interactive confirmation after listing files. There is currently no `-y` option. It cleans fixed repository directories, not arbitrary custom output paths from configuration.

The built-in api_key check is a placeholder, and the HTTP session endpoint has no authentication. Public access requires authentication, TLS and access control at the deployment layer; otherwise use a controlled network or bind only to a loopback address. The default configuration saves audio and timelines. Set recording switches and a retention policy for your use case.

The repository Dockerfile still uses Poetry and has not been validated for this guide. This guide uses uv to run from source. Validation and updates for the container workflow require separate work.
