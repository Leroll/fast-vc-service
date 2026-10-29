# 历史性能报告

## 1. 报告索引

| GPU | 版本 | 报告 |
| --- | --- | --- |
| RTX 4090D | 0.1.0 | [原始报告](version0.1.0_4090D.md) |
| GTX 1080 Ti | 0.1.0 | [原始报告](version0.1.0_1080ti.md) |
| Tesla V100 | 0.1.0 | [原始报告](version0.1.0_v100.md) |

报告正文与路径保持原样，目录名称保留原有拼写以兼容链接。它们是历史测试证据，不是当前版本重测结果。报告中的生产建议只属于当时的测量条件，不能直接外推。

## 2. 当前使用方式

历史报告中提及的 concurrent_ws_client.py 已不在当前仓库。新评测使用[标准客户端配置方式](../getting_started/quick_started_zh.md)和[评测指南](../evaluation/README.md)，不要按旧脚本命令操作。

README 仅摘录有明确版本和硬件条件的历史结果。新报告应补齐模型、输入、参考音频、配置、硬件、采样率、发送节奏和计时位置，分别说明首包、尾部收发差值、处理耗时和播放延迟。

## 3. English note

These reports are preserved historical results for version 0.1.0, not fresh measurements of the current version. The old concurrent_ws_client.py command is no longer available. Use the [current client guide](../getting_started/quick_started_en.md) and [evaluation guide](../evaluation/README.md) (Chinese). Hardware, model, configuration and metric definitions must accompany new results.
