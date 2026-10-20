from __future__ import annotations

import pandas as pd


def add_revenue_column(
    df: pd.DataFrame,
    price_col: str = "price",
    quantity_col: str = "quantity",
    revenue_col: str = "revenue",
) -> pd.DataFrame:
    """Tạo cột doanh thu nếu cột này chưa tồn tại."""
    result = df.copy()
    if revenue_col in result.columns:
        return result
    missing = [c for c in (price_col, quantity_col) if c not in result.columns]
    if missing:
        raise ValueError(f"Cannot create '{revenue_col}'. Missing columns: {missing}")
    result[revenue_col] = result[price_col] * result[quantity_col]
    return result


def period_metric(
    df: pd.DataFrame,
    date_col: str,
    metric_col: str,
    freq: str = "MS",
    agg: str = "sum",
) -> pd.DataFrame:
    """Tổng hợp một chỉ số theo thời gian."""
    if date_col not in df.columns:
        raise KeyError(f"Date column not found: {date_col}")
    if metric_col not in df.columns:
        raise KeyError(f"Metric column not found: {metric_col}")
    result = df.copy()
    result[date_col] = pd.to_datetime(result[date_col], errors="coerce")
    result = result.dropna(subset=[date_col])
    return (
        result.set_index(date_col)[metric_col]
        .resample(freq)
        .agg(agg)
        .reset_index()
    )


def group_metric(
    df: pd.DataFrame,
    dimension_col: str,
    metric_col: str,
    agg: str = "sum",
    top_n: int | None = None,
) -> pd.DataFrame:
    """Tổng hợp một chỉ số theo một chiều phân loại."""
    for column in (dimension_col, metric_col):
        if column not in df.columns:
            raise KeyError(f"Column not found: {column}")
    result = (
        df.groupby(dimension_col, dropna=False)[metric_col]
        .agg(agg)
        .reset_index(name=metric_col)
        .sort_values(metric_col, ascending=False)
    )
    if top_n is not None:
        result = result.head(top_n).reset_index(drop=True)
    return result


def compare_last_two_periods(
    period_df: pd.DataFrame,
    date_col: str,
    metric_col: str,
) -> dict[str, float | None]:
    """So sánh hai kỳ cuối cùng trong bảng đã được tổng hợp."""
    if len(period_df) < 2:
        return {"previous": None, "current": None, "absolute_change": None, "percentage_change": None}
    ordered = period_df.sort_values(date_col).reset_index(drop=True)
    previous = float(ordered.iloc[-2][metric_col])
    current = float(ordered.iloc[-1][metric_col])
    absolute_change = current - previous
    percentage_change = None if previous == 0 else absolute_change / previous * 100
    return {
        "previous": previous,
        "current": current,
        "absolute_change": absolute_change,
        "percentage_change": percentage_change,
    }
