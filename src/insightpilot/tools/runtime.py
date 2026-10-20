from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class AnalysisContext:
    """Trạng thái chạy được các Tool dùng chung trong một phiên phân tích."""

    df: pd.DataFrame | None = None
    source: str | None = None
    last_result: dict = field(default_factory=dict)

    def require_dataset(self) -> pd.DataFrame:
        """Trả về dataset hiện tại hoặc phát sinh lỗi dễ hiểu."""
        if self.df is None:
            raise RuntimeError("No dataset is loaded. Call 'load_dataset' first.")
        return self.df

    def set_dataset(self, df: pd.DataFrame, source: str | Path | None = None) -> None:
        """Lưu dataset vào phiên phân tích hiện tại."""
        self.df = df
        self.source = str(source) if source is not None else None
        self.last_result = {}
