#!/usr/bin/env python3
"""
Build Project 1 trade exposure CSV from OEC BACI annual HS2 data.

The script collects Poland's imports from China and total Polish imports for
each HS2 chapter, then computes the China import share by year.

Current public coverage in this source runs through 2024.

Why this script exists:
1. We need a clean sector-by-year table before we can do any rankings or charts.
2. The public source we found exposes annual BACI trade data at HS2 level.
3. For each year, we need two building blocks:
   - imports from China to Poland in each HS2 sector
   - total Polish imports in the same HS2 sector from all exporters
4. Once we have those two values, the core exposure formula is simple:
      China share = imports_from_china / total_polish_imports * 100

In interview language, this script is the "data preparation layer" of the
project. It turns raw API responses into one analysis-ready table.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests


BASE_URL = "https://api-v2.oec.world/tesseract/data.jsonrecords"
CUBE = "trade_i_baci_a_17"
DEFAULT_START_YEAR = 2020
DEFAULT_END_YEAR = 2025
# In the BACI cube, "Exporter" means the origin country of the traded goods.
# Because we are studying Polish imports from China, China is the exporter and
# Poland is the importer.
REPORTER_ID = "chn"
IMPORTER_ID = "pol"
LABEL_NORMALIZATION = {
    # These fixes are purely presentational.
    # They do not change the data values; they only make outputs cleaner and
    # easier to present in charts and portfolio materials.
    "Knitted clothing accesories": "Knitted clothing accessories",
    "Non-knitted clothing accesories": "Non-knitted clothing accessories",
    "Cars, tractors, trucks & parts thereof.": "Cars, tractors, trucks & parts thereof",
    "Stone, plaster, cement, asbestos, mica.": "Stone, plaster, cement, asbestos, mica",
}


@dataclass
class QueryResult:
    """
    Small container for one API request result.

    year:
        Which year the query was for.
    rows:
        The raw row objects returned by the API.
    total:
        The API's own count of how many rows matched the query.

    Keeping these three fields together makes it easier to debug coverage.
    """
    year: int
    rows: List[dict]
    total: int


def fetch_rows(year: int, exporter_id: Optional[str] = None) -> QueryResult:
    """
    Query the BACI API for one year of trade data.

    exporter_id = "chn"
        Returns only China -> Poland rows for that year.

    exporter_id = None
        Returns all exporter countries -> Poland rows for that year.

    This two-query design is central to the analysis:
    - the China-filtered query gives the numerator
    - the all-exporters query gives the denominator
    """
    params = {
        "cube": CUBE,
        # We request HS2 because our project was intentionally scoped to a
        # practical, interview-friendly sector level instead of HS6 detail.
        "drilldowns": "Exporter Country Official,Importer Country Official,HS2 Official,Year",
        "measures": "Trade Value",
        "Importer Country Official": IMPORTER_ID,
        "Year": year,
        "locale": "en",
    }
    if exporter_id is not None:
        params["Exporter Country Official"] = exporter_id

    resp = requests.get(BASE_URL, params=params, timeout=120)
    resp.raise_for_status()
    payload = resp.json()
    # We return both the raw data rows and the API-reported total count.
    # The total count is useful for checking coverage later.
    return QueryResult(year=year, rows=payload.get("data", []), total=payload.get("page", {}).get("total", 0))


def rows_to_frame(rows: List[dict]) -> pd.DataFrame:
    """
    Convert raw API records into a pandas DataFrame.

    Why not go straight into analysis?
    Because API responses are JSON lists, while pandas gives us:
    - grouping
    - filtering
    - numeric conversion
    - merging
    - exporting

    This function is also where we do lightweight cleaning:
    - ensure Trade Value is numeric
    - ensure Year is numeric
    - normalize messy labels
    - drop unusable rows with missing numeric fields
    """
    if not rows:
        # Returning an empty DataFrame with the expected columns keeps the rest
        # of the pipeline stable even when a year has no public data.
        return pd.DataFrame(
            columns=[
                "Exporter Country Official ID",
                "Exporter Country Official",
                "HS2 Official ID",
                "HS2 Official",
                "Importer Country Official ID",
                "Importer Country Official",
                "Year",
                "Trade Value",
            ]
        )
    df = pd.DataFrame(rows)
    df["Trade Value"] = pd.to_numeric(df["Trade Value"], errors="coerce")
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["HS2 Official"] = df["HS2 Official"].replace(LABEL_NORMALIZATION)
    return df.dropna(subset=["Trade Value", "Year"])


def aggregate_year(year: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build the sector-level metrics for one year.

    Output 1: merged sector table for one year
    Output 2: one-row coverage table for diagnostics

    The logic is:
    1. Pull China -> Poland rows for the given year.
    2. Pull all exporters -> Poland rows for the same year.
    3. Aggregate both datasets to HS2 sector level.
    4. Merge them on year + HS2 code + HS2 label.
    5. Compute the China share.
    """
    china_result = fetch_rows(year, exporter_id=REPORTER_ID)
    total_result = fetch_rows(year, exporter_id=None)

    china_df = rows_to_frame(china_result.rows)
    total_df = rows_to_frame(total_result.rows)

    # Numerator:
    # total Chinese exports received by Poland in each HS2 sector in that year.
    china_agg = (
        china_df.groupby(["Year", "HS2 Official ID", "HS2 Official"], as_index=False)["Trade Value"]
        .sum()
        .rename(columns={"Trade Value": "imports_from_china"})
    )

    # Denominator:
    # total Polish imports from all exporter countries in the same HS2 sector.
    total_agg = (
        total_df.groupby(["Year", "HS2 Official ID", "HS2 Official"], as_index=False)["Trade Value"]
        .sum()
        .rename(columns={"Trade Value": "total_polish_imports"})
    )

    # Left merge keeps the full set of Polish import sectors even if China had
    # zero reported exports in one of them.
    merged = total_agg.merge(
        china_agg,
        on=["Year", "HS2 Official ID", "HS2 Official"],
        how="left",
    )

    # If China has no value in a sector, that should be interpreted as zero
    # exposure in this source, not as a missing value.
    merged["imports_from_china"] = merged["imports_from_china"].fillna(0.0)

    # Core portfolio metric:
    # What share of Poland's imports in a given sector came from China?
    merged["china_share_pct"] = (
        merged["imports_from_china"] / merged["total_polish_imports"] * 100.0
    ).where(merged["total_polish_imports"] > 0)
    merged["data_source"] = "OEC BACI trade_i_baci_a_17"
    merged["year_coverage"] = year

    # Coverage table is useful in presentations and troubleshooting.
    # It lets us explicitly show that 2025 has no public data in this source.
    coverage = pd.DataFrame(
        [
            {
                "year": year,
                "china_rows": china_result.total,
                "total_rows": total_result.total,
                "status": "ok" if total_result.total > 0 else "no_data",
            }
        ]
    )
    return merged, coverage


def build_dataset(start_year: int, end_year: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Loop over the full time window and stack each year's outputs together.

    Conceptually:
    - aggregate_year() gives us one tidy sector-year slice
    - build_dataset() concatenates all slices into a panel dataset
    """
    frames: List[pd.DataFrame] = []
    coverage_frames: List[pd.DataFrame] = []

    for year in range(start_year, end_year + 1):
        merged, coverage = aggregate_year(year)
        if not merged.empty:
            frames.append(merged)
        coverage_frames.append(coverage)

    final_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    coverage_df = pd.concat(coverage_frames, ignore_index=True)

    if not final_df.empty:
        # Rename columns into clean, interview-friendly names.
        # This makes the analysis script easier to read.
        final_df = final_df.rename(
            columns={
                "Year": "year",
                "HS2 Official ID": "hs2_code",
                "HS2 Official": "hs2_label",
            }
        )

        # Keep only the fields we actually need downstream.
        final_df = final_df[
            [
                "year",
                "hs2_code",
                "hs2_label",
                "imports_from_china",
                "total_polish_imports",
                "china_share_pct",
                "data_source",
                "year_coverage",
            ]
        # Sort so each year's highest-exposure sectors appear first.
        ].sort_values(["year", "china_share_pct", "total_polish_imports"], ascending=[True, False, False])

    return final_df, coverage_df


def main() -> None:
    """
    Command-line entry point.

    Typical workflow:
        python3 build_project1_trade_csv.py

    This produces:
    - main analysis-ready CSV
    - separate coverage CSV
    """
    parser = argparse.ArgumentParser(description="Build Project 1 trade exposure CSV.")
    parser.add_argument(
        "--start-year",
        type=int,
        default=DEFAULT_START_YEAR,
        help="First year to include.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=DEFAULT_END_YEAR,
        help="Last year to include.",
    )
    parser.add_argument(
        "--output",
        default="project1_trade_exposure.csv",
        help="Main output CSV path.",
    )
    parser.add_argument(
        "--coverage-output",
        default="project1_trade_coverage.csv",
        help="Year coverage CSV path.",
    )
    args = parser.parse_args()

    df, coverage = build_dataset(args.start_year, args.end_year)
    output_path = Path(args.output)
    coverage_path = Path(args.coverage_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    coverage_path.parent.mkdir(parents=True, exist_ok=True)

    # Export both the main dataset and the coverage diagnostics so later stages
    # can distinguish between "zero trade" and "no public data available".
    df.to_csv(output_path, index=False)
    coverage.to_csv(coverage_path, index=False)

    print(f"Wrote {len(df):,} rows to {output_path}")
    print(f"Wrote {len(coverage):,} rows to {coverage_path}")


if __name__ == "__main__":
    main()
