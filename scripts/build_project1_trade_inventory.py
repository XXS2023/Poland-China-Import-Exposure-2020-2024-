#!/usr/bin/env python3
"""
Build a small source-inventory CSV for Project 1.

This script profiles the currently reachable Eurostat trade dataflows and
records whether they appear suitable for a China/Poland import-exposure build.
It is intentionally conservative: before the final extraction source is fixed,
we first keep a clean audit trail of the usable trade datasets.
"""

from __future__ import annotations

import argparse
import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import requests


BASE = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1"
DATAFLOW_URL = f"{BASE}/dataflow/ESTAT"
USER_AGENT = "ESP Project 1 Trade Inventory (contact: local-analysis)"

NS = {
    "m": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message",
    "s": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure",
    "c": "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common",
}


@dataclass
class SourceRow:
    flow_id: str
    title: str
    version: str
    dimensions: str
    has_partner: bool
    has_geo: bool
    has_product: bool
    partner_cn_probe: str
    partner_cn_probe_note: str


def _get(url: str) -> requests.Response:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp


def _text_list(parent, tag: str) -> List[str]:
    return [node.text for node in parent.findall(tag, NS) if node.text]


def fetch_trade_dataflows() -> List[dict]:
    xml = _get(DATAFLOW_URL).text
    root = ET.fromstring(xml)
    dataflows = []

    for df in root.findall(".//s:Dataflow", NS):
        flow_id = df.attrib.get("id", "")
        title = " | ".join(_text_list(df, "c:Name"))
        structure = df.find("s:Structure", NS)
        ref = None
        if structure is not None:
            ref = structure.find("Ref")
            if ref is None:
                ref = structure.find(".//Ref")
        if not flow_id or ref is None:
            continue
        dataflows.append(
            {
                "flow_id": flow_id,
                "title": title,
                "version": ref.attrib.get("version", ""),
                "dsd_id": ref.attrib.get("id", ""),
                "dsd_version": ref.attrib.get("version", ""),
            }
        )
    return dataflows


def fetch_dimensions(flow_id: str, dsd_version: str) -> List[str]:
    url = f"{BASE}/datastructure/ESTAT/{flow_id}/{dsd_version}"
    xml = _get(url).text
    root = ET.fromstring(xml)
    dsd = root.find(".//s:DataStructure", NS)
    if dsd is None:
        return []
    dims = dsd.find(".//s:DimensionList", NS)
    if dims is None:
        return []
    return [dim.attrib.get("id", "") for dim in dims if dim.attrib.get("id")]


def probe_partner_cn(flow_id: str, dimensions: List[str]) -> tuple[str, str]:
    """
    Try a narrow Poland/China import query to see whether the flow supports it.

    The probe is intentionally tiny and only checks whether the query is accepted.
    """

    # Known key templates for the datasets we found so far.
    if flow_id == "TET00002":
        # freq.indic_et.sitc06.partner.unit.geo
        key = "A.MIO_IMP_VAL.TOTAL.CN.MIO_EUR.PL"
    elif flow_id in {"EXT_LT_INTRATRD", "EXT_LT_INTERCC", "EXT_LT_INTERTRD"}:
        # freq.indic_et.sitc06.partner.geo
        key = "A.MIO_IMP_VAL.TOTAL.CN.PL"
    else:
        return ("not-tested", "flow not in current probe set")

    url = f"{BASE}/data/{flow_id}/{key}?startPeriod=2024&endPeriod=2024"
    try:
        resp = _get(url)
    except requests.HTTPError as exc:
        text = exc.response.text if exc.response is not None else ""
        if "PARTNER=CN" in text or "GEO=CN" in text:
            return ("rejected", "China partner is not accepted by this flow")
        if "INVALID_QUERY_NB_FILTERS" in text:
            return ("rejected", "query shape mismatch")
        return ("error", "unexpected error while probing")
    except requests.RequestException:
        return ("error", "network error while probing")

    return ("accepted", "query returned data")


def build_rows() -> List[SourceRow]:
    candidates = fetch_trade_dataflows()
    wanted = {
        "TET00002",
        "EXT_LT_INTRATRD",
        "EXT_LT_INTERCC",
        "EXT_LT_INTERTRD",
    }

    rows: List[SourceRow] = []
    for flow in candidates:
        if flow["flow_id"] not in wanted:
            continue
        dims = fetch_dimensions(flow["dsd_id"], flow["dsd_version"])
        partner_cn_probe, partner_cn_note = probe_partner_cn(flow["flow_id"], dims)
        rows.append(
            SourceRow(
                flow_id=flow["flow_id"],
                title=flow["title"],
                version=flow["dsd_version"],
                dimensions=";".join(dims),
                has_partner="partner" in dims,
                has_geo="geo" in dims,
                has_product=any(d in dims for d in ["sitc06", "cn", "hs", "prod", "product"]),
                partner_cn_probe=partner_cn_probe,
                partner_cn_probe_note=partner_cn_note,
            )
        )
    return rows


def write_csv(rows: Iterable[SourceRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "flow_id",
                "title",
                "version",
                "dimensions",
                "has_partner",
                "has_geo",
                "has_product",
                "partner_cn_probe",
                "partner_cn_probe_note",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.flow_id,
                    row.title,
                    row.version,
                    row.dimensions,
                    row.has_partner,
                    row.has_geo,
                    row.has_product,
                    row.partner_cn_probe,
                    row.partner_cn_probe_note,
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Project 1 Eurostat source inventory CSV.")
    parser.add_argument(
        "--output",
        default="project1_source_inventory.csv",
        help="Where to write the inventory CSV.",
    )
    args = parser.parse_args()

    rows = build_rows()
    write_csv(rows, Path(args.output))
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
