# InsightPilot — Milestone 4: Planning Integration

## Goal

Milestone 4 integrates the Planning subsystem into `DataAnalystAgent` instead of exposing Planner and Executor as a separate end-user path.

```text
User
  ↓
DataAnalystAgent (orchestrator)
  ↓
Router
  ├── Simple question → existing direct Tool loop
  └── Complex question → Planner → AnalysisPlan → Executor
                                      ↓
                                 ToolRegistry
                                      ↓
                                 AnalysisContext
                                      ↓
                              Data Analysis Engine
                                      ↓
                              Final LLM synthesis
```

## Why keep both direct and planned modes?

Not every question requires a multi-step plan. A simple query can stay on the fast direct tool loop. A complex analytical question benefits from an explicit plan, dependencies, statuses, and a final synthesis step.

## New orchestration concepts

### `_should_plan()`
A lightweight router decides whether a question should use the Planner. It is intentionally conservative and can be replaced by a learned/LLM router later.

### `AnalysisPlanner`
Turns the question + dataset profile + available tools into a validated `AnalysisPlan` using Structured Outputs.

### `AnalysisExecutor`
Runs the validated plan through the existing `ToolRegistry` and `AnalysisContext`.

### `_synthesize_plan_result()`
After plan execution, the top-level Agent asks the LLM to turn only the verified step results into the user-facing answer. No tools are enabled in this synthesis call.

## AgentResult additions

`AgentResult` now contains:

- `mode`: `direct` or `planned`
- `plan`: serialized executed plan when planning was used

This preserves the existing API while making orchestration visible to callers.

## Example

Complex question:

> Why did revenue change between the latest two months, and which product was the top contributor?

Flow:

1. Preflight profile.
2. Derive revenue if required.
3. Router selects planned mode.
4. Planner creates steps.
5. Executor validates and runs the plan.
6. Agent records step-level tool execution.
7. Final synthesis produces the answer from verified results.

## Compatibility

The previous direct Tool loop remains available and is selected automatically for simple questions. `planning_mode="always"` or `planning_mode="never"` can be used for controlled testing.
