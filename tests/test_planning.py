from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from insightpilot.planning import (
    AnalysisExecutor,
    AnalysisPlan,
    AnalysisPlanner,
    AnalysisStep,
    PlanValidationError,
    StepStatus,
)
from insightpilot.planning.demo import build_demo_plan
from insightpilot.tools import AnalysisContext, ToolRegistry, build_data_tools

ROOT = Path(__file__).parent.parent
DATASET = ROOT / "data" / "sample_sales.csv"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_data_tools():
        registry.register(tool)
    return registry


def build_context() -> AnalysisContext:
    context = AnalysisContext()
    build_registry().execute("load_dataset", {"path": str(DATASET)}, context)
    return context


def test_plan_validation_and_dependency_order():
    plan = build_demo_plan()
    registry = build_registry()
    plan.validate({tool["name"] for tool in registry.list_tools()})

    assert [step.id for step in plan.ready_steps()] == ["step_1"]


def test_executor_runs_dependency_order_and_updates_context():
    registry = build_registry()
    context = AnalysisContext()
    registry.execute("load_dataset", {"path": str(DATASET)}, context)

    execution = AnalysisExecutor(registry, context).execute_plan(build_demo_plan())

    assert execution.plan.status.value == "completed"
    assert all(step.status == StepStatus.COMPLETED for step in execution.plan.steps)
    assert "revenue" in context.df.columns
    assert execution.step_results["step_3"]["rows"][0]["product"] == "Laptop"
    assert execution.step_results["step_4"]["percentage_change"] == pytest.approx(-35.5769230769)


def test_plan_rejects_unknown_tool():
    plan = AnalysisPlan(
        goal="Invalid plan",
        steps=[
            AnalysisStep(
                id="step_1",
                purpose="Use a missing tool",
                tool_name="does_not_exist",
            )
        ],
    )

    with pytest.raises(PlanValidationError):
        plan.validate({"profile_dataset"})


def test_plan_rejects_dependency_cycle():
    plan = AnalysisPlan(
        goal="Cyclic plan",
        steps=[
            AnalysisStep(
                id="step_1",
                purpose="A",
                tool_name="profile_dataset",
                depends_on=["step_2"],
            ),
            AnalysisStep(
                id="step_2",
                purpose="B",
                tool_name="profile_dataset",
                depends_on=["step_1"],
            ),
        ],
    )

    with pytest.raises(PlanValidationError, match="dependency cycle"):
        plan.validate({"profile_dataset"})


@dataclass
class FakeResponse:
    output_text: str


class FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, *, model, input, text):
        self.calls.append({"model": model, "input": input, "text": text})
        payload = {
            "goal": "Find the top product by revenue",
            "steps": [
                {
                    "id": "step_1",
                    "purpose": "Calculate revenue by product",
                    "tool_name": "group_metric",
                    "arguments_json": json.dumps(
                        {
                            "dimension_col": "product",
                            "metric_col": "revenue",
                            "agg": "sum",
                            "top_n": 1,
                        }
                    ),
                    "depends_on": [],
                }
            ],
        }
        return FakeResponse(output_text=json.dumps(payload))


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_planner_parses_structured_plan_and_validates_tools():
    registry = build_registry()
    client = FakeClient()
    planner = AnalysisPlanner(
        client=client,
        registry=registry,
        model="test-model",
    )

    plan = planner.build_plan(
        "What is the top product by revenue?",
        dataset_profile={"columns": [{"name": "product"}, {"name": "revenue"}]},
    )

    assert plan.goal == "Find the top product by revenue"
    assert plan.steps[0].tool_name == "group_metric"
    assert plan.steps[0].arguments["top_n"] == 1
    assert client.responses.calls[0]["text"]["format"]["type"] == "json_schema"



def test_executor_reports_failed_and_blocked_steps_and_continues_independent_steps():
    registry = build_registry()
    context = AnalysisContext()
    registry.execute("load_dataset", {"path": str(DATASET)}, context)
    events = []
    plan = AnalysisPlan(
        goal="Test partial execution behavior",
        steps=[
            AnalysisStep(
                id="bad_step",
                purpose="Trigger a controlled Tool error",
                tool_name="group_metric",
                arguments={
                    "dimension_col": "product",
                    "metric_col": "missing_metric",
                    "agg": "sum",
                    "top_n": 1,
                },
            ),
            AnalysisStep(
                id="dependent_step",
                purpose="Must not run after its prerequisite fails",
                tool_name="profile_dataset",
                depends_on=["bad_step"],
            ),
            AnalysisStep(
                id="independent_step",
                purpose="Can still run independently",
                tool_name="profile_dataset",
            ),
        ],
    )

    execution = AnalysisExecutor(registry, context).execute_plan(
        plan,
        on_step=lambda step: events.append((step.id, step.status.value)),
    )

    statuses = {step.id: step.status for step in execution.plan.steps}
    assert statuses["bad_step"] == StepStatus.FAILED
    assert statuses["dependent_step"] == StepStatus.BLOCKED
    assert statuses["independent_step"] == StepStatus.COMPLETED
    assert execution.plan.status.value == "partial"
    assert execution.execution_order == ["bad_step", "independent_step"]
    assert execution.steps_attempted == 2
    assert ("bad_step", "failed") in events
    assert ("independent_step", "completed") in events
    assert all(step_id != "dependent_step" for step_id, _ in events)


def test_executor_rejects_reexecuting_the_same_plan_object():
    registry = build_registry()
    context = AnalysisContext()
    registry.execute("load_dataset", {"path": str(DATASET)}, context)
    executor = AnalysisExecutor(registry, context)
    plan = build_demo_plan()

    executor.execute_plan(plan)

    with pytest.raises(ValueError, match="already started"):
        executor.execute_plan(plan)
