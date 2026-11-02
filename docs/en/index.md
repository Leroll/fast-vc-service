# Fast-VC documentation

[简体中文](../README.md) · [Project home](README.md)

Start with your first voice conversion, then find deployment instructions, API contracts and explanations for your task.

**Documentation version: main development branch.** For a released version, open its tag from [GitHub Releases](https://github.com/Leroll/fast-vc-service/releases) and read the documentation at that tag.

## 1. Installation and operation

Start with the [quick start](getting-started/quick-start.md): prepare the environment, start the service, convert a bundled audio sample and inspect the result.

| I want to… | Read |
| --- | --- |
| Configure models, reference voices or multiple Workers | [Configuration and deployment](getting-started/configuration.md) |
| Integrate a WebSocket audio stream | [Voice conversion API](api/voice-conversion.md) |
| Check service health and version | [System API](api/system.md) |
| Retrieve recordings and session timelines | [Session data API](api/session-data.md) |
| Diagnose startup, connection or audio problems | [Troubleshooting](getting-started/troubleshooting.md) |
| Measure quality, latency and throughput | [Evaluation guide](../evaluation/README.md) (Chinese) |

## 2. API reference

The [API reference](api/README.md) is the primary source for messages, fields, errors and integration contracts. [Configuration and deployment](getting-started/configuration.md#2-common-settings) explains deployment settings and their source.

## 3. Further reading

- [Architecture](../design/总体设计.md) and [design index](../design/README.md) (Chinese): buffering, sessions, streaming conversion and models.
- [Release notes](../changelog/releases_en.md): user-facing changes for recorded releases.
- [Development and maintenance](../maintainers/README.md) (Chinese): contribution instructions, documentation maintenance and engineering records.
