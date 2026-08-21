# AirLLM 安裝與相容性 Runbook

## 目的

在 Perob 工作區中提供獨立的 AirLLM 執行環境，用來測試低記憶體大型模型載入能力。這個環境不併入主 Web server runtime，避免 ML 依賴影響 `desktop_chat_app.py`、LangGraph、FAISS 與前端服務。

## 已驗證環境

| 項目 | 值 |
|---|---|
| 工作區 | `/Volumes/智能體/城城城程式` |
| AirLLM venv | `.venv-airllm` |
| Python | `3.12.13` |
| macOS CPU | Intel `x86_64` |
| AirLLM | `2.11.0` |
| Torch | `2.2.2` |
| Transformers | `4.48.3` |
| Optimum | `1.17.1` |
| NumPy | `1.26.4` |

## 為什麼不用主系統 Python

主系統目前是 Python 3.14，已知會觸發 Pydantic v1 warning。AirLLM 又依賴 PyTorch、Transformers、Optimum、NumPy，若直接灌進主 runtime，會讓前後端、LangGraph、RAG 和模型依賴互相污染。

生活化說法：主系統是正在營業的廚房，AirLLM 是重型模型實驗室；兩邊的工具不要混放，否則 Debug 時會分不清是哪個鍋子冒煙。

## 安裝指令

```bash
cd /Volumes/智能體/城城城程式
/Users/user/.local/bin/python3.12 -m venv .venv-airllm
.venv-airllm/bin/python -m pip install --upgrade pip setuptools wheel
.venv-airllm/bin/python -m pip install -r requirements-airllm.txt
.venv-airllm/bin/python tools/patch_airllm_intel_macos.py
.venv-airllm/bin/python tools/airllm_smoke_test.py
```

## Intel macOS 相容補丁

AirLLM `2.8.6+` 在 macOS 上會直接載入 MLX：

```python
if platform == "darwin":
    from .airllm_llama_mlx import AirLLMLlamaMlx
```

但 MLX 不支援本機 Intel `x86_64`，因此會出現：

```text
ModuleNotFoundError: No module named 'mlx'
```

本專案提供：

```bash
.venv-airllm/bin/python tools/patch_airllm_intel_macos.py
```

補丁邏輯：只有 Apple Silicon `arm64/aarch64` 才走 MLX；Intel macOS 改走 AirLLM 原本的非 MLX PyTorch 路線。

## 依賴版本原因

AirLLM 官方依賴範圍較寬，直接 `pip install airllm` 會在目前時間點裝到：

- `transformers 5.x`：會要求較新的 PyTorch，導致 `torch 2.2.2` 被停用。
- `optimum 2.x`：已移除 `optimum.bettertransformer`，但 AirLLM 還會 import。
- `numpy 2.x`：會和 `torch 2.2.2` 的 NumPy 1.x ABI 產生警告。

因此使用 `requirements-airllm.txt` 固定相容組合。

## 驗證

```bash
.venv-airllm/bin/python -m pip check
.venv-airllm/bin/python tools/airllm_smoke_test.py
```

成功時應看到：

```text
airllm_smoke=ok
```

## 使用提醒

1. 第一次載入模型會下載 HuggingFace 模型與 AirLLM 分層檔，請確認磁碟空間。
2. 不要在 Web request 主執行緒中同步下載或切分大型模型。
3. 若要接進 Perob，應做成背景 worker 或 sidecar，再由 OpenClaw/Lobster 或任務佇列調度。
4. `.venv-airllm` 已被 `.gitignore` 的 `.venv*/` 忽略，不應提交。
