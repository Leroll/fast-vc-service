# HTTP API

## 1. 接口 / Endpoints

默认地址为 `http://localhost:8042`。以下接口无内置鉴权，会话接口能读取保存的音频与时间线，访问范围由部署层控制。

These endpoints have no built-in authentication. Restrict access at the deployment layer, especially for saved session data.

| 方法与路径 | 返回 / Response |
| --- | --- |
| GET /health | `{"status": "healthy"}`，不执行推理探测 / Does not run an inference probe |
| GET /version | version、build_date，来自包常量 / Package version and build date |
| GET /tools/session/{session_id} | JSON 字符串：Base64(GZIP(ZIP(匹配文件))) / Encoded session archive |

会话读取可带 date 查询参数（YYYY-MM-DD）。查找使用会话 ID 文件名前缀，日期只是搜索提示，不是租户隔离机制。没有匹配文件等异常当前返回 HTTP 500。

Session lookup matches a filename prefix. An optional date narrows the search; this is not tenant isolation. Missing files currently produce HTTP 500.

## 2. 调用 / Examples

```bash
curl http://localhost:8042/health
curl http://localhost:8042/version
curl 'http://localhost:8042/tools/session/example-001?date=2026-10-29'
```

最后一条要求该会话已经保存。返回值是 JSON 字符串，先解析 JSON，再 Base64 解码和 GZIP 解压，得到 ZIP。complete 后的后台保存不一定已完成。

The last request requires saved files. Parse the JSON string, then Base64-decode and GZIP-decompress it to obtain a ZIP archive. Protocol completion does not guarantee that background saving has finished.

## 3. 实现与范围 / Implementation and scope

源码：[base.py](../../src/fast_vc_service/routers/base.py)、[tools.py](../../src/fast_vc_service/routers/tools.py)、[SessionDataManager](../../src/fast_vc_service/tools/session_data_manager.py)。保存约定见[会话设计](../design/会话与可观测性.md)。

FastAPI 默认提供 /docs 和 /openapi.json，描述 HTTP 路由；WebSocket 合同见独立 [API](websocket-api-doc.md)。当前没有 /tools/performance-report 路由。

FastAPI exposes /docs and /openapi.json for HTTP routes by default. WebSocket messages have a separate reference. There is no current /tools/performance-report endpoint.
