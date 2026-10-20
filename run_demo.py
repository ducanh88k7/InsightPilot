from pathlib import Path

from insightpilot.analysis.basic import (
    add_revenue_column,
    compare_last_two_periods,
    group_metric,
    period_metric,
)
from insightpilot.data.loader import load_dataset
from insightpilot.data.profile import profile_dataset


DATASET = Path(__file__).parent / "data" / "sample_sales.csv"


def main() -> None:
    df = load_dataset(DATASET)
    profile = profile_dataset(df)

    print("=== DATASET PROFILE ===")
    print(profile)

    df = add_revenue_column(df)
    monthly = period_metric(df, "date", "revenue")
    comparison = compare_last_two_periods(monthly, "date", "revenue")
    by_product = group_metric(df, "product", "revenue", top_n=5)

    print("\n=== MONTHLY REVENUE ===")
    print(monthly.to_string(index=False))

    print("\n=== PERIOD COMPARISON ===")
    print(comparison)

    print("\n=== TOP PRODUCTS ===")
    print(by_product.to_string(index=False))


if __name__ == "__main__":
    main()
