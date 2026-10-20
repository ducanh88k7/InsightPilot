# InsightPilot — Milestone 4.5: Integration Testing & Reliability

## Goal

Harden the integrated DataAnalystAgent + Planner + Executor workflow without adding another Agent or requiring a real OpenAI API call during tests.

## Changes

### 1. Per-turn observability

`AgentResult` now reports:

- `llm_requests`: number of Responses API request attempts, including requests that raised an exception.
- `tool_call_count`: number of recorded Tool attempts, including preflight and direct/planned Tool calls. Blocked plan steps are not counted as Tool calls because their Tools did not execute.
- `plan_steps_total`, `plan_steps_completed`, `plan_steps_failed`, `plan_steps_blocked`.
- `duration_ms`: end-to-end processing time for the turn.
- `fallback_used`, `fallback_reason`, and `warnings`.

The value `iterations` is retained for compatibility. In Direct Mode it is the direct loop iteration count; in Planned Mode it remains one orchestration cycle. Use `llm_requests` when measuring API requests.

A small per-turn client proxy counts calls to `responses.create()`. The counter is created inside `ask()`, not stored globally on the Agent, so metrics are scoped to one question.

### 2. Safer fallback boundary

Fallback to Direct Mode happens only if the Planner fails to produce a valid plan, before the planned Executor starts.

A Tool/Executor failure after execution begins does **not** silently trigger Direct Mode. This avoids rerunning analysis steps after some Tools may already have changed session state or produced side effects.

If final LLM synthesis fails after execution, InsightPilot returns a deterministic summary of the plan status and recorded step outputs rather than re-executing the plan.

### 3. Execution trace

`AnalysisExecutor.execute_plan()` accepts an optional `on_step` callback. It calls it after each attempted step has a final state (`COMPLETED` or `FAILED`). `PlanExecutionResult` now includes:

- `execution_order`: IDs of steps whose Tools were attempted.
- `duration_ms`: plan execution time.
- `steps_attempted`: derived from `execution_order`.

Blocked steps are represented in the Plan, but are not listed as executed Tools.

### 4. Single-use plan protection

The Executor rejects a Plan object that has already started or has old results. Callers must create a fresh Plan before retrying. This prevents accidental duplicate Tool execution by passing the same completed/failed object back to the Executor.

### 5. Tool result contract

`ToolRegistry.execute()` now checks that every Tool returns a dictionary. A Tool returning an unexpected type raises a clear `TypeError` that callers can handle.

## Integration workflow

```text
DataAnalystAgent.ask()
  ├─ preflight + dataset profile
  ├─ Router
  │   ├─ Direct Mode: LLM ↔ ToolRegistry loop
  │   └─ Planned Mode:
  │       ├─ Planner builds and validates AnalysisPlan
  │       ├─ Executor runs ready steps through ToolRegistry
  │       └─ LLM synthesizes recorded results (no Tools enabled)
  └─ AgentResult with request/tool/step/time metrics
```

## Testing

Run from the project root:

```bash
pytest -q
python run_planning_demo.py
```

The tests use fake clients. They do not call the OpenAI API and do not incur API token charges.

Coverage includes:

- Direct Mode and Planned Mode metrics.
- Planner failure followed by an observable Direct Mode fallback.
- Planner failure with fallback disabled.
- Synthesis failure without rerunning Tools.
- Tool failure and blocked dependencies.
- Independent steps still running after another step fails.
- Rejection of re-executing a used Plan object.

## Current limitations

- Router selection is keyword-based, not an LLM-based classifier.
- Ready steps execute sequentially, even when they are independent.
- Results are stored per step, but there is no generic output-to-argument mapping between steps yet.
- This milestone does not add retries, re-planning, Critic Agent, or a UI.
