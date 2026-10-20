from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def json_safe(value: Any) -> Any:
    """Chuyển các giá trị pandas/numpy thường gặp thành kiểu Python tương thích với JSON."""
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if not np.isnan(value) else None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Chuyển DataFrame thành danh sách dictionary theo từng dòng, tương thích với JSON."""
    records = df.to_dict(orient="records")
    return [
        {str(key): json_safe(value) for key, value in row.items()}
        for row in records
    ]
