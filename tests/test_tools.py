from pathlib import Path

import pytest

from insightpilot.tools import AnalysisContext, ToolRegistry, build_data_tools


ROOT = Path(__file__).parent.parent
DATASET = ROOT / "data" / "sample_sales.csv"


@pytest.fixture()
def registry_and_context() -> tuple[ToolRegistry, AnalysisContext]:
    registry = ToolRegistry()
    for tool in build_data_tools():
        registry.register(tool)
    return registry, AnalysisContext()


def test_load_dataset_tool(registry_and_context):
    registry, context = registry_and_context
    result = registry.execute("load_dataset", {"path": str(DATASET)}, context)

    assert result["status"] == "ok"
    assert result["profile"]["row_count"] == 8
    assert context.df is not None


def test_tool_schema_has_required_fields(registry_and_context):
    registry, _ = registry_and_context
    tools = registry.list_tools()

    assert {tool["name"] for tool in tools} == {
        "add_revenue_column",
        "compare_last_two_periods",
        "group_metric",
        "load_dataset",
        "period_metric",
        "profile_dataset",
    }
    assert all("description" in tool for tool in tools)
    assert all("parameters" in tool for tool in tools)


def test_add_revenue_and_compare(registry_and_context):
    registry, context = registry_and_context
    registry.execute("load_dataset", {"path": str(DATASET)}, context)
    revenue_result = registry.execute(
        "add_revenue_column",
        {"price_col": "price", "quantity_col": "quantity", "revenue_col": "revenue"},
        context,
    )
    comparison = registry.execute(
        "compare_last_two_periods",
        {"date_col": "date", "metric_col": "revenue", "freq": "MS", "agg": "sum"},
        context,
    )

    assert revenue_result["revenue_column"] == "revenue"
    assert comparison["previous"] == 26000.0
    assert comparison["current"] == 16750.0
    assert round(comparison["percentage_change"], 2) == -35.58


def test_group_metric_tool(registry_and_context):
    registry, context = registry_and_context
    registry.execute("load_dataset", {"path": str(DATASET)}, context)
    registry.execute("add_revenue_column", {}, context)

    result = registry.execute(
        "group_metric",
        {
            "dimension_col": "product",
            "metric_col": "revenue",
            "agg": "sum",
            "top_n": 2,
        },
        context,
    )

    assert result["rows"][0]["product"] == "Laptop"
    assert result["rows"][0]["revenue"] == 34800
    assert len(result["rows"]) == 2


def test_tool_requires_dataset(registry_and_context):
    registry, context = registry_and_context
    with pytest.raises(RuntimeError, match="No dataset is loaded"):
        registry.execute("profile_dataset", {}, context)


def test_registry_rejects_tool_that_returns_non_dictionary():
    from insightpilot.tools import ToolSpec

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="bad_tool",
            description="Tool used to test output contract.",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            execute=lambda context, arguments: "not a dictionary",
        )
    )

    with pytest.raises(TypeError, match="must return a dictionary"):
        registry.execute("bad_tool", {}, AnalysisContext())
