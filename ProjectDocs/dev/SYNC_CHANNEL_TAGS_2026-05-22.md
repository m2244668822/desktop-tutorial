# Sync Channel Tags

## macOS Channel

- tag: `mac-sync`
- script: `tools/sync_ssd_to_hdd.sh`
- command:

```bash
./tools/sync_ssd_to_hdd.sh <SOURCE_DIR> <DEST_DIR>
```

## Windows / Microsoft Channel

- tag: `windows-sync`
- script: `tools/sync_workspace_windows.ps1`
- command:

```powershell
.\tools\sync_workspace_windows.ps1 -SourceDir "G:\城城城程式" -DestDir "D:\Backups\城城城程式"
```

## n8n Command Channel (Windows)

- tag: `windows-n8n-cmd`
- script: `tools/start_n8n_windows.cmd`
- command:

```powershell
.\tools\start_n8n_windows.cmd
```
