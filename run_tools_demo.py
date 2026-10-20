from pathlib import Path

from insightpilot.tools import AnalysisContext, ToolRegistry, build_data_tools


ROOT = Path(__file__).parent
DATASET = ROOT / "data" / "sample_sales.csv"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_data_tools():
        registry.register(tool)
    return registry


def main() -> None:
    context = AnalysisContext()
    registry = build_registry()

    print("=== AVAILABLE TOOLS ===")
    for tool in registry.list_tools():
        print(f"- {tool['name']}: {tool['description']}")

    print("\n=== 1. LOAD DATASET ===")
    print(registry.execute("load_dataset", {"path": str(DATASET)}, context))

    print("\n=== 2. ADD REVENUE ===")
    print(
        registry.execute(
            "add_revenue_column",
            {
                "price_col": "price",
                "quantity_col": "quantity",
                "revenue_col": "revenue",
            },
            context,
        )
    )

    print("\n=== 3. COMPARE LAST TWO MONTHS ===")
    print(
        registry.execute(
            "compare_last_two_periods",
            {
                "date_col": "date",
                "metric_col": "revenue",
                "freq": "MS",
                "agg": "sum",
            },
            context,
        )
    )

    print("\n=== 4. TOP PRODUCTS ===")
    print(
        registry.execute(
            "group_metric",
            {
                "dimension_col": "product",
                "metric_col": "revenue",
                "agg": "sum",
                "top_n": 3,
            },
            context,
        )
    )


if __name__ == "__main__":
    main()
