from __future__ import annotations

from insightpilot.tools import AnalysisContext, ToolRegistry, build_data_tools

from .executor import AnalysisExecutor
from .models import AnalysisPlan, AnalysisStep


def build_demo_plan() -> AnalysisPlan:
    """Ví dụ có kết quả xác định, chạy được mà không cần mô hình ngôn ngữ hoặc gọi API."""
    return AnalysisPlan(
        goal=(
            "Prepare evidence for the question: What are the top 3 products by "
            "total revenue, and how did overall revenue change between the two "
            "most recent months?"
        ),
        steps=[
            AnalysisStep(
                id="step_1",
                purpose="Inspect the current dataset schema before calculation.",
                tool_name="profile_dataset",
            ),
            AnalysisStep(
                id="step_2",
                purpose="Create revenue from price and quantity for downstream analysis.",
                tool_name="add_revenue_column",
                arguments={
                    "price_col": "price",
                    "quantity_col": "quantity",
                    "revenue_col": "revenue",
                },
                depends_on=["step_1"],
            ),
            AnalysisStep(
                id="step_3",
                purpose="Find the top 3 products by total revenue.",
                tool_name="group_metric",
                arguments={
                    "dimension_col": "product",
                    "metric_col": "revenue",
                    "agg": "sum",
                    "top_n": 3,
                },
                depends_on=["step_2"],
            ),
            AnalysisStep(
                id="step_4",
                purpose="Compare the two most recent monthly revenue totals.",
                tool_name="compare_last_two_periods",
                arguments={
                    "date_col": "date",
                    "metric_col": "revenue",
                    "freq": "MS",
                    "agg": "sum",
                },
                depends_on=["step_2"],
            ),
        ],
    )


def run_demo() -> dict:
    context = AnalysisContext()
    registry = ToolRegistry()
    for tool in build_data_tools():
        registry.register(tool)

    registry.execute(
        "load_dataset",
        {"path": "data/sample_sales.csv"},
        context,
    )

    plan = build_demo_plan()
    execution = AnalysisExecutor(registry, context).execute_plan(plan)

    return {
        "plan": execution.plan.to_dict(),
        "step_results": execution.step_results,
    }
