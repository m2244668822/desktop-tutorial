# Task 1 Implementation Report — 建立第一課的純邏輯 engine

## Result

- Status: done
- Repository: `E:\智能體\Trevor-integration-20261102`
- Branch: `codex/trevor-integration-20261102`
- Base SHA: `ac8ef962386cf8c324016b0ff8361e6bb634be2d`
- Commit: `d2ecbd856b305127b7d1836f244377fe3a767a53` (`feat: add pressure is not command lesson engine`)
- Executor: Codex (GPT-6), operating in the supplied workspace.

## Files changed

- `core/recovery_lesson.py` — pure, stateless five-field lesson engine and serialization contract.
- `tests/test_recovery_lesson.py` — nine behavior tests covering the public contract and safety/faith/raw-text boundaries.

No n8n files or unrelated files were staged or committed.

## Implementation details

- Exported `LESSON_ID = "recovery_lesson_1_pressure_is_not_command"` and `FIELD_ORDER = ("event", "expectation", "inner_content", "evidence", "next_step")`.
- Added frozen `FiveFieldRecord`, `LessonState`, and `LessonTurn` dataclasses; `LessonState` supports dictionary round trips.
- Added `RecoveryLessonEngine.is_start_request`, `start`, and `accept`.
- Accepted nonempty input is kept as raw text and saved only in the current field. Blank, punctuation-only, and recognized omission responses retain the current state and prompt again.
- Urgent safety assessment returns `safety_hold` before changing state and emits no lesson context.
- Non-urgent referential/meaning/mission categories preserve the message and append the required constraint: “先分離感受與證據，不確認外部意義”.
- Faith opt-in is stored on state. No faith interpretation is generated when off; raw user text is not scrubbed from the record or completion summary.
- Completion summarizes only the five captured values and makes no causal claims.
- The engine itself contains no session store or persistence side effects.

## TDD and validation evidence

1. Wrote the tests first. Initial `python -m pytest tests/test_recovery_lesson.py -q` could not start because the system Python did not have pytest installed. Used `uv run --with pytest` for the specified test command instead.
2. RED: `uv run --with pytest python -m pytest tests/test_recovery_lesson.py -q` failed during collection with `ModuleNotFoundError: No module named 'core.recovery_lesson'`, as expected before implementation.
3. GREEN/focused: `uv run --with pytest python -m pytest tests/test_recovery_lesson.py -q` — **9 passed**.
4. Relevant existing safety slice: `uv run --with pytest python -m pytest tests/test_recovery_lesson.py tests/test_safety_signal_tracker.py -q` — **12 passed**.
5. `git diff --check` and staged diff whitespace check — passed.
6. Commit completed. Remaining worktree entries are pre-existing untracked n8n planning/spec documents; no Task 1 files remain uncommitted.

## Self-review

Reviewed safety short-circuit ordering, raw-text preservation, state immutability, absence of session persistence, opt-in boundary, completion output, and staged file scope. The task brief does not define exhaustive localized wording for start-request detection or omission phrases; the implementation currently recognizes common Traditional Chinese start phrases and the omission forms `略`, `跳過`, `不知道`, `不想說`, `先不說`, and `無`, in addition to blank/punctuation-only input.

## Blockers / concerns

- None blocking.
- No full repository suite was run; the brief requires the focused tests and relevant existing slice, both of which passed.
- Initial repository state was already dirty in unrelated n8n files (`automation/n8n/trevor-training-evaluation.json`, `tests/test_n8n_workflow_contract.py`, and `tools/validate_n8n_training_workflow.py`, plus other untracked n8n work). These were preserved. Additional untracked n8n plan/spec files remain visible after the commit.

## Reviewer follow-up fixes

### Findings addressed

1. **P1 — Safety assessment is now mandatory.** `RecoveryLessonEngine.accept` requires a `SafetyAssessment` argument, with no default. Urgent assessment returns `safety_hold` with the unchanged state before inspecting or recording the message. Every normal test call now supplies an explicit non-urgent assessment; dedicated tests verify omitted assessment raises `TypeError` and urgent input cannot advance.
2. **P2 — “無” is preserved as content.** Removed `無` and the ambiguous `不知道` from the omission set. Only explicit skip responses remain (`略`, `跳過`, `不想說`, `先不說`), plus blank and punctuation-only inputs. Added a test that stores `無` verbatim in the evidence field and advances.
3. **P2 — Negated start requests are rejected.** `is_start_request` now checks leading negative requests (`不要`, `先不要`, `暫時不要`, `別`, `不想`, `不用`) before positive phrase matching. Added the required `不要開始第一課` regression test.

Existing non-diagnostic behavior and faith opt-in boundary are unchanged. Input remains raw and is not interpreted or sanitized.

### TDD and command outputs

- RED command: `uv run --with pytest python -m pytest tests/test_recovery_lesson.py -q`
  - Output: **4 failed, 9 passed**. Failures reproduced negated-start acceptance, optional safety argument, and “無” being discarded (negated case is asserted in two tests).
- GREEN focused command: `uv run --with pytest python -m pytest tests/test_recovery_lesson.py -q`
  - Output: **13 passed in 0.13s**.
- Relevant safety slice: `uv run --with pytest python -m pytest tests/test_recovery_lesson.py tests/test_safety_signal_tracker.py -q`
  - Output: **16 passed in 0.19s**.
- Whitespace validation: `git diff --check`
  - Output: no errors.

### Self-review and commit

Reviewed signature/call sites in the focused test file, urgent short-circuit ordering, preservation of the raw “無” answer, explicit-negation gate, and faith/non-diagnostic coverage. Only `core/recovery_lesson.py`, `tests/test_recovery_lesson.py`, and this report are included in the fix commit. Unrelated pre-existing untracked n8n plan/spec documents remain untouched.

- Fix commit: `16289ec92d4bcfc357bd91ecad6cea522ec21010` (`fix: close recovery lesson reviewer findings`).
