from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable

from insightpilot.tools import AnalysisContext, ToolRegistry

from .models import AnalysisPlan, PlanStatus, StepStatus, AnalysisStep


StepCallback = Callable[[AnalysisStep], None]


@dataclass
class PlanExecutionResult:
    """Bản tóm tắt quá trình thực thi một AnalysisPlan."""

    plan: AnalysisPlan
    step_results: dict[str, dict[str, Any]]
    execution_order: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def steps_attempted(self) -> int:
        return len(self.execution_order)


class AnalysisExecutor:
    """Thực thi kế hoạch đã được xác thực bằng ToolRegistry và Context hiện có."""

    def __init__(self, registry: ToolRegistry, context: AnalysisContext) -> None:
        self.registry = registry
        self.context = context

    def execute_plan(
        self,
        plan: AnalysisPlan,
        on_step: StepCallback | None = None,
    ) -> PlanExecutionResult:
        """Thực thi mỗi bước đã sẵn sàng một lần và tùy chọn thông báo các bước thành công/thất bại.
            
                    Mỗi kế hoạch chỉ được sử dụng một lần. Từ chối thực thi lần hai giúp tránh
                    chạy lặp các Tool có tác động phụ khi bên gọi thử lại cùng một đối tượng kế hoạch.
                    
            """
        started_at = perf_counter()
        available_tools = {tool["name"] for tool in self.registry.list_tools()}
        plan.validate(available_tools)

        if plan.status != PlanStatus.PENDING or any(
            step.status != StepStatus.PENDING or step.result is not None
            for step in plan.steps
        ):
            raise ValueError(
                "AnalysisPlan has already started or contains prior results; "
                "build a fresh plan before executing it again."
            )

        plan.status = PlanStatus.RUNNING
        step_results: dict[str, dict[str, Any]] = {}
        execution_order: list[str] = []

        while True:
            ready = plan.ready_steps()
            if not ready:
                pending = [
                    step for step in plan.steps if step.status == StepStatus.PENDING
                ]
                if pending:
                    plan.mark_blocked_dependents()
                    pending = [
                        step for step in plan.steps if step.status == StepStatus.PENDING
                    ]
                    if pending:
                        raise RuntimeError(
                            "Execution stopped because pending steps have unresolved dependencies."
                        )
                break

            # Phiên bản hiện tại cố ý thực thi tuần tự. Các bước trong
            # nhóm sẵn sàng này độc lập với nhau theo khai báo quan hệ phụ thuộc.
            for step in ready:
                step.status = StepStatus.RUNNING
                execution_order.append(step.id)
                try:
                    result = self.registry.execute(
                        step.tool_name,
                        step.arguments,
                        self.context,
                    )
                except Exception as exc:
                    result = {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "tool": step.tool_name,
                    }

                step.result = result
                step_results[step.id] = result

                if result.get("status") == "error":
                    step.status = StepStatus.FAILED
                    plan.mark_blocked_dependents()
                else:
                    step.status = StepStatus.COMPLETED

                # Gọi callback sau khi đã ghi nhận trạng thái và kết quả của bước.
                # Không gọi callback thực thi cho bước bị chặn vì Tool của bước đó chưa chạy.
                if on_step is not None:
                    on_step(step)

        plan.refresh_status()
        return PlanExecutionResult(
            plan=plan,
            step_results=step_results,
            execution_order=execution_order,
            duration_ms=round((perf_counter() - started_at) * 1000, 3),
        )
