from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .runtime import AnalysisContext


ToolExecutor = Callable[[AnalysisContext, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    """Mô tả một Tool mà Agent có thể gọi."""

    name: str
    description: str
    input_schema: dict[str, Any]
    execute: ToolExecutor

    def as_llm_schema(self) -> dict[str, Any]:
        """Trả về schema của function Tool độc lập với nhà cung cấp."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }


class ToolRegistry:
    """Lưu trữ và thực thi các Tool mà Agent được phép sử dụng."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._tools))
            raise KeyError(f"Unknown tool '{name}'. Available tools: {available}") from exc

    def list_tools(self) -> list[dict[str, Any]]:
        """Trả về danh sách schema Tool độc lập với nhà cung cấp."""
        return [
            self._tools[name].as_llm_schema()
            for name in sorted(self._tools)
        ]

    def list_tool_specs(self) -> list[ToolSpec]:
        """Trả về các đối tượng ToolSpec đã đăng ký."""
        return [self._tools[name] for name in sorted(self._tools)]

    def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        context: AnalysisContext,
    ) -> dict[str, Any]:
        tool = self.get(name)
        if not isinstance(arguments, dict):
            raise TypeError("Tool arguments must be a dictionary.")
        result = tool.execute(context, arguments)
        if not isinstance(result, dict):
            raise TypeError(
                f"Tool '{name}' must return a dictionary, "
                f"got {type(result).__name__}."
            )
        context.last_result = result
        return result
