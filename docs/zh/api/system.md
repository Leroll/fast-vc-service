# 系统 API

[API 参考](README.md) · [English](../../en/api/system.md)

查询服务的存活状态和版本信息。以下接口均无请求参数和请求体；访问控制见[认证](README.md#3-认证)。

## 1. 健康检查

`GET /health`

检查 API 是否可访问。

**请求**

```bash
curl http://localhost:8042/health
```

**响应** · `200 OK` · `application/json`

```json
{"status": "healthy"}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | 固定为 `healthy` |

此接口返回固定的存活响应，不检测 GPU、模型推理或可用容量。

## 2. 版本查询

`GET /version`

获取服务包的版本和构建日期。

**请求**

```bash
curl http://localhost:8042/version
```

**响应** · `200 OK` · `application/json`

```json
{
  "version": "0.1.7",
  "build_date": "2025-11-04"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `version` | string | 服务包版本 |
| `build_date` | string | 包内记录的构建日期，不是服务启动时间 |

响应不包含模型、参考音色或部署配置。
