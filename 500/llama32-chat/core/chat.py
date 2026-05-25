import json
import sys
import os
import argparse
import time
import subprocess
from pathlib import Path
import openai
import requests
from google import genai

try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️  Anthropic SDK 未安裝，Claude 功能不可用。安裝方式: pip install anthropic")

try:
    from groq import Groq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    print("⚠️  Groq SDK 未安裝。安裝方式: pip install groq")

# 添加父目录到 sys.path 以支持模块导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.agent import agent
from agents.task_manager import task_manager
from core.autonomous_agent import autonomous_agent
from core.constants import *
from core.utils import TimeHelper, PrintHelper, StringHelper
from learning.rag_pipeline import RAGPipeline, SimpleRAG, create_rag_pipeline

# API URLs and Keys
OLLAMA_URL = os.getenv("OLLAMA_URL", DEFAULT_OLLAMA_URL)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
XAI_API_KEY = os.getenv("XAI_API_KEY")
CUSTOM_API_URL = os.getenv("CUSTOM_API_URL")
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY")
CUSTOM_API_HEADERS = os.getenv("CUSTOM_API_HEADERS")
CUSTOM_API_METHOD = os.getenv("CUSTOM_API_METHOD", "POST")
CUSTOM_API_TIMEOUT = os.getenv("CUSTOM_API_TIMEOUT")
CUSTOM_API_REQUEST_TEMPLATE = os.getenv("CUSTOM_API_REQUEST_TEMPLATE")
CUSTOM_API_RESPONSE_PATH = os.getenv("CUSTOM_API_RESPONSE_PATH", "text")
CUSTOM_API_MODEL = os.getenv("CUSTOM_API_MODEL")

# 設定 Gemini (使用新的 API)
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# 設定 Groq
if GROQ_AVAILABLE and GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)

# 設定 Claude (Anthropic)
if ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY:
    anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)


def is_ollama_running(url=OLLAMA_URL):
    """檢查 Ollama 是否正在運行"""
    try:
        response = requests.get(f"{url}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False


def start_ollama():
    """啟動 Ollama 服務"""
    print("🚀 正在啟動 Ollama 服務...")
    try:
        # 在後台啟動 Ollama
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # 等待服務啟動（最多等待 15 秒）
        for i in range(15):
            time.sleep(1)
            if is_ollama_running():
                print("✅ Ollama 服務已成功啟動！")
                return True
            print(f"   等待中... ({i + 1}/15)")

        print("⚠️  Ollama 啟動超時，但會繼續嘗試連接")
        return False

    except Exception as e:
        print(f"⚠️  啟動 Ollama 時發生錯誤: {e}")
        print("   提示：請確認已安裝 Ollama (https://ollama.ai)")
        return False


def ensure_ollama_running():
    """確保 Ollama 正在運行"""
    print("🔍 檢查 Ollama 服務狀態...")

    if is_ollama_running():
        print("✅ Ollama 服務已在運行中")
        return True
    else:
        print("⚠️  Ollama 服務未運行")
        return start_ollama()


def _call_ollama(prompt: str, model: str = None) -> str:
    """調用 Ollama 模型（增強穩定性版本）"""
    model = model or os.getenv("MODEL", DEFAULT_MODELS["ollama"])
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }

    # 加強重試機制
    max_retries = OLLAMA_MAX_RETRIES
    for attempt in range(max_retries + 1):
        try:
            # 分開連接超時和讀取超時
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_TIMEOUT),
                stream=True,
            )
            response.raise_for_status()

            full_content = ""
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line.decode("utf-8"))
                        if data.get("done", False):
                            break
                        if "message" in data and "content" in data["message"]:
                            content = data["message"]["content"]
                            sys.stdout.write(content)
                            sys.stdout.flush()
                            full_content += content
                    except json.JSONDecodeError:
                        continue
            print()
            return full_content

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries:
                wait_time = 2**attempt  # 指數退避：1秒、2秒
                print(
                    f"\n⚠️  Ollama 連線失敗 (嘗試 {attempt + 1}/{max_retries + 1})，{wait_time}秒後重試...",
                    file=sys.stderr,
                )
                time.sleep(wait_time)
            else:
                raise  # 最後一次嘗試失敗，拋出異常
        except requests.exceptions.HTTPError as e:
            # HTTP 錯誤不重試（如 404, 500 等）
            raise


def _call_openai(
    prompt: str, model: str = None, api_key: str = None, base_url: str = None
) -> str:
    """調用 OpenAI 兼容的 API"""
    model = model or DEFAULT_MODELS["openai"]
    api_key = api_key or OPENAI_API_KEY

    if not api_key:
        raise ValueError("API_KEY 未設定")

    client = (
        openai.OpenAI(api_key=api_key, base_url=base_url)
        if base_url
        else openai.OpenAI(api_key=api_key)
    )

    response = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}], stream=True
    )

    full_response = ""
    for chunk in response:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            sys.stdout.write(content)
            sys.stdout.flush()
            full_response += content
    print()
    return full_response


def _call_gemini(prompt: str, model: str = None) -> str:
    """調用 Gemini 模型 (使用新的 google.genai API)"""
    model = model or DEFAULT_MODELS["gemini"]

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY 未設定")

    response = gemini_client.models.generate_content(model=model, contents=prompt)

    # 防禦性處理：處理可能返回的元組
    res_obj = (
        response[0] if isinstance(response, tuple) and len(response) > 0 else response
    )

    # 新 API 直接返回文本，不是流式
    full_response = res_obj.text if hasattr(res_obj, "text") else str(res_obj)
    sys.stdout.write(full_response)
    sys.stdout.flush()
    print()
    return full_response


def _call_groq(prompt: str, model: str = None) -> str:
    """調用 Groq 模型 (超快速推理)"""
    if not GROQ_AVAILABLE:
        raise ValueError("Groq SDK 未安裝，請執行: pip install groq")

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY 未設定")

    model = model or DEFAULT_MODELS["groq"]

    try:
        message = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            temperature=0.7,
            max_tokens=512,
        )

        full_response = message.choices[0].message.content
        sys.stdout.write(full_response)
        sys.stdout.flush()
        print()
        return full_response
    except Exception as e:
        print(f"❌ Groq 調用失敗: {str(e)}")
        raise


def _call_claude(prompt: str, model: str = None) -> str:
    """調用 Anthropic Claude 模型"""
    model = model or DEFAULT_MODELS["claude"]

    if not ANTHROPIC_AVAILABLE:
        raise ValueError("Anthropic SDK 未安裝，請執行: pip install anthropic")

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY 未設定")

    # 使用 Claude API
    response = anthropic_client.messages.create(
        model=model, max_tokens=4096, messages=[{"role": "user", "content": prompt}]
    )

    # 提取回應文本
    full_response = response.content[0].text
    sys.stdout.write(full_response)
    sys.stdout.flush()
    print()
    return full_response


def _parse_headers(raw_headers: str) -> dict:
    if not raw_headers:
        return {}
    try:
        return json.loads(raw_headers)
    except json.JSONDecodeError as exc:
        raise ValueError("CUSTOM_API_HEADERS must be valid JSON") from exc


def _render_template(value, prompt: str, model: str):
    if isinstance(value, str):
        return value.replace("{prompt}", prompt).replace("{model}", model)
    if isinstance(value, list):
        return [_render_template(v, prompt, model) for v in value]
    if isinstance(value, dict):
        return {k: _render_template(v, prompt, model) for k, v in value.items()}
    return value


def _build_custom_payload(prompt: str, model: str) -> dict:
    if CUSTOM_API_REQUEST_TEMPLATE:
        try:
            template = json.loads(CUSTOM_API_REQUEST_TEMPLATE)
        except json.JSONDecodeError as exc:
            raise ValueError("CUSTOM_API_REQUEST_TEMPLATE must be valid JSON") from exc
        return _render_template(template, prompt, model)

    return {"model": model, "prompt": prompt}


def _extract_by_path(data, path: str):
    if not path:
        return data

    normalized = path.replace("[", ".").replace("]", "")
    parts = [p for p in normalized.split(".") if p]
    current = data
    for part in parts:
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
        elif isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            return None
    return current


def _call_custom(prompt: str, model: str = None) -> str:
    if not CUSTOM_API_URL:
        raise ValueError("CUSTOM_API_URL 未設定")

    model = model or CUSTOM_API_MODEL or DEFAULT_MODELS["custom"]
    timeout = int(CUSTOM_API_TIMEOUT) if CUSTOM_API_TIMEOUT else DEFAULT_TIMEOUT
    headers = {"Content-Type": "application/json"}

    if CUSTOM_API_KEY and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {CUSTOM_API_KEY}"

    headers.update(_parse_headers(CUSTOM_API_HEADERS))
    payload = _build_custom_payload(prompt, model)

    response = requests.request(
        CUSTOM_API_METHOD.upper(),
        CUSTOM_API_URL,
        json=payload,
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    content = _extract_by_path(data, CUSTOM_API_RESPONSE_PATH)
    if content is None:
        raise ValueError("CUSTOM_API_RESPONSE_PATH 找不到內容")

    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    sys.stdout.write(content)
    sys.stdout.flush()
    print()
    return content


def _prepare_rag_pipeline(args) -> RAGPipeline:
    pipeline = create_rag_pipeline(
        db_dir=Path(args.rag_db),
        collection_name=args.rag_collection,
        embed_model=args.rag_embed_model,
        prefer_chroma=True,
    )

    if isinstance(pipeline, SimpleRAG):
        print("RAG: Chroma not available, using stdlib TF-IDF fallback.")

    if args.rag_rebuild:
        pipeline.index_conversations(CONVERSATION_FILE, rebuild=True)
    else:
        pipeline.ensure_index(CONVERSATION_FILE)

    return pipeline


def _apply_rag(prompt: str, pipeline: RAGPipeline, top_k: int) -> str:
    if not pipeline:
        return prompt

    retrieved = pipeline.retrieve(prompt, top_k=top_k)
    context = pipeline.format_context(retrieved)
    if not context:
        return prompt

    return f"{context}\n\n# User question\n{prompt}"


def chat_with_model(
    model_name: str,
    prompt: str,
    custom_model: str = None,
    conversation_history: list = None,
) -> str:
    """
    統一的模型調用接口 - 消除重複代碼（支援對話歷史）

    Args:
        model_name: 模型名稱 ('ollama', 'openai', 'gemini', 'xai')
        prompt: 用戶提示詞
        custom_model: 自定義模型名稱（可選）
        conversation_history: 對話歷史列表 [{"role": "user/assistant", "content": "..."}]（可選）

    Returns:
        模型的回應文本，或 None 如果失敗
    """
    start_time = time.time()

    # 如果有對話歷史，將prompt與歷史結合
    if conversation_history:
        # 構建完整的上下文提示
        context_lines = []
        for msg in conversation_history[-10:]:  # 保留最近10輪對話
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                context_lines.append(f"User: {content}")
            else:
                context_lines.append(f"Assistant: {content}")

        # 添加當前問題
        context_lines.append(f"\nUser: {prompt}")
        full_prompt = "\n".join(context_lines) + "\n\nAssistant:"
    else:
        full_prompt = prompt

    try:
        if model_name == "ollama":
            response = _call_ollama(full_prompt, custom_model)
        elif model_name == "openai":
            response = _call_openai(
                full_prompt,
                custom_model or os.getenv("OPENAI_MODEL") or DEFAULT_MODELS["openai"],
                OPENAI_API_KEY,
                OPENAI_BASE_URL,
            )
        elif model_name == "gemini":
            response = _call_gemini(
                full_prompt, custom_model or DEFAULT_MODELS["gemini"]
            )
        elif model_name == "groq":
            response = _call_groq(full_prompt, custom_model or DEFAULT_MODELS["groq"])
        elif model_name == "claude":
            response = _call_claude(
                full_prompt, custom_model or DEFAULT_MODELS["claude"]
            )
        elif model_name == "xai":
            response = _call_openai(
                full_prompt,
                custom_model or DEFAULT_MODELS["xai"],
                XAI_API_KEY,
                DEFAULT_XAI_BASE_URL,
            )
        elif model_name == "custom":
            response = _call_custom(full_prompt, custom_model)
        else:
            raise ValueError(f"未知的模型: {model_name}")

        # 記錄成功
        response_time = time.time() - start_time
        autonomous_agent.record_success(model_name, response_time)
        agent.save_conversation(model_name, prompt, response)

        return response

    except ValueError as e:
        error_msg = str(e)
        print(f"配置錯誤 ({model_name}): {error_msg}", file=sys.stderr)
        autonomous_agent.record_failure(model_name, error_msg)
        agent.log_error(model_name, prompt, "ConfigError", error_msg)
        return None
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        print(f"連接錯誤 ({model_name}): {error_msg}", file=sys.stderr)
        autonomous_agent.record_failure(model_name, error_msg)
        agent.log_error(model_name, prompt, "ConnectionError", error_msg)
        return None
    except Exception as e:
        error_msg = str(e)
        print(f"錯誤 ({model_name}): {error_msg}", file=sys.stderr)
        autonomous_agent.record_failure(model_name, error_msg)
        agent.log_error(model_name, prompt, type(e).__name__, error_msg)
        return None


# ============ 保留的舊函數（為了向後兼容） ============
def chat_with_ollama(prompt, model=None):
    """（已過時）使用 chat_with_model 替代"""
    return chat_with_model("ollama", prompt, model)


def chat_with_openai(prompt, model=None):
    """（已過時）使用 chat_with_model 替代"""
    return chat_with_model("openai", prompt, model)


def chat_with_gemini(prompt, model=None):
    """（已過時）使用 chat_with_model 替代"""
    return chat_with_model("gemini", prompt, model)


def chat_with_xai(prompt, model=None):
    """（已過時）使用 chat_with_model 替代"""
    return chat_with_model("xai", prompt, model)


def smart_chat(
    prompt, preferred_model=None, enable_failover=True, conversation_history=None
):
    """
    智能聊天：自動選擇最佳模型並支持故障轉移（支援對話歷史）

    Args:
        prompt: 用戶提示詞
        preferred_model: 用戶偏好的模型（可選）
        enable_failover: 是否啟用自動故障轉移
        conversation_history: 對話歷史列表（可選）

    Returns:
        回應內容或 None
    """
    # 使用自主代理決定最佳模型
    chosen_model = autonomous_agent.decide_best_model(prompt, preferred_model)

    if chosen_model != preferred_model and preferred_model:
        print(f"\n🤖 智能選擇：使用 {chosen_model}（原選擇：{preferred_model}）")

    # 嘗試執行（傳遞對話歷史）
    result = chat_with_model(
        chosen_model, prompt, conversation_history=conversation_history
    )

    # 如果失敗且啟用故障轉移
    if result is None and enable_failover:
        failover_info = autonomous_agent.auto_failover(
            chosen_model, prompt, "模型返回空結果"
        )

        if failover_info:
            backup_model, _ = failover_info
            result = chat_with_model(
                backup_model, prompt, conversation_history=conversation_history
            )

            # 如果備用模型也失敗，嘗試最後一次
            if result is None:
                remaining_models = [
                    m for m in AVAILABLE_MODELS if m not in [chosen_model, backup_model]
                ]
                for fallback_model in remaining_models:
                    if autonomous_agent._is_model_healthy(fallback_model):
                        print(f"\n🔄 最後嘗試：{fallback_model}")
                        result = chat_with_model(
                            fallback_model,
                            prompt,
                            conversation_history=conversation_history,
                        )
                        if result:
                            break

    return result


def round_table_chat(prompt, models):
    """圓桌模式：多個模型輪流互動（改進版，使用統一接口）"""
    conversation = prompt
    print("\n" + "=" * 60)
    print("🎯 【圓桌討論模式】")
    print("=" * 60 + "\n")

    for model in models:
        print(f"\n--- {model.upper()} 的回應 ---")
        response = chat_with_model(model, conversation)

        if response:
            conversation += f"\n\n{model.upper()}: {response}"
        else:
            print(f"模型 {model} 返回空結果")

    print("\n" + "=" * 60)
    print("✅ 【圓桌討論結束】")
    print("=" * 60 + "\n")


def interactive_round_table_chat(prompt, models, rounds=None):
    """持續互動圓桌模式：多個模型互相討論多輪

    Args:
        prompt: 初始問題
        models: 模型列表
        rounds: 討論輪數（如果為 None，則無限制，用戶按 Ctrl+C 結束）
    """
    conversation = f"話題：{prompt}\n\n"

    print("\n" + "=" * 80)
    print("🎪 【持續互動圓桌討論模式】")
    print("=" * 80)
    print(f"📌 話題：{prompt}")
    print(f"🤖 參與者：{', '.join([m.upper() for m in models])}")
    if rounds:
        print(f"📊 討論輪數：{rounds} 輪")
    else:
        print("📊 討論輪數：無限制（按 Ctrl+C 結束）")
    print("=" * 80 + "\n")

    round_num = 0
    max_rounds = rounds or float("inf")

    try:
        while round_num < max_rounds:
            round_num += 1
            print(f"\n{'=' * 80}")
            print(f"🔄 第 {round_num} 輪討論")
            print(f"{'=' * 80}")

            all_empty = True
            for model in models:
                print(f"\n🎤 {model.upper()} 的觀點：")
                print("-" * 60)
                response = chat_with_model(model, conversation)

                if response:
                    all_empty = False
                    conversation += f"\n【{model.upper()} 說】\n{response}\n"
                else:
                    print(f"⚠️  {model.upper()} 暫時無法回應")

            if all_empty:
                print("\n⚠️  本輪所有模型都無法回應，討論結束")
                break

            # 如果是無限制模式，詢問是否繼續
            if max_rounds == float("inf"):
                user_input = (
                    input(f"\n➡️  是否繼續下一輪討論？(y/是 繼續，n/否 結束): ")
                    .strip()
                    .lower()
                )
                if user_input in ["n", "no", "否", "n"]:
                    break

        # 討論結束
        print(f"\n{'=' * 80}")
        print(f"✨ 【圓桌討論結束】({round_num} 輪)")
        print(f"{'=' * 80}\n")

        # 顯示完整對話
        print("📝 完整對話記錄：")
        print("▼" * 40)
        print(conversation)
        print("▲" * 40)

    except KeyboardInterrupt:
        print(f"\n\n⏹️  討論被中斷（進行了 {round_num} 輪）")
        print(f"{'=' * 80}\n")


def user_participates_round_table(initial_topic, models):
    """用戶參與圓桌討論：用戶和 AI 模型輪流對話

    Args:
        initial_topic: 初始話題
        models: AI 模型列表
    """
    conversation = f"話題：{initial_topic}\n\n"

    print("\n" + "=" * 80)
    print("🎪 【互動圓桌討論 - 用戶參與模式】")
    print("=" * 80)
    print(f"📌 話題：{initial_topic}")
    print(f"🤖 參與者：您 + {', '.join([m.upper() for m in models])}")
    print("💡 輸入 'exit'、'quit' 或 '結束' 退出討論")
    print("=" * 80 + "\n")

    round_num = 0

    try:
        while True:
            round_num += 1
            print(f"\n{'=' * 80}")
            print(f"🔄 第 {round_num} 輪討論")
            print(f"{'=' * 80}")

            # 用戶發言
            print(f"\n👤 請輸入您的觀點：")
            user_input = input("您: ").strip()

            # 檢查是否退出
            if user_input.lower() in ["exit", "quit", "結束", "bye", "退出"]:
                print("\n👋 感謝參與討論！")
                break

            if user_input:
                conversation += f"\n【您說】\n{user_input}\n"
                print(f"✓ 已記錄您的觀點")
            else:
                print("⚠️  您沒有輸入內容，跳過本輪")
                continue

            # AI 模型輪流回應
            for model in models:
                print(f"\n🎤 {model.upper()} 的回應：")
                print("-" * 60)
                response = chat_with_model(model, conversation)

                if response:
                    conversation += f"\n【{model.upper()} 說】\n{response}\n"
                else:
                    print(f"⚠️  {model.upper()} 暫時無法回應")

        # 討論結束
        print(f"\n{'=' * 80}")
        print(f"✨ 【圓桌討論結束】({round_num} 輪)")
        print(f"{'=' * 80}\n")

        # 顯示完整對話
        print("📝 完整對話記錄：")
        print("▼" * 40)
        print(conversation)
        print("▲" * 40)

    except KeyboardInterrupt:
        print(f"\n\n⏹️  討論被中斷（進行了 {round_num} 輪）")
        print(f"{'=' * 80}\n")


def execute_tasks_mode(rag_pipeline=None, rag_topk: int = 5):
    """執行任務模式 - 自動檢測並執行所有待處理任務（支持自動故障轉移）"""
    tasks = task_manager.get_all_pending_tasks()

    if not tasks:
        print("\n✓ 沒有待處理任務\n")
        return

    print(f"\n🚀 開始執行 {len(tasks)} 個待處理任務（自主決策模式）...\n")

    for task in sorted(tasks, key=lambda x: x["priority"]):
        task_id = task["id"]
        model = task["model"]
        prompt = task["prompt"]

        # 開始任務
        task_manager.start_task(task_id)

        # 使用智能聊天（自動故障轉移）
        result = None
        try:
            rag_prompt = _apply_rag(prompt, rag_pipeline, rag_topk)
            result = smart_chat(rag_prompt, preferred_model=model, enable_failover=True)

            if result:
                # 任務成功
                task_manager.complete_task(task_id, result)
                # 模型已經在 chat_with_* 函數中保存了對話
            else:
                # 任務失敗
                task_manager.fail_task(task_id, "所有模型均返回空結果")

        except Exception as e:
            # 任務失敗
            error_msg = str(e)
            task_manager.fail_task(task_id, error_msg)

    print("\n✅ 所有任務已執行完畢！\n")


def interactive_mode(
    model_name="ollama",
    ollama_model=None,
    openai_model=None,
    gemini_model=None,
    xai_model=None,
    rag_pipeline=None,
    rag_topk: int = 5,
):
    """互動模式：持續對話（支援輸入確認和對話歷史）"""
    ollama_model = ollama_model or DEFAULT_MODELS["ollama"]
    openai_model = openai_model or DEFAULT_MODELS["openai"]
    gemini_model = gemini_model or DEFAULT_MODELS["gemini"]
    xai_model = xai_model or DEFAULT_MODELS["xai"]

    print(f"\n🤖 互動模式啟動（使用 {model_name.upper()}）")
    print("=" * 60)
    print("💡 使用說明：")
    print("  • 輸入問題後，系統會顯示預覽並詢問是否確認")
    print("  • 輸入 'n' 或 '否' 可以重新輸入")
    print("  • 輸入 'exit'、'quit' 或 'bye' 結束對話")
    print("  • 輸入 'redo' 或 '重來' 可以重新輸入上一句")
    print("  • 輸入 'history' 或 '歷史' 查看本次對話記錄")
    print("  • 切換模型時，系統會自動保留對話上下文")
    print("=" * 60 + "\n")

    last_input = None  # 記錄上一次的輸入
    conversation_history = []  # 維護對話歷史

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # 檢查歷史查看命令
            if user_input.lower() in ["history", "歷史", "查看歷史"]:
                print(f"\n📚 本次對話歷史（共 {len(conversation_history)} 條）：")
                print("=" * 60)
                for i, msg in enumerate(conversation_history, 1):
                    role = "用戶" if msg["role"] == "user" else "AI"
                    content = (
                        msg["content"][:100] + "..."
                        if len(msg["content"]) > 100
                        else msg["content"]
                    )
                    print(f"{i}. [{role}] {content}")
                print("=" * 60 + "\n")
                continue

            # 檢查重來命令
            if user_input.lower() in ["redo", "重來", "重新輸入"] and last_input:
                print(f"\n📝 重新輸入上一句：「{last_input}」")
                user_input = input("You (重新輸入): ").strip()
                if not user_input:
                    continue

            # 檢查退出命令
            if user_input.lower() in ["exit", "quit", "bye", "退出", "再見"]:
                print(
                    f"\n📊 對話統計：共進行了 {len(conversation_history) // 2} 輪對話"
                )
                print("👋 再見！")
                break

            # 顯示輸入預覽並確認
            print(f"\n📋 您的輸入：「{user_input}」")
            confirm = (
                input("✅ 確認送出？(直接按 Enter 或輸入 y/是，輸入 n/否 重新輸入): ")
                .strip()
                .lower()
            )

            # 如果用戶要重新輸入
            if confirm in ["n", "no", "否", "不"]:
                print("🔄 請重新輸入：")
                continue

            # 記錄這次輸入（供 redo 使用）
            last_input = user_input

            # 添加到對話歷史
            conversation_history.append({"role": "user", "content": user_input})

            # 應用RAG增強（如果啟用）
            rag_prompt = _apply_rag(user_input, rag_pipeline, rag_topk)

            # 發送給 AI（使用智能聊天，傳遞對話歷史）
            print(f"\n💬 AI ({model_name.upper()}): ", end="", flush=True)
            response = smart_chat(
                rag_prompt,
                preferred_model=model_name,
                enable_failover=True,
                conversation_history=conversation_history,
            )

            # 如果有回應，添加到歷史
            if response:
                conversation_history.append({"role": "assistant", "content": response})
                print("\n" + "-" * 60)  # 分隔線
                print(
                    f"📊 本次對話第 {len(conversation_history) // 2} 輪 | 歷史記錄: {len(conversation_history)} 條"
                )
                print("-" * 60)
            else:
                print("\n⚠️  AI 未能生成回應")
                # 如果失敗，從歷史中移除用戶輸入
                conversation_history.pop()

        except KeyboardInterrupt:
            print(f"\n\n📊 對話統計：共進行了 {len(conversation_history) // 2} 輪對話")
            print("👋 對話中斷，再見！")
            break
        except EOFError:
            print(f"\n\n📊 對話統計：共進行了 {len(conversation_history) // 2} 輪對話")
            print("👋 再見！")
            break


def main():
    # 自動啟動 Ollama
    ensure_ollama_running()

    parser = argparse.ArgumentParser(description="多模型聊天程式（自主決策版）")
    parser.add_argument("prompt", nargs="?", help="聊天提示")
    parser.add_argument(
        "--model", choices=AVAILABLE_MODELS, default=DEFAULT_MODEL, help="選擇模型"
    )
    parser.add_argument(
        "--round-table",
        nargs="+",
        choices=AVAILABLE_MODELS,
        help="圓桌模式：指定多個模型輪流討論一次",
    )
    parser.add_argument(
        "--continuous-round-table",
        "-crt",
        nargs="+",
        choices=AVAILABLE_MODELS,
        help="持續圓桌模式：指定多個模型互相討論多輪",
    )
    parser.add_argument(
        "--user-round-table",
        "-urt",
        nargs="+",
        choices=AVAILABLE_MODELS,
        help="用戶參與圓桌：您和 AI 模型輪流討論",
    )
    parser.add_argument(
        "--round-rounds",
        type=int,
        default=None,
        help="討論輪數（默認無限制，按 Ctrl+C 結束）",
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="互動模式：持續對話"
    )
    parser.add_argument(
        "--tasks", action="store_true", help="任務執行模式：自動執行所有待處理任務"
    )
    parser.add_argument(
        "--monitor-tasks", action="store_true", help="任務監控模式：查看任務狀態"
    )
    parser.add_argument(
        "--live-monitor", action="store_true", help="實時監控模式：持續顯示系統狀態"
    )
    parser.add_argument(
        "--model-stats", action="store_true", help="顯示模型統計和健康狀態"
    )
    parser.add_argument("--health-check", action="store_true", help="執行模型健康檢查")
    parser.add_argument(
        "--disable-failover", action="store_true", help="禁用自動故障轉移"
    )
    parser.add_argument(
        "--ollama-model", default=DEFAULT_MODELS["ollama"], help="Ollama 模型名稱"
    )
    parser.add_argument(
        "--openai-model", default=DEFAULT_MODELS["openai"], help="OpenAI 模型名稱"
    )
    parser.add_argument(
        "--gemini-model", default=DEFAULT_MODELS["gemini"], help="Gemini 模型名稱"
    )
    parser.add_argument(
        "--xai-model", default=DEFAULT_MODELS["xai"], help="xAI Grok 模型名稱"
    )
    parser.add_argument(
        "--custom-model", default=DEFAULT_MODELS["custom"], help="自訂 API 模型名稱"
    )
    parser.add_argument("--rag", action="store_true", help="啟用 RAG 檢索")
    parser.add_argument("--rag-rebuild", action="store_true", help="重建 RAG 索引")
    parser.add_argument("--rag-topk", type=int, default=5, help="RAG 檢索筆數")
    parser.add_argument("--rag-db", default=str(RAG_DB_DIR), help="RAG 向量庫目錄")
    parser.add_argument(
        "--rag-collection", default=RAG_COLLECTION, help="RAG collection 名稱"
    )
    parser.add_argument(
        "--rag-embed-model", default=RAG_EMBED_MODEL, help="RAG 嵌入模型"
    )

    args = parser.parse_args()

    rag_pipeline = None
    if args.rag:
        try:
            rag_pipeline = _prepare_rag_pipeline(args)
        except Exception as e:
            print(f"RAG 初始化失敗: {e}", file=sys.stderr)
            sys.exit(1)

    # 實時監控模式
    if args.live_monitor:
        from monitor import Monitor

        Monitor.live_monitor(refresh_interval=3)
    # 模型統計
    elif args.model_stats:
        print("\n" + "=" * 60)
        print("📊 模型統計和健康狀態")
        print("=" * 60)
        stats = autonomous_agent.get_model_statistics()
        for model, data in stats.items():
            print(f"\n🤖 {model.upper()}")
            for key, value in data.items():
                print(f"   {key}: {value}")
        print("\n" + "=" * 60 + "\n")
    # 健康檢查
    elif args.health_check:
        print("\n" + "=" * 60)
        print("🏥 模型健康檢查")
        print("=" * 60)
        health = autonomous_agent.health_check()
        for model, status in health.items():
            icon = "✅" if status["healthy"] else "⚠️"
            print(f"\n{icon} {model.upper()}")
            print(f"   健康: {'是' if status['healthy'] else '否'}")
            print(f"   連續失敗: {status['consecutive_failures']} 次")
            print(f"   最後失敗: {status['last_failure']}")
        print("\n" + "=" * 60 + "\n")
    # 任務監控模式
    elif args.monitor_tasks:
        from task_monitor import TaskMonitor

        monitor = TaskMonitor()
        monitor.show_all()
    # 任務執行模式
    elif args.tasks:
        execute_tasks_mode(rag_pipeline=rag_pipeline, rag_topk=args.rag_topk)
    # 互動模式
    elif args.interactive:
        interactive_mode(
            args.model,
            args.ollama_model,
            args.openai_model,
            args.gemini_model,
            args.xai_model,
            rag_pipeline,
            args.rag_topk,
        )
    # 用戶參與圓桌模式
    elif args.user_round_table:
        if not args.prompt:
            print("用戶圓桌模式需要提供初始話題", file=sys.stderr)
            sys.exit(1)
        user_participates_round_table(args.prompt, args.user_round_table)
    # 持續圓桌模式
    elif args.continuous_round_table:
        if not args.prompt:
            print("持續圓桌模式需要提供提示", file=sys.stderr)
            sys.exit(1)
        interactive_round_table_chat(
            args.prompt, args.continuous_round_table, args.round_rounds
        )
    # 圓桌模式
    elif args.round_table:
        if not args.prompt:
            print("圓桌模式需要提供提示", file=sys.stderr)
            sys.exit(1)
        round_table_chat(args.prompt, args.round_table)
    # 單次問答（使用智能聊天）
    else:
        if not args.prompt:
            print('用法：python chat.py "你的問題" [--model 模型]')
            print("或使用：python chat.py --interactive 進入互動模式")
            print("新功能：python chat.py --model-stats  查看模型統計")
            print("       python chat.py --health-check 健康檢查")
            sys.exit(1)
        # 使用智能聊天（支持自動故障轉移）
        enable_failover = not args.disable_failover
        rag_prompt = _apply_rag(args.prompt, rag_pipeline, args.rag_topk)
        smart_chat(
            rag_prompt, preferred_model=args.model, enable_failover=enable_failover
        )

    # 安全關閉智能體
    agent.shutdown()


if __name__ == "__main__":
    main()
