# System API

[API reference](README.md) · [简体中文](../../api/system.md)

Query service liveness and version information. These endpoints take no parameters or request body. See [authentication](README.md#3-authentication) for access control.

## 1. Health check

`GET /health`

Check whether the API is reachable.

**Request**

```bash
curl http://localhost:8042/health
```

**Response** · `200 OK` · `application/json`

```json
{"status": "healthy"}
```

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | Always `healthy` |

This endpoint returns a constant liveness response. It does not check the GPU, model inference or available capacity.

## 2. Version

`GET /version`

Get the service package version and build date.

**Request**

```bash
curl http://localhost:8042/version
```

**Response** · `200 OK` · `application/json`

```json
{
  "version": "0.1.7",
  "build_date": "2025-11-04"
}
```

| Field | Type | Description |
| --- | --- | --- |
| `version` | string | Service package version |
| `build_date` | string | Build date recorded in the package, not the service start time |

The response does not include the model, reference voice or deployment settings.
