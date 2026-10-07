"""Transparent investigation priorities; scores are heuristics, not forecasts."""
import numpy as np
import pandas as pd


def rank_recommendations(aggregated, minimum_gap=0):
    result = aggregated.loc[aggregated["opportunity"] > max(0, minimum_gap)].copy()
    result["sales_gap"] = result["sales_growth_rm"] - result["sales_growth_willow"]
    result["unit_gap"] = result["unit_growth_rm"] - result["unit_growth_willow"]
    if "willow_aup" not in result:
        result["willow_aup"] = result["willow_sales"].div(result["willow_units"].replace(0, np.nan))
    if "rm_aup" not in result:
        result["rm_aup"] = result["rm_sales"].div(result["rm_units"].replace(0, np.nan))
    result["price_gap"] = (result["willow_aup"].div(result["rm_aup"].replace(0, np.nan)) - 1) * 100
    maximum = result["opportunity"].max()
    opportunity_score = result["opportunity"] / maximum * 50 if len(result) else 0
    result["score"] = (
        opportunity_score
        + result["sales_gap"].fillna(0).clip(0, 10) * 3
        + result["unit_gap"].fillna(0).clip(0, 10) * 2
    ).round(1)
    result["priority"] = np.select(
        [result["score"] >= 70, result["score"] >= 40],
        ["High", "Medium"], default="Review"
    )
    return result.sort_values(["score", "opportunity"], ascending=False).reset_index(drop=True)


def explain_recommendation(row):
    reasons = [f"${row['opportunity']:,.0f} estimated opportunity"]
    for field, label in [("sales_gap", "sales growth"), ("unit_gap", "unit growth")]:
        value = row[field]
        if pd.notna(value):
            if value > 0:
                reasons.append(f"Willow {label} trails RM by {value:.1f} percentage points")
            else:
                reasons.append(f"Willow {label} matches or exceeds RM")
        else:
            reasons.append(f"{label.capitalize()} comparison unavailable")
    if pd.notna(row["price_gap"]) and abs(row["price_gap"]) >= 10:
        direction = "above" if row["price_gap"] > 0 else "below"
        reasons.append(f"average unit price is {abs(row['price_gap']):.1f}% {direction} RM; investigate pricing and product mix")
    return "; ".join(reasons) + "."
