# Trevor Deployment

## Trust Boundary

- API and Graphiti bind only to `127.0.0.1` on OCI.
- Tailscale Serve publishes the API only inside the tailnet; do not enable Funnel.
- Mutable state lives in `/var/lib/trevor`; secrets live in root-only systemd credential files.
- The Mac Edge Client stores failed requests in an AES-256-GCM encrypted queue and reads its API key from Keychain.

## OCI Credentials

Create `/etc/trevor/credentials` with owner `root:root` and mode `0700`. Add these mode `0600` files without a trailing label or shell assignment:

- `nvidia_api_key`
- `gemini_api_key`
- `graphiti_token`
- `trevor_api_hmac`
- `trevor_memory_key_b64`
- `ai_horde_api_key`

Generate independent control secrets with `openssl rand -hex 32` for `graphiti_token` and `trevor_api_hmac`. Generate `trevor_memory_key_b64` with `openssl rand -base64 32`. Never copy these values into `.env` files.

## OCI Install

Prepare Python 3.12 environments at `/opt/trevor/app/.venv` and `/opt/trevor/app/services/graphiti_sidecar/.venv`, pull `nomic-embed-text` into OCI Ollama, then run:

```bash
sudo bash deploy/systemd/install.sh /path/to/checked-out/trevor
sudo tailscale serve status --json
curl --fail http://127.0.0.1:5001/health/ready
```

The installer configures `tailscale serve --bg --https=443 http://127.0.0.1:5001`. Tailscale ACLs must restrict the node to the owner’s devices.

## Mac Edge

Bootstrap the local admin API key once, then install the rendered LaunchAgent with the OCI MagicDNS URL:

```bash
python tools/bootstrap_trevor_api_key.py
python tools/install_trevor_edge_launchagent.py \
  --remote-url https://trevor.example-tailnet.ts.net
```

Use `launchctl print gui/$(id -u)/com.trevor.edge` and `~/Library/Application Support/Trevor/edge/status.json` for health checks.

## Rollback

- Revert application changes with `python tools/trevor_operations.py rollback --commit <sha> --reason <reason>`; the command refuses dirty or non-protected branches and never force-resets.
- Restore Graphiti and data from the latest `/var/lib/trevor` snapshot.
- Verify `audit/events.jsonl` before and after rollback; a broken hash chain blocks autonomous work.
