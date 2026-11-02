# Trevor 第一課「壓力不是命令」Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在現有 Trevor 桌面／網頁文字對話中，加入單人 Phase 0 的第一課「壓力不是命令」，以對話流程收集五格紀錄，保持非診斷性，並在安全訊號出現時暫停課程而不強化未驗證敘事。

**Architecture:** 新增一個無外部副作用的 `RecoveryLessonEngine`，負責第一課的欄位順序、狀態轉換與安全暫停；現有 `SessionConversationStore` 只保存 session-scoped lesson state，不升格成長期記憶。`DesktopBridge.send_message` 在既有安全評估之後接入 lesson workflow，並把結構化的 lesson context 傳給既有 LLM prompt builder；若模型不可用，使用 engine 的 deterministic fallback。

**Tech Stack:** Python 3、dataclasses、現有 `pytest` 測試架構、既有 `SafetySignalTracker`、`SessionConversationStore`、`build_trevor_system_prompt`；不新增第三方套件。

**Spec:** `docs/superpowers/specs/2026-11-02-trevor-recovery-learning-lab-design.md`

## Global Constraints

- 本次只做單人 Phase 0，不開放外部測試者、帳號系統或即時真人監看。
- 介面限定桌面／網頁文字對話，不做硬體、推播、自動聯絡或自動救援。
- 第一課只使用五個欄位：`event`、`expectation`、`inner_content`、`evidence`、`next_step`。
- `SafetySignalTracker` 只提供非診斷性觀察；不得把訊號轉成診斷、身份或確定因果。
- 家庭壓力只可標示為可能脈絡或假說，不得寫成精神症狀的唯一原因。
- 「內在聲音」必須保持現象描述；系統不得確認為神諭、外部訊息或命令，也不得在資訊不足時替使用者診斷。
- 基督教語彙不是第一課必要條件；未明確 opt-in 時不得自動引入聖經、神學、寬恕或贖罪語言。
- 五格紀錄只保留在 session state，不自動寫入長期記憶或 training overlay。
- 任何明確 immediate danger 都優先進入安全暫停；不可繼續用一般教學語氣推進 lesson。

## File Map

- Create: `core/recovery_lesson.py` — 第一課的資料結構、欄位流程、安全暫停與 prompt context。
- Modify: `core/session_context.py` — 增加 session-scoped lesson state 的深拷貝讀寫與清除介面。
- Modify: `core/conversation_prompt.py` — 增加第一課 prompt contract，保留現有一般對談 prompt 的行為。
- Modify: `desktop_chat_app.py` — 將第一課接入 `DesktopBridge.send_message`，並將 lesson context 傳入既有 LLM 生成流程。
- Create: `tests/test_recovery_lesson.py` — engine 的 TDD 測試。
- Modify: `tests/test_session_conversation_store.py` — lesson state 隔離、深拷貝與清除測試。
- Modify: `tests/test_conversation_prompt.py` — lesson prompt 與 opt-in 邊界測試；若檔案不存在則建立。
- Create: `tests/test_recovery_lesson_integration.py` — DesktopBridge lesson hook 的狀態與安全暫停測試。

## Review Focus

1. **未標記的自然語言**：使用者不照五格格式回答時，系統應把內容放進目前欄位並只追問一個下一步問題，而不是自行補寫未提供的事實；測試在 Task 1。
2. **空白或只有標點的回答**：不得推進欄位或產生假紀錄；測試在 Task 1。
3. **安全訊號中斷**：immediate danger 出現時不得呼叫一般 lesson prompt 或 LLM，應回傳安全暫停；測試在 Task 1 與 Task 4。
4. **內在聲音／指涉感**：回應可承認感受，但不得確認外部訊息、神諭、使命或診斷；測試在 Task 1 與 Task 3。
5. **信仰模式未同意**：未 opt-in 時不得產生基督教詮釋；測試在 Task 3。

---

### Task 1: 建立第一課的純邏輯 engine

**Files:**
- Create: `core/recovery_lesson.py`
- Test: `tests/test_recovery_lesson.py`

**Interfaces:**
- Consumes: `core.safety_signals.SafetyAssessment`；輸入為 session 內的單輪文字。
- Produces: `LESSON_ID`、`FIELD_ORDER`、`FiveFieldRecord`、`LessonState`、`LessonTurn`、`RecoveryLessonEngine`，供 session store 與 desktop bridge 使用。

- [ ] **Step 1: Write the failing tests**

建立以下測試，固定第一課的公開契約：

```python
def test_start_returns_first_field_prompt():
    turn = RecoveryLessonEngine().start()
    assert turn.status == "active"
    assert turn.state.current_field == "event"
    assert "實際發生了什麼" in turn.reply

def test_unlabelled_answer_is_saved_only_to_current_field():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    turn = engine.accept("昨天家人問我什麼時候才像個正常人", state)
    assert turn.state.record.event == "昨天家人問我什麼時候才像個正常人"
    assert turn.state.record.expectation == ""
    assert turn.state.current_field == "expectation"

def test_blank_answer_does_not_advance_or_invent_content():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    turn = engine.accept("...", state)
    assert turn.state.current_field == "event"
    assert turn.state.record.event == ""

def test_urgent_safety_signal_holds_lesson_before_llm():
    safety = SafetyAssessment(
        categories=("immediate_danger",), strength=3, should_nudge=True,
        urgent=True, nudge="先確認安全。"
    )
    turn = RecoveryLessonEngine().accept("我現在可能傷害自己", RecoveryLessonEngine().start().state, safety)
    assert turn.status == "safety_hold"
    assert turn.state.current_field == "event"
    assert "先確認安全" in turn.reply

def test_completion_keeps_user_values_as_raw_text():
    engine = RecoveryLessonEngine()
    state = engine.start().state
    for value in ["事件", "家人期待", "我腦中出現的語句", "目前沒有外部證據", "先去散步十分钟"]:
        turn = engine.accept(value, state)
        state = turn.state
    assert turn.status == "completed"
    assert turn.state.record.next_step == "先去散步十分钟"
```

欄位顯示文字固定為：`事件`、`家庭期待／外部要求`、`內在語句／聲音／想法`、`證據與其他解釋`、`下一個安全可逆的小行動`。測試中使用的「聲音」只作使用者原文，不得被 engine 重新解釋。

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest tests/test_recovery_lesson.py -q`

Expected: FAIL because `core.recovery_lesson` does not yet exist.

- [ ] **Step 3: Implement the minimal engine in `core/recovery_lesson.py`**

定義：

```python
LESSON_ID = "recovery_lesson_1_pressure_is_not_command"
FIELD_ORDER = ("event", "expectation", "inner_content", "evidence", "next_step")

@dataclass(frozen=True)
class FiveFieldRecord:
    event: str = ""
    expectation: str = ""
    inner_content: str = ""
    evidence: str = ""
    next_step: str = ""

@dataclass(frozen=True)
class LessonState:
    lesson_id: str = LESSON_ID
    current_field: str = "event"
    record: FiveFieldRecord = FiveFieldRecord()
    completed: bool = False
    faith_opt_in: bool = False

    def to_dict(self) -> dict[str, object]: ...

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "LessonState": ...

@dataclass(frozen=True)
class LessonTurn:
    status: str
    reply: str
    state: LessonState
    lesson_context: str = ""

class RecoveryLessonEngine:
    def is_start_request(self, message: str) -> bool: ...
    def start(self, *, faith_opt_in: bool = False) -> LessonTurn: ...
    def accept(
        self,
        message: str,
        state: LessonState,
        safety: SafetyAssessment | None = None,
    ) -> LessonTurn: ...
```

實作規則：

- `accept` 只把非空使用者原文寫入目前欄位，不由規則或模型補寫其他欄位。
- 空白、只有標點或只有省略語意的輸入留在原欄位，回傳同一個短問題。
- `urgent=True` 時回傳 `safety_hold`，不修改 record，不產生 lesson context。
- 非 urgent 的指涉感／使命訊號保留使用者輸入，lesson context 只加入「先分離感受與證據，不確認外部意義」的約束。
- `faith_opt_in=False` 時，所有 reply 與 lesson context 不得加入聖經、神、寬恕、贖罪或悔改詮釋。
- 五個欄位完成後回傳 `completed`，只整理已輸入內容，不生成因果結論。

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -m pytest tests/test_recovery_lesson.py -q`

Expected: all tests PASS.

- [ ] **Step 5: Commit the pure engine**

```bash
git add core/recovery_lesson.py tests/test_recovery_lesson.py
git commit -m "feat: add pressure is not command lesson engine"
```

### Task 2: 將 lesson state 接到現有 session store

**Files:**
- Modify: `core/session_context.py`
- Modify: `tests/test_session_conversation_store.py`

**Interfaces:**
- Consumes: `LessonState` 的 `to_dict()` 或等價 JSON-compatible mapping。
- Produces: `set_lesson_state(session_id: str | None, state: Mapping[str, Any]) -> None`、`lesson_state(session_id: str | None) -> dict[str, Any] | None`、`clear_lesson_state(session_id: str | None) -> None`。

- [ ] **Step 1: Write failing tests**

在既有 session store 測試加入：

```python
def test_lesson_state_isolated_by_session(): ...
def test_lesson_state_is_returned_as_deep_copy(): ...
def test_clear_lesson_state_does_not_clear_messages(): ...
def test_unknown_session_has_no_lesson_state(): ...
```

測試必須確認 `session-a` 的五格內容不會出現在 `session-b`，修改回傳 dict 不會反寫 store，清除 lesson 不會刪除對話歷史。

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `python -m pytest tests/test_session_conversation_store.py -q`

Expected: FAIL with missing lesson-state methods.

- [ ] **Step 3: Implement session-scoped storage**

在 `_SessionState` 加入 `lesson_state: dict[str, Any] | None = None`。使用既有 `RLock`、session normalization 與 `deepcopy`；不得把 lesson state 寫入既有 `messages`、memory promotion 或長期資料庫。

- [ ] **Step 4: Run the focused tests and regression tests**

Run: `python -m pytest tests/test_session_conversation_store.py tests/test_memory_promotion_policy.py -q`

Expected: all PASS。

- [ ] **Step 5: Commit the session boundary**

```bash
git add core/session_context.py tests/test_session_conversation_store.py
git commit -m "feat: keep recovery lesson state in session scope"
```

### Task 3: 建立第一課的 prompt contract

**Files:**
- Modify: `core/conversation_prompt.py`
- Create or Modify: `tests/test_conversation_prompt.py`

**Interfaces:**
- Consumes: `LessonState` 的公開欄位與 `SafetyAssessment` 的非診斷性訊息。
- Produces: `build_recovery_lesson_prompt(field: str, record: Mapping[str, str], *, faith_opt_in: bool = False, safety_hold: bool = False) -> str`。

- [ ] **Step 1: Write failing tests**

測試以下契約：

```python
def test_lesson_prompt_requires_one_question_and_no_diagnosis(): ...
def test_lesson_prompt_does_not_confirm_unverified_inner_voice(): ...
def test_faith_terms_absent_without_opt_in(): ...
def test_faith_terms_are_optional_and_non_authoritative_when_opted_in(): ...
def test_safety_hold_prompt_cannot_continue_lesson(): ...
```

具體斷言：未 opt-in 的 prompt 不含「聖經」「神」「贖罪」「寬恕」；所有版本都含「不診斷」「不把感受直接判定為外部事實」或等價約束；每輪要求最多一個問題；安全暫停版本要求先確認安全，不要求填下一格。

- [ ] **Step 2: Run focused tests and verify they fail**

Run: `python -m pytest tests/test_conversation_prompt.py -q`

Expected: FAIL because the new builder does not exist.

- [ ] **Step 3: Implement `build_recovery_lesson_prompt`**

prompt 必須使用現有繁體中文語氣，輸入的 record 只作已知資料，未填欄位標成未知；不准把家庭壓力寫成唯一病因，不准把內在聲音寫成神諭或外部訊息，不准透過宗教語言取代安全判斷。`faith_opt_in=True` 時只能加入「可選的意義整理框架」，並保留拒絕、退出與界線。

- [ ] **Step 4: Run focused and existing prompt tests**

Run: `python -m pytest tests/test_conversation_prompt.py tests/test_trevor_identity_contract.py -q`

Expected: all PASS，既有一般／程式／研究模式的 prompt 行為不變。

- [ ] **Step 5: Commit the prompt contract**

```bash
git add core/conversation_prompt.py tests/test_conversation_prompt.py
git commit -m "feat: add non-diagnostic recovery lesson prompt contract"
```

### Task 4: 接入 DesktopBridge 的單人第一課流程

**Files:**
- Modify: `desktop_chat_app.py`
- Create: `tests/test_recovery_lesson_integration.py`

**Interfaces:**
- Consumes: `RecoveryLessonEngine.start/accept`、`SessionConversationStore` lesson-state methods、`build_recovery_lesson_prompt`、既有 `SafetySignalTracker.assess`。
- Produces: `DesktopBridge._process_recovery_lesson_turn(session_id: str, user_message: str, safety: SafetyAssessment) -> LessonTurn | None`，以及 `_build_live_llm_messages(..., lesson_context: str = "")`、`_generate_live_llm_reply(..., lesson_context: str = "")` 的向後相容參數。

- [ ] **Step 1: Write failing integration tests**

以不啟動背景執行緒的最小 bridge fixture 測試：

```python
def test_start_request_creates_lesson_state_and_returns_first_question(): ...
def test_active_lesson_saves_raw_answer_and_advances_one_field(): ...
def test_urgent_safety_bypasses_llm_and_returns_safety_hold(): ...
def test_lesson_state_is_not_promoted_to_long_term_memory(): ...
def test_non_lesson_message_keeps_existing_route_behavior(): ...
```

第一課啟動語句至少支援「開始第一課」「開始壓力不是命令」「做五格紀錄」；啟動與進行中的 lesson turn 必須先於一般 router 續接，但不得破壞既有 pending confirmation／clarification 行為。

- [ ] **Step 2: Run integration tests and verify they fail**

Run: `python -m pytest tests/test_recovery_lesson_integration.py -q`

Expected: FAIL because DesktopBridge has no lesson hook or lesson prompt parameter。

- [ ] **Step 3: Add engine and lesson state wiring**

在 `DesktopBridge.__init__` 建立無狀態 `RecoveryLessonEngine`。在 `send_message` 完成 pending confirmation／clarification 的續接處理，並完成 `safety_tracker.assess` 後、呼叫一般 `InteractionGateway.decide` 前：

1. 若是啟動語句，建立 session lesson state，回傳第一格問題。
2. 若 session 有 lesson state，將本輪原文交給 engine；把新 state 寫回 session。
3. 若 `safety_hold`，不呼叫 `_generate_live_llm_reply`、不啟動 LangGraph、不做一般學習鼓勵；只回傳安全暫停與既有非診斷性 nudge。
4. 若一般 active turn，將 `lesson_context` 傳入 `_build_live_llm_messages`；若 LLM 失敗，使用 engine 的 deterministic `reply`。
5. response payload 加入 `lesson: {id, status, current_field, record}`，但維持 `memory.promotion.saved == False`，且不把五格原文送進 training overlay。

新增 `lesson_context` 時只在 lesson workflow 使用，不改變既有一般聊天、任務、研究與程式請求的 prompt。

- [ ] **Step 4: Run integration, safety, memory and existing chat contract tests**

Run: `python -m pytest tests/test_recovery_lesson_integration.py tests/test_safety_signal_tracker.py tests/test_memory_promotion_policy.py tests/test_session_conversation_store.py tests/test_prophet_dialog_first.py -q`

Expected: all PASS。

- [ ] **Step 5: Commit the vertical slice**

```bash
git add desktop_chat_app.py tests/test_recovery_lesson_integration.py
git commit -m "feat: wire first recovery lesson into desktop chat"
```

### Task 5: 完成 Phase 0 驗證與回歸檢查

**Files:**
- Modify: `tests/test_recovery_lesson.py` — 補齊 edge cases only if discovered by validation。
- Modify: `tests/test_recovery_lesson_integration.py` — 補齊 routing／fallback cases only if discovered by validation。
- Modify: `docs/superpowers/specs/2026-11-02-trevor-recovery-learning-lab-design.md` — 寫入已驗證的 Phase 0 結果，不把測試通過寫成臨床效果。

**Interfaces:**
- Consumes: Tasks 1–4 的 public contracts。
- Produces: 可重現的 Phase 0 benchmark evidence 與 go／no-go 記錄。

- [ ] **Step 1: Run the focused suite**

Run: `python -m pytest tests/test_recovery_lesson.py tests/test_recovery_lesson_integration.py tests/test_safety_signal_tracker.py tests/test_conversation_prompt.py -q`

Expected: all PASS。

- [ ] **Step 2: Run the broader bounded suite**

Run: `python -m pytest -q`

Expected: no new failures attributable to the lesson slice；任何既有失敗都要明確列出，不得用歷史 log 宣稱通過。

- [ ] **Step 3: Check the diff and repository state**

Run: `git diff --check` 以及 `git status --short`。

Expected: no whitespace errors；只包含本計畫的文件、核心模組與測試變更。

- [ ] **Step 4: Record the first benchmark result**

在設計文件中記錄：五格流程是否可重現、urgent safety 是否能中斷、未 opt-in 信仰語彙是否為零、lesson state 是否未進入長期記憶；不得把這些結果寫成「改善精神症狀」或「臨床有效」。

- [ ] **Step 5: Commit the verified Phase 0 slice**

```bash
git add docs/superpowers/specs/2026-11-02-trevor-recovery-learning-lab-design.md
git commit -m "test: verify first recovery lesson phase zero slice"
```

## Self-Review

- Spec coverage: 第一課、五格紀錄、非診斷性、現實感邊界、信仰 opt-in、session-only memory、安全暫停、LLM fallback、測試與 Phase 0 閘門均有對應 task。
- Scope: 沒有加入多人帳號、推播、硬體、臨床監看、藥物決策或自動救援；這些保留到後續產品審查。
- Type consistency: `LessonState` 是 engine 的 immutable domain state；session store 只保存 JSON-compatible mapping；bridge 透過 `LessonTurn` 對接兩者。
- Main unresolved product decision intentionally excluded: 對外測試者的納入／排除標準、人工事件處理者、資料保留與地區化轉介，必須在 Phase 1 前另立設計審查。
- Review focus coverage: all five high-risk input classes are pinned to focused tests before broader regression.

