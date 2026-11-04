# Session Data API

[API reference](README.md) · [简体中文](../../zh/api/session-data.md)

`GET /tools/session/{session_id}`

Retrieve saved session recordings and timelines as a ZIP archive encoded with GZIP and Base64. This endpoint reads files on disk, not active sessions.

## 1. Request

```bash
curl --fail-with-body \
  'http://localhost:8042/tools/session/example-001?date=2026-11-02'
```

Replace the session ID and date with actual values. There is no request body. See [authentication](README.md#3-authentication) for access control.

| Parameter | Location | Type | Required | Description |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | Yes | The voice conversion `session_id`, or `stream_id` for the simple protocol |
| `date` | query | string | No | Save date in `YYYY-MM-DD` format; omit to search the entire save directory |

The date is the server process's local date when saving. The server searches the configured save directory recursively, restricting the search to the date subdirectory when a valid date is supplied.

**Matching**: filenames are matched by the `{session_id}*` prefix. For example, `example-001` may also match files for `example-001-extra`; use unique, unambiguous session IDs. An invalid date currently falls back to searching the entire save directory instead of returning a date-format error.

## 2. Response

`200 OK` · `application/json`

The response body is a **JSON string**. Parse the JSON, then decode it in this order:

```text
JSON string → Base64 decode → GZIP decompress → ZIP archive
```

Do not parse it as a `{ "data": ... }` object or save the HTTP response directly as a ZIP file. The current `/openapi.json` does not declare a precise success-response model for this endpoint.

The ZIP may contain these files, depending on recording settings and the data recorded:

| File | Contents |
| --- | --- |
| `{session_id}_input.wav` | Input recording at the model-front-end sample rate |
| `{session_id}_output.wav` | Converted recording at `sample_rate_out` |
| `{session_id}_timeline.json` | Session event timeline |

### 2.1 Python decoding example

This example retrieves session data and lists the files in the ZIP. It uses only the Python standard library.

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

## 3. Errors

`500 Internal Server Error` · `application/json`

If no files are found, or lookup, reading or compression fails, the endpoint returns an object with `detail`. Example for missing files:

```json
{
  "detail": "Internal server error: No files found for session ID: example-001"
}
```

| Field | Type | Description |
| --- | --- | --- |
| `detail` | string | Exception description, not a fixed business error code |

Missing files currently return `500`, not `404`. Check the session ID, save date, recording settings and save progress first. Consult server logs for other `500` errors.

## 4. Save timing

After voice conversion sends `complete` / `completed`, the server starts background saving during cleanup. An immediate query may report missing files or include only some of the files already written.

This endpoint does not wait for saving or provide a completion marker or atomic snapshot. Retrieve files after they have been saved; do not retry every `500` unconditionally. See [deployment settings](../getting-started/configuration.md) for storage configuration and the [recording design](../../zh/design/数据记录与可观测性.md#31-保存内容) (Chinese) for recording details.
