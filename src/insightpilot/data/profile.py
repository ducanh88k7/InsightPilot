from __future__ import annotations

from typing import Any

import pandas as pd


def profile_dataset(df: pd.DataFrame) -> dict[str, Any]:
    """Trả về hồ sơ dataset gọn nhẹ, tương thích với JSON để Agent sử dụng.
        
            Agent dùng kết quả này để hiểu cấu trúc dữ liệu trước khi quyết định
            cần gọi những công cụ phân tích nào.
            
        """
    numeric_columns = df.select_dtypes(include="number").columns.tolist()
    categorical_columns = df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    columns: list[dict[str, Any]] = []
    for column in df.columns:
        series = df[column]
        columns.append(
            {
                "name": column,
                "dtype": str(series.dtype),
                "missing_count": int(series.isna().sum()),
                "unique_count": int(series.nunique(dropna=True)),
            }
        )

    return {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
        "numeric_columns": numeric_columns,
        "categorical_columns": categorical_columns,
    }
