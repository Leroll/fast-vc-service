# Fast-VC documentation

[简体中文](../README.md) · [Project home](README.md)

Start with your first voice conversion, then find deployment instructions, API contracts and explanations for your task.

[Get started](getting-started/quick-start.md) · [Explore the API](api/README.md)

**Documentation version: main development branch.** For a released version, open its tag from [GitHub Releases](https://github.com/Leroll/fast-vc-service/releases) and read the documentation at that tag.

## 1. Installation and operation

| Task | What you will learn | Read |
| --- | --- | --- |
| Your first conversion | Prepare the environment, start the service and verify audio input and output with a bundled sample. | [Quick start](getting-started/quick-start.md) |
| Integrate your application | Understand messages, fields and audio formats; receive converted audio and session data. | [Voice conversion API](api/voice-conversion.md) · [System API](api/system.md) · [Session data](api/session-data.md) |
| Configure and deploy | Set up models, reference voices, devices and Workers, and diagnose runtime issues. | [Configuration and deployment](getting-started/configuration.md) · [Troubleshooting](getting-started/troubleshooting.md) |
| Understand and evaluate | Follow the streaming pipeline and measure quality, latency and throughput consistently. | [Architecture](../design/总体设计.md) · [Evaluation guide](../evaluation/README.md) (Chinese) · [Evaluation reports](../evaluation/reports/README.md) (Chinese index) |

## 2. API reference

The [API reference](api/README.md) is the primary source for messages, fields, errors and integration contracts. [Configuration and deployment](getting-started/configuration.md#2-common-settings) explains deployment settings and their source.

## 3. Further reading

- [Architecture](../design/总体设计.md) and [design index](../design/README.md) (Chinese): buffering, sessions, streaming conversion and models.
- [Release notes](../changelog/releases_en.md): user-facing changes for recorded releases.
- [Development and maintenance](../maintainers/README.md) (Chinese): contribution instructions, documentation maintenance and engineering records.
