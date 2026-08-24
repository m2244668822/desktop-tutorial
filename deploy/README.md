<!-- markdownlint-configure-file
{
  "MD013": {
    "line_length": 80,
    "code_blocks": false,
    "tables": false
  }
}
-->

# Trevor Deployment

## Trust Boundary

- API and Graphiti bind only to `127.0.0.1` on OCI.
- Tailscale Serve publishes the API only inside the tailnet; do not enable
  Funnel.
- Mutable state lives in `/var/lib/trevor`; secrets live in root-only systemd
  credential files.
- The Mac Edge Client stores failed requests in an AES-256-GCM encrypted queue
  and reads its API key from Keychain.

## OCI Credentials

Create `/etc/trevor/credentials` with owner `root:root` and mode `0700`. Add
these mode `0600` files without a trailing label or shell assignment:

- `nvidia_api_key`
- `gemini_api_key`
- `graphiti_token`
- `trevor_api_hmac`
- `trevor_memory_key_b64`
- `ai_horde_api_key`

Generate independent control secrets with `openssl rand -hex 32` for
`graphiti_token` and `trevor_api_hmac`. Generate `trevor_memory_key_b64` with
`openssl rand -base64 32`. Never copy these values into `.env` files.

## OCI Install

Prepare Python 3.12 environments at `/opt/trevor/app/.venv` and
`/opt/trevor/app/services/graphiti_sidecar/.venv`, pull `nomic-embed-text` into
OCI Ollama, then run:

```bash
sudo bash deploy/systemd/install.sh /path/to/checked-out/trevor
sudo tailscale serve status --json
curl --fail http://127.0.0.1:5001/health/ready
```

The installer configures
`tailscale serve --bg --https=443 http://127.0.0.1:5001`. Tailscale ACLs must
restrict the node to the owner’s devices.

## Migration Status

After both device and Graphiti migrations complete, generate the privacy-safe
status files before publishing migration state to OCI:

```bash
TREVOR_DISABLE_KEYCHAIN=true .venv312/bin/python -m core.migration_status \
  --source "$HOME/Library/Application Support/Trevor/migrations" \
  --destination /tmp/trevor-migration-status
```

Transfer only the two generated JSON files to `/var/lib/trevor/migrations` with
owner `trevor:trevor` and mode `0600`. Never transfer the source manifests:
they include device file inventory or per-turn content hashes that OCI does not
need.

## Mac Edge

Bootstrap the local admin API key once, then install the rendered LaunchAgent
with the OCI MagicDNS URL:

```bash
python tools/bootstrap_trevor_api_key.py \
  --remote-host opc@trevor.example-tailnet.ts.net \
  --ssh-key ~/.ssh/trevor_oci_ed25519
python tools/install_trevor_edge_launchagent.py \
  --remote-url https://trevor.example-tailnet.ts.net
```

The bootstrap command issues the key inside OCI's
`/var/lib/trevor/auth/api_keys.json` using OCI's HMAC credential, transfers the
one-time plaintext only over the SSH channel, and stores it in the Mac
Keychain. It never creates an incompatible Mac-local server key record.

Use `launchctl print gui/$(id -u)/com.trevor.edge` and
`~/Library/Application Support/Trevor/edge/status.json` for health checks.

## Mac Autonomy Fallback

OCI remains the primary autonomy host. When OCI is unavailable, install the
local combined scheduler and worker as a supervised LaunchAgent:

```bash
.venv312/bin/python tools/install_trevor_autonomy_launchagent.py
launchctl print gui/$(id -u)/com.trevor.autonomy
curl --fail --silent http://127.0.0.1:5001/api/trevor/status \
  | python3 -c "import json,sys; payload=json.load(sys.stdin); raise SystemExit(0 if payload['autonomy']['ready'] else 1)"
```

The rendered plist contains paths and non-secret policy settings only. Provider
and memory credentials resolve from the private
`~/Library/Application Support/Trevor/credentials` directory, mutable state
remains under `TREVOR_DATA_DIR`, and launchd restarts the daemon after any exit.
External-volume workspaces use the non-interactive Terminal-safe manager
instead of loading inaccessible paths into launchd.

## Rollback

- Revert application changes with
  `python tools/trevor_operations.py rollback --commit <sha> --reason <reason>`;
  the command refuses dirty or non-protected branches and never force-resets.
- Restore Graphiti and data from the latest `/var/lib/trevor` snapshot.
- Verify `audit/events.jsonl` before and after rollback; a broken hash chain
  blocks autonomous work.
