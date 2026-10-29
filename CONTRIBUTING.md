# Contributing to Fast-VC

## 1. Start here

Fast-VC welcomes fixes, documentation improvements, reproducible bug reports and service integrations. Start with the [README](README.md) and [documentation index](docs/README.md). Implementation and design documents are currently maintained in Chinese; the README, quick start and WebSocket reference are available in English and Chinese.

Use [GitHub Issues](https://github.com/Leroll/fast-vc-service/issues) for bugs and proposals. Include the repository revision, model/configuration, environment, input format, reproduction steps, expected behavior and actual result. Share minimal examples and sanitized logs.

## 2. Development setup

Clone with submodules and follow the [quick start](docs/getting_started/quick_started_en.md). Use uv with the existing pyproject.toml and uv.lock. Run commands from the repository root.

Service code lives in `src/fast_vc_service/`; clients in `examples/websocket/`; configuration in `configs/`. The Seed-VC submodule is part of this repository's dependency tree. See the [design index](docs/design/README.md) before changing streaming behavior.

## 3. Propose and implement a change

For substantial features, protocol changes, refactors, inference changes or deployment changes, record the design and acceptance criteria in [specs](docs/specs/README.md) before implementation. Small fixes can use a concise changelog entry. Reuse an existing task record when continuing the same change.

Keep patches focused. Update current design and affected user documentation alongside behavior changes. Keep the English and Chinese README, quick start and WebSocket reference consistent. AI-assisted work follows [AGENTS.md](AGENTS.md).

## 4. Validation

Documentation changes require relative-link and anchor checks, a source consistency review and `git diff --check`.

Choose validation appropriate to code changes: protocol/configuration checks, service integration, GPU inference, listening evaluation or load testing. This repository currently has no dedicated automated test suite; do not claim that example clients constitute regression coverage. Describe what you actually ran and what remains untested.

Performance and audio-quality results must state their model, hardware, configuration and input conditions; follow the [evaluation guide](docs/evaluation/README.md). Keep raw audio, model caches, session outputs and credentials out of patches unless their publication is explicitly part of the contribution.

## 5. Pull requests and commits

Explain the problem, resulting behavior, compatibility impact and validation. Link the related issue or Spec and describe limitations. Preserve unrelated work and historical records.

Use commit messages in the form `<type>: <中文描述>`, for example `docs: 更新流式接口与快速开始`. Types: feat, fix, docs, refactor, test, build, ci, chore.

Record actual changes in [changelog](docs/changelog/README.md). Use [todo](docs/todo.md) only for confirmed unfinished work; proposals remain proposals until accepted.
