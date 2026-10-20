from __future__ import annotations

import json
from typing import Any, Protocol

from insightpilot.tools import ToolRegistry

from .models import AnalysisPlan, AnalysisStep, PlanValidationError


class PlannerClient(Protocol):
    """Giao diện tối thiểu mà AnalysisPlanner cần từ client gọi mô hình."""

    @property
    def responses(self) -> Any: ...


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {
            "type": "string",
            "description": "The analytical objective the plan is designed to answer.",
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "purpose": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "arguments_json": {
                        "type": "string",
                        "description": "A JSON object containing arguments for the tool.",
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": [
                    "id",
                    "purpose",
                    "tool_name",
                    "arguments_json",
                    "depends_on",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["goal", "steps"],
    "additionalProperties": False,
}


class AnalysisPlanner:
    """Chuyển câu hỏi của người dùng thành kế hoạch phân tích đã xác thực và có thể thực thi."""

    def __init__(
        self,
        client: PlannerClient,
        registry: ToolRegistry,
        model: str,
    ) -> None:
        self.client = client
        self.registry = registry
        self.model = model

    def _input(self, question: str, dataset_profile: dict[str, Any] | None) -> list[dict[str, str]]:
        profile_text = json.dumps(
            dataset_profile or {},
            ensure_ascii=False,
            indent=2,
        )
        tool_text = json.dumps(
            self.registry.list_tools(),
            ensure_ascii=False,
            indent=2,
        )
        system = (
            "You are the planning component of InsightPilot, an AI data analyst. "
            "Create an executable analysis plan using only the available tools. "
            "Prefer the smallest correct set of steps. "
            "Use dependencies when a step logically requires a previous step. "
            "Do not invent columns or tools. The arguments_json field must be a valid JSON object string."
        )
        context = (
            "CURRENT DATASET PROFILE:\n"
            f"{profile_text}\n\n"
            "AVAILABLE TOOLS:\n"
            f"{tool_text}\n\n"
            "USER QUESTION:\n"
            f"{question}"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": context},
        ]

    def build_plan(
        self,
        question: str,
        dataset_profile: dict[str, Any] | None = None,
    ) -> AnalysisPlan:
        """Yêu cầu mô hình tạo kế hoạch có cấu trúc rồi tự xác thực kế hoạch trong chương trình."""
        if not question.strip():
            raise ValueError("Question must not be empty.")

        response = self.client.responses.create(
            model=self.model,
            input=self._input(question, dataset_profile),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "analysis_plan",
                    "schema": PLAN_SCHEMA,
                    "strict": True,
                }
            },
        )

        raw = getattr(response, "output_text", "").strip()
        if not raw:
            raise RuntimeError("Planner model returned no structured output.")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Planner returned invalid JSON.") from exc

        steps: list[AnalysisStep] = []
        for item in payload.get("steps", []):
            raw_args = item.get("arguments_json", "{}")
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                raise PlanValidationError(
                    f"Step '{item.get('id', '<unknown>')}' has invalid arguments_json."
                ) from exc
            if not isinstance(arguments, dict):
                raise PlanValidationError(
                    f"Step '{item.get('id', '<unknown>')}' arguments_json must decode to an object."
                )
            steps.append(
                AnalysisStep(
                    id=item["id"],
                    purpose=item["purpose"],
                    tool_name=item["tool_name"],
                    arguments=arguments,
                    depends_on=item["depends_on"],
                )
            )

        plan = AnalysisPlan(goal=payload["goal"], steps=steps)
        available_tools = {tool["name"] for tool in self.registry.list_tools()}
        plan.validate(available_tools)
        return plan
