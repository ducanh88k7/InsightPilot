from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class EvidenceExecutionStatus(str, Enum):
    """Cho biết lần gọi Tool tạo ra kết quả có thể sử dụng hay gặp lỗi thực thi."""

    SUCCESS = "success"
    ERROR = "error"


def _json_safe(value: Any) -> Any:
    """Đệ quy chuyển các giá trị Python/pandas/numpy thường gặp để lưu dưới dạng JSON."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())
    if isinstance(value, (str, int, bool)):
        return value
    return value


@dataclass
class EvidenceItem:
    """Một lần thực thi Tool cùng kết quả, được giữ lại để xác minh sau đó."""

    evidence_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    execution_status: EvidenceExecutionStatus
    mode: str
    plan_step_id: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Trả về bản biểu diễn độc lập, tương thích với JSON của bằng chứng này."""
        return {
            "evidence_id": self.evidence_id,
            "tool_name": self.tool_name,
            "arguments": _json_safe(deepcopy(self.arguments)),
            "result": _json_safe(deepcopy(self.result)),
            "execution_status": self.execution_status.value,
            "mode": self.mode,
            "plan_step_id": self.plan_step_id,
            "created_at": self.created_at,
        }


class EvidenceLedger:
    """Tập hợp kết quả Tool của một lượt hỏi, dùng làm căn cứ cho câu trả lời của Agent.
        
            Ledger chỉ lưu đầu ra của Tool, không lưu toàn bộ DataFrame nguồn. Mỗi lần ghi đều
            tạo bản sao để việc thay đổi dictionary kết quả về sau không âm thầm làm sai lệch
            bằng chứng đã được lưu để xác minh.
            
        """

    def __init__(self) -> None:
        self._items: list[EvidenceItem] = []
        self._next_id = 1

    def add(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        mode: str,
        plan_step_id: str | None = None,
        execution_status: EvidenceExecutionStatus | str | None = None,
    ) -> EvidenceItem:
        """Ghi nhận một lần gọi Tool và trả về bản ghi bằng chứng đã lưu."""
        if not tool_name or not isinstance(tool_name, str):
            raise ValueError("tool_name must be a non-empty string.")
        if not isinstance(arguments, dict):
            raise TypeError("Tool arguments must be a dictionary.")
        if not isinstance(result, dict):
            raise TypeError("Tool result must be a dictionary.")
        if not mode or not isinstance(mode, str):
            raise ValueError("mode must be a non-empty string.")

        if execution_status is None:
            status = (
                EvidenceExecutionStatus.ERROR
                if result.get("status") == "error"
                else EvidenceExecutionStatus.SUCCESS
            )
        else:
            status = EvidenceExecutionStatus(execution_status)

        item = EvidenceItem(
            evidence_id=f"E{self._next_id:04d}",
            tool_name=tool_name,
            arguments=_json_safe(deepcopy(arguments)),
            result=_json_safe(deepcopy(result)),
            execution_status=status,
            mode=mode,
            plan_step_id=plan_step_id,
        )
        self._items.append(item)
        self._next_id += 1
        return deepcopy(item)

    def get(self, evidence_id: str) -> EvidenceItem | None:
        """Trả về bản sao độc lập của một bản ghi, hoặc None nếu không tìm thấy ID."""
        for item in self._items:
            if item.evidence_id == evidence_id:
                return deepcopy(item)
        return None

    def all(self) -> list[EvidenceItem]:
        """Trả về bản sao độc lập của toàn bộ bằng chứng theo thứ tự được ghi nhận."""
        return deepcopy(self._items)

    def to_dict(self) -> dict[str, Any]:
        """Tuần tự hóa ledger nhưng vẫn giữ thứ tự bản ghi trong lượt hỏi."""
        return {
            "items": [item.to_dict() for item in self._items],
            "count": len(self._items),
        }

    def to_prompt_context(self) -> str:
        """Tuần tự hóa bằng chứng thành JSON dễ đọc để dùng trong prompt xác minh sau đó."""
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    def clear(self) -> None:
        """Xóa các bản ghi của lượt hỏi hiện tại và khởi động lại dãy ID bằng chứng."""
        self._items.clear()
        self._next_id = 1

    def __len__(self) -> int:
        return len(self._items)
