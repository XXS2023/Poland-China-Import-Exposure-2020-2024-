#!/usr/bin/env python3
"""
Create Project 1 analysis outputs from the trade exposure CSV.

Outputs:
- sector metrics table
- ranking tables
- SVG charts
- short executive summary

This is the "analysis layer" of Project 1.

In practical terms, the script answers four business questions:

1. Exposure ranking:
   Which Polish sectors are most dependent on China?

2. Growth in exposure:
   In which sectors has China's role increased the most since 2020?

3. Absolute importance:
   Which sectors matter most in money terms, not just percentages?

4. Portfolio communication:
   How do we convert the numbers into charts and summary tables that are easy
   to explain in an interview or portfolio?
"""

from __future__ import annotations

import argparse
import html
import math
from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd


DEFAULT_INPUT = "project1_trade_exposure.csv"
DEFAULT_OUTPUT_DIR = "project1_analysis"
BAR_COLORS = ["#1f77b4", "#2a9d8f", "#e76f51", "#f4a261", "#6a4c93"]


def pct_change(new_value: float, old_value: float) -> float | None:
    """
    Standard growth-rate formula.

    Example:
        if imports from China rise from 100 to 130,
        pct_change = (130 / 100 - 1) * 100 = 30%

    We return None when the old value is zero or negative because percentage
    growth would be undefined or misleading.
    """
    if old_value <= 0:
        return None
    return (new_value / old_value - 1.0) * 100.0


def cagr(new_value: float, old_value: float, periods: int) -> float | None:
    """
    Compound annual growth rate.

    Why use CAGR?
    A simple total growth figure tells us "how much bigger" something became.
    CAGR tells us the average annual growth pace over multiple years.

    Formula:
        ((new / old) ** (1 / periods) - 1) * 100
    """
    if old_value <= 0 or periods <= 0:
        return None
    return ((new_value / old_value) ** (1.0 / periods) - 1.0) * 100.0


def shorten(label: str, max_len: int = 44) -> str:
    """Shorten long chart labels so exported visuals stay readable."""
    if len(label) <= max_len:
        return label
    return label[: max_len - 1].rstrip() + "…"


def fmt_billions(value: float) -> str:
    """Format large currency-like values for chart annotations."""
    return f"{value / 1_000_000_000:.1f}bn"


def fmt_pct(value: float) -> str:
    """Format percentages consistently."""
    return f"{value:.1f}%"


def fmt_pp(value: float) -> str:
    """Format changes in percentage points."""
    return f"{value:+.1f} pp"


def build_sector_metrics(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """
    Convert the long sector-year dataset into a sector comparison table.

    Input format ("long"):
        one row per year + HS2 sector

    Output format ("wide"):
        one row per HS2 sector, with 2020 and 2024 values side by side

    This wide format is ideal for interview-style business analysis because it
    lets us compare the start year and the latest year directly.
    """
    base_year = int(df["year"].min())
    latest_year = int(df["year"].max())

    # Split the dataset into the starting snapshot and the latest snapshot.
    base = df[df["year"] == base_year].copy()
    latest = df[df["year"] == latest_year].copy()

    # Merge on sector identifiers so each row becomes:
    # HS2 sector + 2020 values + 2024 values
    merged = base.merge(
        latest,
        on=["hs2_code", "hs2_label"],
        suffixes=(f"_{base_year}", f"_{latest_year}"),
    )

    # Change in China share is best expressed in percentage points, not percent.
    # Example:
    # 10% -> 15% is +5 percentage points, not +50 percentage points.
    merged["share_change_pp"] = (
        merged[f"china_share_pct_{latest_year}"] - merged[f"china_share_pct_{base_year}"]
    )

    # Growth in imports from China:
    # this captures how quickly the China-origin value changed.
    merged["china_import_growth_pct"] = merged.apply(
        lambda row: pct_change(
            row[f"imports_from_china_{latest_year}"],
            row[f"imports_from_china_{base_year}"],
        ),
        axis=1,
    )

    # Growth in total Polish imports:
    # useful because sometimes China gains share simply because the entire
    # Polish market is growing, and sometimes because China is growing faster
    # than the market. We want both views.
    merged["total_import_growth_pct"] = merged.apply(
        lambda row: pct_change(
            row[f"total_polish_imports_{latest_year}"],
            row[f"total_polish_imports_{base_year}"],
        ),
        axis=1,
    )

    # CAGR gives a smoother trend measure across the multi-year period.
    merged["china_import_cagr_pct"] = merged.apply(
        lambda row: cagr(
            row[f"imports_from_china_{latest_year}"],
            row[f"imports_from_china_{base_year}"],
            latest_year - base_year,
        ),
        axis=1,
    )

    # Absolute value change answers:
    # "How many more euros/dollars/etc. of imports are we talking about?"
    merged["value_change_from_china"] = (
        merged[f"imports_from_china_{latest_year}"] - merged[f"imports_from_china_{base_year}"]
    )
    merged["value_change_total_imports"] = (
        merged[f"total_polish_imports_{latest_year}"] - merged[f"total_polish_imports_{base_year}"]
    )

    ordered = [
        "hs2_code",
        "hs2_label",
        f"imports_from_china_{base_year}",
        f"imports_from_china_{latest_year}",
        f"total_polish_imports_{base_year}",
        f"total_polish_imports_{latest_year}",
        f"china_share_pct_{base_year}",
        f"china_share_pct_{latest_year}",
        "share_change_pp",
        "china_import_growth_pct",
        "total_import_growth_pct",
        "china_import_cagr_pct",
        "value_change_from_china",
        "value_change_total_imports",
    ]

    # Sort primarily by latest China share and secondarily by latest import value
    # so the most exposed sectors rise to the top.
    return merged[ordered].sort_values(
        [f"china_share_pct_{latest_year}", f"imports_from_china_{latest_year}"],
        ascending=[False, False],
    ), base_year, latest_year


def horizontal_bar_svg(
    df: pd.DataFrame,
    label_col: str,
    value_col: str,
    title: str,
    subtitle: str,
    value_formatter,
    output_path: Path,
    color: str = "#1f77b4",
) -> None:
    """
    Export a simple horizontal bar chart as SVG.

    Why SVG?
    - crisp in presentations and PDFs
    - easy to scale
    - no extra plotting dependency required

    The chart is built manually from rectangles and text labels.
    That is why the code looks longer than a matplotlib version.
    """
    chart = df.copy()
    width = 1200
    top_margin = 120
    left_margin = 380
    right_margin = 120
    row_h = 42
    bar_h = 24
    height = top_margin + len(chart) * row_h + 80
    chart_width = width - left_margin - right_margin
    max_value = chart[value_col].max()
    if max_value <= 0:
        max_value = 1

    # Start the SVG document and add title/subtitle.
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left_margin}" y="42" font-size="28" font-family="Arial" font-weight="bold" fill="#1f2937">{html.escape(title)}</text>',
        f'<text x="{left_margin}" y="72" font-size="15" font-family="Arial" fill="#4b5563">{html.escape(subtitle)}</text>',
    ]

    for i, (_, row) in enumerate(chart.iterrows()):
        # Each row becomes:
        # label on the left + scaled rectangle + formatted value on the right.
        y = top_margin + i * row_h
        label = html.escape(shorten(str(row[label_col]), 52))
        value = float(row[value_col])
        bar_w = chart_width * (value / max_value)
        value_text = html.escape(value_formatter(value))
        parts.append(
            f'<text x="{left_margin - 12}" y="{y + 17}" text-anchor="end" font-size="14" font-family="Arial" fill="#111827">{label}</text>'
        )
        parts.append(
            f'<rect x="{left_margin}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" rx="4" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{left_margin + bar_w + 10:.1f}" y="{y + 17}" font-size="13" font-family="Arial" fill="#111827">{value_text}</text>'
        )

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def scatter_svg(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    size_col: str,
    label_col: str,
    title: str,
    subtitle: str,
    output_path: Path,
) -> None:
    """
    Build an SVG scatter plot.

    Interpretation:
    - x-axis = latest China share
    - y-axis = change in China share since 2020
    - bubble size = latest import value from China

    This is a very useful interview chart because it shows three dimensions at
    once:
    1. current exposure
    2. change in exposure
    3. scale of the sector
    """
    chart = df.copy()
    width = 1200
    height = 760
    left = 110
    right = 90
    top = 110
    bottom = 100
    plot_w = width - left - right
    plot_h = height - top - bottom

    x_min = min(0.0, float(chart[x_col].min()))
    x_max = float(chart[x_col].max()) * 1.05
    y_min = min(0.0, float(chart[y_col].min()))
    y_max = float(chart[y_col].max()) * 1.08
    s_min = float(chart[size_col].min())
    s_max = float(chart[size_col].max())

    def sx(v: float) -> float:
        # Map data-space x values into pixel-space x positions.
        if x_max == x_min:
            return left + plot_w / 2
        return left + (v - x_min) / (x_max - x_min) * plot_w

    def sy(v: float) -> float:
        # SVG y coordinates run downward, so we invert the scale.
        if y_max == y_min:
            return top + plot_h / 2
        return top + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    def sr(v: float) -> float:
        # Convert the import value into a visible bubble radius.
        if s_max == s_min:
            return 10
        return 7 + (v - s_min) / (s_max - s_min) * 24

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="42" font-size="28" font-family="Arial" font-weight="bold" fill="#1f2937">{html.escape(title)}</text>',
        f'<text x="{left}" y="72" font-size="15" font-family="Arial" fill="#4b5563">{html.escape(subtitle)}</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#9ca3af" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#9ca3af" stroke-width="1"/>',
    ]

    for tick in range(6):
        x_val = x_min + (x_max - x_min) * tick / 5
        x_pos = sx(x_val)
        parts.append(f'<line x1="{x_pos:.1f}" y1="{top + plot_h}" x2="{x_pos:.1f}" y2="{top + plot_h + 6}" stroke="#9ca3af"/>')
        parts.append(
            f'<text x="{x_pos:.1f}" y="{top + plot_h + 28}" text-anchor="middle" font-size="12" font-family="Arial" fill="#374151">{html.escape(fmt_pct(x_val))}</text>'
        )

        y_val = y_min + (y_max - y_min) * tick / 5
        y_pos = sy(y_val)
        parts.append(f'<line x1="{left - 6}" y1="{y_pos:.1f}" x2="{left}" y2="{y_pos:.1f}" stroke="#9ca3af"/>')
        parts.append(
            f'<text x="{left - 10}" y="{y_pos + 4:.1f}" text-anchor="end" font-size="12" font-family="Arial" fill="#374151">{html.escape(fmt_pp(y_val))}</text>'
        )

    parts.append(
        f'<text x="{left + plot_w / 2:.1f}" y="{height - 30}" text-anchor="middle" font-size="14" font-family="Arial" fill="#111827">China share in latest year</text>'
    )
    parts.append(
        f'<text x="28" y="{top + plot_h / 2:.1f}" transform="rotate(-90 28 {top + plot_h / 2:.1f})" text-anchor="middle" font-size="14" font-family="Arial" fill="#111827">Change in China share (percentage points)</text>'
    )

    top_labels = chart.nlargest(8, size_col).index
    for idx, row in chart.iterrows():
        # Draw each sector as a bubble.
        x = sx(float(row[x_col]))
        y = sy(float(row[y_col]))
        r = sr(float(row[size_col]))
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#1f77b4" fill-opacity="0.55" stroke="#1f4f7a" stroke-width="1"/>'
        )

        # To avoid clutter, only label the largest bubbles.
        if idx in top_labels:
            parts.append(
                f'<text x="{x + r + 6:.1f}" y="{y + 4:.1f}" font-size="12" font-family="Arial" fill="#111827">{html.escape(shorten(str(row[label_col]), 28))}</text>'
            )

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def line_chart_svg(
    long_df: pd.DataFrame,
    title: str,
    subtitle: str,
    output_path: Path,
) -> None:
    """
    Build a multi-line trend chart showing how China share evolves over time.

    We use this for the biggest import sectors because:
    - they are commercially important
    - they create a strong portfolio narrative
    - a trend line is easier to discuss than a single-year snapshot
    """
    width = 1200
    height = 760
    left = 110
    right = 180
    top = 110
    bottom = 90
    plot_w = width - left - right
    plot_h = height - top - bottom

    years = sorted(long_df["year"].unique().tolist())
    min_year = min(years)
    max_year = max(years)
    y_min = 0.0
    y_max = float(long_df["china_share_pct"].max()) * 1.1

    def sx(year: int) -> float:
        # Convert calendar year into chart x position.
        if max_year == min_year:
            return left + plot_w / 2
        return left + (year - min_year) / (max_year - min_year) * plot_w

    def sy(value: float) -> float:
        # Convert percentage share into chart y position.
        if y_max == y_min:
            return top + plot_h / 2
        return top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="42" font-size="28" font-family="Arial" font-weight="bold" fill="#1f2937">{html.escape(title)}</text>',
        f'<text x="{left}" y="72" font-size="15" font-family="Arial" fill="#4b5563">{html.escape(subtitle)}</text>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#9ca3af" stroke-width="1"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#9ca3af" stroke-width="1"/>',
    ]

    for year in years:
        x = sx(year)
        parts.append(f'<line x1="{x:.1f}" y1="{top + plot_h}" x2="{x:.1f}" y2="{top + plot_h + 6}" stroke="#9ca3af"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_h + 28}" text-anchor="middle" font-size="12" font-family="Arial" fill="#374151">{year}</text>'
        )

    for tick in range(6):
        val = y_min + (y_max - y_min) * tick / 5
        y = sy(val)
        parts.append(f'<line x1="{left - 6}" y1="{y:.1f}" x2="{left}" y2="{y:.1f}" stroke="#9ca3af"/>')
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-size="12" font-family="Arial" fill="#374151">{html.escape(fmt_pct(val))}</text>'
        )

    parts.append(
        f'<text x="28" y="{top + plot_h / 2:.1f}" transform="rotate(-90 28 {top + plot_h / 2:.1f})" text-anchor="middle" font-size="14" font-family="Arial" fill="#111827">China share of Polish imports</text>'
    )

    for idx, (sector, sector_df) in enumerate(long_df.groupby("hs2_label")):
        # One polyline per sector.
        sector_df = sector_df.sort_values("year")
        points = " ".join(f"{sx(int(r.year)):.1f},{sy(float(r.china_share_pct)):.1f}" for r in sector_df.itertuples())
        color = BAR_COLORS[idx % len(BAR_COLORS)]
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>')
        last = sector_df.iloc[-1]
        parts.append(
            f'<text x="{left + plot_w + 12}" y="{sy(float(last.china_share_pct)) + 4:.1f}" font-size="12" font-family="Arial" fill="{color}">{html.escape(shorten(str(sector), 28))}</text>'
        )
        for r in sector_df.itertuples():
            parts.append(
                f'<circle cx="{sx(int(r.year)):.1f}" cy="{sy(float(r.china_share_pct)):.1f}" r="4" fill="{color}"/>'
            )

    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")


def write_summary(
    metrics: pd.DataFrame,
    base_year: int,
    latest_year: int,
    output_path: Path,
) -> None:
    """
    Create a compact text summary for quick reading.

    This is useful for:
    - portfolio write-ups
    - interview preparation
    - executive-brief drafting
    """
    top_exposure = metrics.nlargest(5, f"china_share_pct_{latest_year}")
    top_share_gain = metrics.nlargest(5, "share_change_pp")
    top_value = metrics.nlargest(5, f"imports_from_china_{latest_year}")

    lines = [
        "Project 1 Executive Summary",
        "",
        f"Source window: {base_year}-{latest_year}",
        "Note: the public source currently has no 2025 data, so this version uses 2024 as the latest year.",
        "",
        f"Top exposure sectors in {latest_year}:",
    ]
    for row in top_exposure.itertuples():
        lines.append(
            f"- HS {row.hs2_code} {row.hs2_label}: {row.__getattribute__(f'china_share_pct_{latest_year}'):.1f}% China share"
        )

    lines.append("")
    lines.append(f"Fastest increases in China share, {base_year}-{latest_year}:")
    for row in top_share_gain.itertuples():
        lines.append(f"- HS {row.hs2_code} {row.hs2_label}: {row.share_change_pp:+.1f} percentage points")

    lines.append("")
    lines.append(f"Largest Polish imports from China in {latest_year}:")
    for row in top_value.itertuples():
        lines.append(
            f"- HS {row.hs2_code} {row.hs2_label}: {fmt_billions(row.__getattribute__(f'imports_from_china_{latest_year}'))}"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """
    Main execution flow.

    Sequence:
    1. Load the cleaned trade exposure CSV.
    2. Build sector comparison metrics.
    3. Export ranking tables.
    4. Export charts.
    5. Export a concise summary note.
    """
    parser = argparse.ArgumentParser(description="Build Project 1 analysis outputs.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Input trade exposure CSV.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics, base_year, latest_year = build_sector_metrics(df)
    metrics_path = output_dir / "sector_metrics_2020_2024.csv"
    metrics.to_csv(metrics_path, index=False)

    # Ranking 1:
    # sectors with the highest China share in the latest year.
    top_exposure = metrics.nlargest(15, f"china_share_pct_{latest_year}")[
        ["hs2_code", "hs2_label", f"china_share_pct_{latest_year}", f"imports_from_china_{latest_year}", f"total_polish_imports_{latest_year}"]
    ]
    top_exposure.to_csv(output_dir / "top_exposure_2024.csv", index=False)

    # Ranking 2:
    # sectors where China's share increased the most over the full period.
    top_share_gain = metrics.nlargest(15, "share_change_pp")[
        ["hs2_code", "hs2_label", "share_change_pp", f"china_share_pct_{base_year}", f"china_share_pct_{latest_year}", "china_import_growth_pct"]
    ]
    top_share_gain.to_csv(output_dir / "top_share_gain_2020_2024.csv", index=False)

    # Ranking 3:
    # sectors with the largest absolute import value from China.
    top_import_value = metrics.nlargest(15, f"imports_from_china_{latest_year}")[
        ["hs2_code", "hs2_label", f"imports_from_china_{latest_year}", f"china_share_pct_{latest_year}", "share_change_pp"]
    ]
    top_import_value.to_csv(output_dir / "top_import_value_2024.csv", index=False)

    # Ranking 4:
    # sectors with the fastest raw growth in imports from China.
    top_growth = metrics.dropna(subset=["china_import_growth_pct"]).nlargest(15, "china_import_growth_pct")[
        ["hs2_code", "hs2_label", "china_import_growth_pct", "china_import_cagr_pct", "share_change_pp"]
    ]
    top_growth.to_csv(output_dir / "top_growth_2020_2024.csv", index=False)

    # The first three charts correspond directly to the three most useful
    # portfolio ranking questions:
    # exposure, growth in exposure, and absolute value.
    horizontal_bar_svg(
        top_exposure.head(10).sort_values(f"china_share_pct_{latest_year}"),
        "hs2_label",
        f"china_share_pct_{latest_year}",
        f"Top Poland sectors by China share ({latest_year})",
        "HS2 sectors ranked by China's share of total Polish imports",
        fmt_pct,
        output_dir / "chart_top_exposure_2024.svg",
        color="#1f77b4",
    )
    horizontal_bar_svg(
        top_share_gain.head(10).sort_values("share_change_pp"),
        "hs2_label",
        "share_change_pp",
        f"Fastest increases in China exposure ({base_year}-{latest_year})",
        "HS2 sectors ranked by change in China's share of Polish imports",
        fmt_pp,
        output_dir / "chart_top_share_gain_2020_2024.svg",
        color="#2a9d8f",
    )
    horizontal_bar_svg(
        top_import_value.head(10).sort_values(f"imports_from_china_{latest_year}"),
        "hs2_label",
        f"imports_from_china_{latest_year}",
        f"Largest Polish imports from China ({latest_year})",
        "HS2 sectors ranked by import value from China",
        fmt_billions,
        output_dir / "chart_top_import_value_2024.svg",
        color="#e76f51",
    )

    # The scatter chart adds a more strategic view:
    # current dependence vs direction of change.
    scatter_svg(
        metrics,
        f"china_share_pct_{latest_year}",
        "share_change_pp",
        f"imports_from_china_{latest_year}",
        "hs2_label",
        f"China exposure vs exposure growth ({latest_year})",
        "Bubble size = Polish imports from China; x = latest-year share; y = change in share since 2020",
        output_dir / "chart_exposure_vs_growth_2024.svg",
    )

    # For the trend chart, we choose the five largest China-import sectors
    # because they are the most commercially meaningful sectors to track.
    selected_labels = top_import_value.head(5)["hs2_label"].tolist()
    line_chart_svg(
        df[df["hs2_label"].isin(selected_labels)].sort_values(["hs2_label", "year"]),
        "China share trends in major import sectors",
        "Top five sectors by latest China import value",
        output_dir / "chart_share_trends_major_sectors.svg",
    )

    write_summary(metrics, base_year, latest_year, output_dir / "executive_summary.txt")
    print(f"Analysis outputs written to {output_dir}")


if __name__ == "__main__":
    main()
