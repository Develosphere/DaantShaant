# Live video WebSocket protocol

**Endpoint:** `WS /v1/live/session` (orchestrator, port 8000)

## Client → server

| type | fields |
|------|--------|
| `session.start` | `user_id` (UUID), `locale` (optional, default `en`) |
| `frame` | `seq` (int), `image_base64` (JPEG, no data-URL prefix) |
| `session.end` | — |
| `ping` | — |

## Server → client

| type | fields |
|------|--------|
| `session.ready` | `session_id`, `max_fps`, `max_analyses` |
| `analysis.progress` | `step`: `opencv` \| `vision` \| `diagnosis`, `seq` |
| `quality.hint` | `message`, optional `quality_score` |
| `analysis.partial` | `analysis`, `diagnosis` (same shape as HTTP pipeline) |
| `analysis.final` | `analysis`, `diagnosis`, `frames_received`, `frames_analyzed`, `session_id` |
| `error` | `code`, `message` |
| `pong` | — |

## Rate limits (defaults)

- Max 1 FPS analyzed server-side
- Max 8 vision calls per session
- Max 120s session duration
