# 会话数据 API

[API 参考](README.md) · [English](../../en/api/session-data.md)

`GET /tools/session/{session_id}`

读取已保存的会话录音和时间线，返回经过 ZIP、GZIP 和 Base64 编码的文件包。此接口查询磁盘文件，不查询正在运行的会话。

## 1. 请求

```bash
curl --fail-with-body \
  'http://localhost:8042/tools/session/example-001?date=2026-11-02'
```

将示例中的会话 ID 和日期替换为实际值。请求无 body，访问控制见[认证](README.md#3-认证)。

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 语音转换时使用的 `session_id`，简单协议对应 `stream_id` |
| `date` | query | string | 否 | 保存日期，格式为 `YYYY-MM-DD`；省略时搜索整个保存目录 |

日期按服务进程保存文件时的本地日期计算。服务从配置的保存目录递归查找，提供有效日期时仅搜索对应日期的子目录。

**匹配规则**：文件名使用 `{session_id}*` 前缀匹配。例如 `example-001` 也可能匹配 `example-001-extra` 的文件；请使用唯一且不易混淆的会话 ID。当前无效日期会回退到整个保存目录搜索，不会返回日期格式错误。

## 2. 响应

`200 OK` · `application/json`

响应体是 **JSON 字符串**。解析 JSON 后，按以下顺序得到 ZIP 文件：

```text
JSON string → Base64 解码 → GZIP 解压 → ZIP 文件
```

不要按 `{ "data": ... }` 对象解析，也不要直接把 HTTP 响应保存为 ZIP。当前 `/openapi.json` 未声明该接口的精确成功响应模型。

ZIP 中可能包含以下文件，是否生成取决于保存配置及实际录音数据：

| 文件 | 内容 |
| --- | --- |
| `{session_id}_input.wav` | 输入录音，使用模型前端采样率 |
| `{session_id}_output.wav` | 转换后的录音，使用 `sample_rate_out` |
| `{session_id}_timeline.json` | 会话事件时间线 |

### 2.1 Python 解码示例

以下示例请求会话数据并列出 ZIP 内的文件，仅依赖 Python 标准库。

```python
import base64
import gzip
import io
import json
import zipfile
from urllib.request import urlopen

url = "http://localhost:8042/tools/session/example-001?date=2026-11-02"
with urlopen(url, timeout=30) as response:
    encoded = json.load(response)

zip_bytes = gzip.decompress(base64.b64decode(encoded, validate=True))
with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
    for entry in archive.infolist():
        print(entry.filename, entry.file_size)
```

## 3. 错误

`500 Internal Server Error` · `application/json`

未找到文件，或查找、读取、压缩失败时，返回包含 `detail` 的对象。未找到文件的响应示例：

```json
{
  "detail": "Internal server error: No files found for session ID: example-001"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `detail` | string | 异常说明；不是固定的业务错误码 |

当前未找到文件也返回 `500`，而非 `404`。先确认会话 ID、保存日期、录音开关和保存状态；其他 `500` 错误需结合服务日志排查。

## 4. 保存时序

语音转换的 `complete` / `completed` 消息发出后，服务才在退出清理时启动后台保存。立即查询可能返回“未找到文件”，也可能只包含部分已写入文件。

此接口不等待保存完成，也不提供完成标志或原子快照。调用方应在文件保存后读取；不要对所有 `500` 无条件重试。保存设置见[配置与部署](../getting-started/configuration.md)，具体记录内容见[数据记录设计](../design/数据记录与可观测性.md#31-保存内容)。
