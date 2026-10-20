from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class PlanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class PlanValidationError(ValueError):
    """Được phát sinh khi cấu trúc kế hoạch không hợp lệ."""


@dataclass
class AnalysisStep:
    """Một bước có thể thực thi trong kế hoạch phân tích."""

    id: str
    purpose: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class AnalysisPlan:
    """Kế hoạch có cấu trúc được tạo trước khi thực hiện một phân tích phức tạp."""

    goal: str
    steps: list[AnalysisStep] = field(default_factory=list)
    status: PlanStatus = PlanStatus.PENDING

    def validate(self, available_tools: set[str] | None = None) -> None:
        """Kiểm tra ID, quan hệ phụ thuộc, tên Tool và chu trình phụ thuộc."""
        if not self.goal.strip():
            raise PlanValidationError("Plan goal must not be empty.")
        if not self.steps:
            raise PlanValidationError("Plan must contain at least one step.")

        step_ids = [step.id for step in self.steps]
        duplicates = {step_id for step_id in step_ids if step_ids.count(step_id) > 1}
        if duplicates:
            raise PlanValidationError(
                f"Duplicate step IDs: {sorted(duplicates)}."
            )

        known_ids = set(step_ids)
        if available_tools is not None:
            unknown_tools = {
                step.tool_name
                for step in self.steps
                if step.tool_name not in available_tools
            }
            if unknown_tools:
                raise PlanValidationError(
                    f"Unknown tools in plan: {sorted(unknown_tools)}."
                )

        for step in self.steps:
            if step.id in step.depends_on:
                raise PlanValidationError(
                    f"Step '{step.id}' cannot depend on itself."
                )
            missing = set(step.depends_on) - known_ids
            if missing:
                raise PlanValidationError(
                    f"Step '{step.id}' depends on unknown steps: {sorted(missing)}."
                )

        # Phát hiện chu trình phụ thuộc bằng thuật toán Kahn.
        remaining = {step.id: set(step.depends_on) for step in self.steps}
        resolved: set[str] = set()
        while remaining:
            ready = [step_id for step_id, deps in remaining.items() if deps <= resolved]
            if not ready:
                raise PlanValidationError("Plan contains a dependency cycle.")
            for step_id in ready:
                resolved.add(step_id)
                del remaining[step_id]

    def ready_steps(self) -> list[AnalysisStep]:
        """Trả về các bước đang chờ mà toàn bộ bước phụ thuộc đã hoàn tất thành công."""
        completed = {
            step.id
            for step in self.steps
            if step.status == StepStatus.COMPLETED
        }
        return [
            step
            for step in self.steps
            if step.status == StepStatus.PENDING
            and set(step.depends_on) <= completed
        ]

    def mark_blocked_dependents(self) -> None:
        """Chặn các bước đang chờ nếu chúng phụ thuộc vào bước thất bại hoặc bị chặn."""
        failed_or_blocked = {
            step.id
            for step in self.steps
            if step.status in {StepStatus.FAILED, StepStatus.BLOCKED}
        }
        changed = True
        while changed:
            changed = False
            for step in self.steps:
                if step.status != StepStatus.PENDING:
                    continue
                if set(step.depends_on) & failed_or_blocked:
                    step.status = StepStatus.BLOCKED
                    failed_or_blocked.add(step.id)
                    changed = True

    def refresh_status(self) -> PlanStatus:
        """Xác định trạng thái chung của kế hoạch dựa trên trạng thái các bước hiện tại."""
        statuses = [step.status for step in self.steps]
        if statuses and all(status == StepStatus.COMPLETED for status in statuses):
            self.status = PlanStatus.COMPLETED
        elif any(status == StepStatus.FAILED for status in statuses):
            if any(status == StepStatus.COMPLETED for status in statuses):
                self.status = PlanStatus.PARTIAL
            else:
                self.status = PlanStatus.FAILED
        elif any(status == StepStatus.BLOCKED for status in statuses):
            self.status = PlanStatus.PARTIAL
        elif statuses and all(status == StepStatus.SKIPPED for status in statuses):
            self.status = PlanStatus.PARTIAL
        else:
            self.status = PlanStatus.RUNNING
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status.value,
            "steps": [step.to_dict() for step in self.steps],
        }
