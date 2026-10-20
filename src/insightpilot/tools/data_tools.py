from __future__ import annotations

from typing import Any

from insightpilot.analysis.basic import (
    add_revenue_column,
    compare_last_two_periods,
    group_metric,
    period_metric,
)
from insightpilot.data.loader import load_dataset
from insightpilot.data.profile import profile_dataset

from .helpers import dataframe_to_records
from .registry import ToolSpec
from .runtime import AnalysisContext


def _load_dataset(context: AnalysisContext, arguments: dict[str, Any]) -> dict[str, Any]:
    path = arguments["path"]
    df = load_dataset(path)
    context.set_dataset(df, source=path)
    return {
        "status": "ok",
        "source": str(path),
        "profile": profile_dataset(df),
    }


def _profile_dataset(context: AnalysisContext, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    df = context.require_dataset()
    return profile_dataset(df)


def _add_revenue(context: AnalysisContext, arguments: dict[str, Any]) -> dict[str, Any]:
    df = context.require_dataset()
    result = add_revenue_column(
        df,
        price_col=arguments.get("price_col", "price"),
        quantity_col=arguments.get("quantity_col", "quantity"),
        revenue_col=arguments.get("revenue_col", "revenue"),
    )
    context.df = result
    revenue_col = arguments.get("revenue_col", "revenue")
    return {
        "status": "ok",
        "revenue_column": revenue_col,
        "row_count": len(result),
        "sample": dataframe_to_records(result[[revenue_col]].head(5)),
    }


def _period_metric(context: AnalysisContext, arguments: dict[str, Any]) -> dict[str, Any]:
    df = context.require_dataset()
    result = period_metric(
        df,
        date_col=arguments["date_col"],
        metric_col=arguments["metric_col"],
        freq=arguments.get("freq", "MS"),
        agg=arguments.get("agg", "sum"),
    )
    return {
        "status": "ok",
        "date_col": arguments["date_col"],
        "metric_col": arguments["metric_col"],
        "frequency": arguments.get("freq", "MS"),
        "aggregation": arguments.get("agg", "sum"),
        "rows": dataframe_to_records(result),
    }


def _group_metric(context: AnalysisContext, arguments: dict[str, Any]) -> dict[str, Any]:
    df = context.require_dataset()
    result = group_metric(
        df,
        dimension_col=arguments["dimension_col"],
        metric_col=arguments["metric_col"],
        agg=arguments.get("agg", "sum"),
        top_n=arguments.get("top_n"),
    )
    return {
        "status": "ok",
        "dimension_col": arguments["dimension_col"],
        "metric_col": arguments["metric_col"],
        "aggregation": arguments.get("agg", "sum"),
        "top_n": arguments.get("top_n"),
        "rows": dataframe_to_records(result),
    }


def _compare_last_two_periods(
    context: AnalysisContext,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    df = context.require_dataset()
    date_col = arguments["date_col"]
    metric_col = arguments["metric_col"]
    freq = arguments.get("freq", "MS")
    agg = arguments.get("agg", "sum")

    period_df = period_metric(
        df,
        date_col=date_col,
        metric_col=metric_col,
        freq=freq,
        agg=agg,
    )
    comparison = compare_last_two_periods(
        period_df,
        date_col=date_col,
        metric_col=metric_col,
    )
    return {
        "status": "ok",
        "date_col": date_col,
        "metric_col": metric_col,
        "frequency": freq,
        "aggregation": agg,
        **comparison,
    }


def build_data_tools() -> list[ToolSpec]:
    """Tạo bộ Tool của Milestone 2."""
    return [
        ToolSpec(
            name="load_dataset",
            description="Load a CSV or Excel dataset into the current analysis session.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Local path to a CSV, XLSX, or XLS file.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            execute=_load_dataset,
        ),
        ToolSpec(
            name="profile_dataset",
            description="Inspect the currently loaded dataset: size, columns, types, missing values, and unique counts.",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            execute=_profile_dataset,
        ),
        ToolSpec(
            name="add_revenue_column",
            description="Create a revenue column by multiplying a price column by a quantity column.",
            input_schema={
                "type": "object",
                "properties": {
                    "price_col": {"type": "string", "description": "Price column name."},
                    "quantity_col": {"type": "string", "description": "Quantity column name."},
                    "revenue_col": {"type": "string", "description": "Output revenue column name."},
                },
                "required": [],
                "additionalProperties": False,
            },
            execute=_add_revenue,
        ),
        ToolSpec(
            name="period_metric",
            description="Aggregate a metric over time, such as monthly or weekly revenue.",
            input_schema={
                "type": "object",
                "properties": {
                    "date_col": {"type": "string", "description": "Date column name."},
                    "metric_col": {"type": "string", "description": "Numeric metric column name."},
                    "freq": {"type": "string", "description": "Pandas frequency such as MS for month start."},
                    "agg": {"type": "string", "description": "Aggregation such as sum, mean, min, or max."},
                },
                "required": ["date_col", "metric_col"],
                "additionalProperties": False,
            },
            execute=_period_metric,
        ),
        ToolSpec(
            name="group_metric",
            description="Aggregate a numeric metric by a categorical dimension, optionally returning only the top N groups.",
            input_schema={
                "type": "object",
                "properties": {
                    "dimension_col": {"type": "string", "description": "Column used for grouping."},
                    "metric_col": {"type": "string", "description": "Numeric metric column name."},
                    "agg": {"type": "string", "description": "Aggregation such as sum, mean, min, or max."},
                    "top_n": {"type": "integer", "minimum": 1, "description": "Optional number of top groups to return."},
                },
                "required": ["dimension_col", "metric_col"],
                "additionalProperties": False,
            },
            execute=_group_metric,
        ),
        ToolSpec(
            name="compare_last_two_periods",
            description="Compare the two most recent time periods for a metric and calculate absolute and percentage change.",
            input_schema={
                "type": "object",
                "properties": {
                    "date_col": {"type": "string", "description": "Date column name."},
                    "metric_col": {"type": "string", "description": "Numeric metric column name."},
                    "freq": {"type": "string", "description": "Pandas frequency such as MS for month start."},
                    "agg": {"type": "string", "description": "Aggregation such as sum, mean, min, or max."},
                },
                "required": ["date_col", "metric_col"],
                "additionalProperties": False,
            },
            execute=_compare_last_two_periods,
        ),
    ]
