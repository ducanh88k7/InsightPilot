import pandas as pd

from insightpilot.analysis.basic import (
    add_revenue_column,
    compare_last_two_periods,
    group_metric,
    period_metric,
)
from insightpilot.data.profile import profile_dataset


def make_sales_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-07-01", "2026-07-10", "2026-08-01", "2026-08-10"],
            "product": ["A", "B", "A", "B"],
            "price": [100, 200, 80, 180],
            "quantity": [10, 5, 5, 4],
        }
    )


def test_add_revenue_column():
    df = add_revenue_column(make_sales_df())
    assert df["revenue"].tolist() == [1000, 1000, 400, 720]


def test_period_metric_and_compare():
    df = add_revenue_column(make_sales_df())
    monthly = period_metric(df, "date", "revenue")
    comparison = compare_last_two_periods(monthly, "date", "revenue")
    assert comparison["previous"] == 2000
    assert comparison["current"] == 1120
    assert round(comparison["percentage_change"], 2) == -44.0


def test_group_metric():
    df = add_revenue_column(make_sales_df())
    grouped = group_metric(df, "product", "revenue")
    assert grouped.iloc[0]["product"] == "B"
    assert grouped.iloc[0]["revenue"] == 1720


def test_profile_dataset():
    profile = profile_dataset(make_sales_df())
    assert profile["row_count"] == 4
    assert profile["column_count"] == 4
    assert "price" in profile["numeric_columns"]
