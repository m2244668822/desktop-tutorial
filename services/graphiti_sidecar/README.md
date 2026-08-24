# Trevor Graphiti Sidecar

This service runs Graphiti `0.29.3` on Python 3.12 and binds only to loopback.
It serializes graph writes, limits graph queries, disables Graphiti telemetry,
stores no raw episode content, and uses FalkorDBLite `0.10.0`.

```bash
cd services/graphiti_sidecar
GRAPHITI_TELEMETRY_ENABLED=false uv sync --python 3.12
uv run trevor-graphiti
```

Required runtime credentials:

- systemd credential `gemini_api_key` or `nvidia_api_key`; `auto` prefers a valid Gemini key and safely falls back to NVIDIA
- Keychain accounts `trevor.providers/gemini-api-key` and `trevor.providers/nvidia-api-key` are supported by the macOS launcher
- internal token from systemd credential `graphiti_token` or Keychain account `trevor.providers/graphiti-token`
- optional internal API token `TREVOR_GRAPHITI_TOKEN` or systemd credential `graphiti_token`
- OCI Ollama at `TREVOR_OLLAMA_BASE_URL`, with `nomic-embed-text` installed

When Gemini is unavailable, Graphiti uses NVIDIA Nemotron for extraction and a
deterministic lexical reranker. External candidate models never receive graph write authority.

The sidecar API is intentionally limited to `/health`, `/v1/search`, and
`/v1/episodes`. Do not publish port `8091` through a reverse proxy.
