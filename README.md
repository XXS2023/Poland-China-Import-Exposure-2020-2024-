# Poland–China Import Exposure (2020–2024)

A portfolio project in **trade analysis, market research, and business intelligence**, measuring Poland's sector-level import exposure to China using annual HS2 trade data.

---

## Overview

This project examines where Poland is most exposed to Chinese imports and how that exposure changed between 2020 and 2024.

It combines:

- trade data collection
- sector-level exposure analysis
- growth analysis
- business interpretation
- portfolio-ready charts and summary tables

The core question is not only **how much Poland imports from China**, but also **how dependent different sectors are on China within Poland's total import structure**.

---

## Research question

**Which product sectors showed the strongest and/or fastest-growing Polish import exposure to China between 2020 and 2024?**

---

## Core metric

```text
China share = imports_from_china / total_polish_imports * 100
```

This measures how important China is within Poland's imports in each HS2 product sector.

---

## Data source

Current version uses:

- **OEC API**
- public **BACI-based annual trade data**
- **HS2 sector classification**

### Current coverage

- **2020–2024**

### Important note

The original project idea aimed at 2020–2025, but the public workflow available here currently provides reliable data only through **2024**.

---

## What this repository contains

### `scripts/`

- `build_project1_trade_inventory.py`  
  Profiles reachable trade-source flows.

- `build_project1_trade_csv.py`  
  Builds the cleaned trade exposure dataset.

- `build_project1_analysis.py`  
  Produces rankings, charts, and summary outputs.

### `data/`

- `project1_trade_exposure.csv`
- `project1_trade_coverage.csv`
- `project1_source_inventory.csv`

### `analysis/`

- sector metrics table
- ranking tables
- executive summary

### `charts/`

- top exposure chart
- top share-growth chart
- top import-value chart
- exposure vs growth scatter plot
- trend chart for major sectors

---

## How to run

Build the trade exposure dataset:

```bash
python3 scripts/build_project1_trade_csv.py
```

Build the analysis outputs:

```bash
python3 scripts/build_project1_analysis.py
```

---

## Key analytical outputs

This project identifies:

- sectors with the **highest China share**
- sectors where China exposure **increased fastest**
- sectors with the **largest absolute import value from China**

---

## Headline findings

### Highest China exposure in 2024

Examples include:

- HS67 — Feather articles, artificial flowers, and related goods
- HS66 — Umbrellas and walking sticks
- HS46 — Straw and esparto manufactures
- HS65 — Headgear
- HS95 — Toys, games, and sports goods

### Largest import values from China in 2024

Examples include:

- HS85 — Electrical machinery and electronics
- HS84 — Machinery and mechanical appliances
- HS87 — Vehicles and related parts
- HS94 — Furniture and lighting-related goods
- HS61 — Knitted clothing accessories

### Fastest increases in China exposure, 2020–2024

Examples include:

- special woven fabrics and tapestries
- vegetable textile fibres and paper yarn
- ships and floating structures
- knitted fabrics
- tools and cutlery

---

## Skills demonstrated

- international trade data analysis
- Python data collection and cleaning
- sector-level exposure measurement
- market intelligence thinking
- business interpretation of trade dependence
- portfolio-style visual communication

---

## Limitations

- current public workflow ends in **2024**
- this version uses an accessible **BACI-based** public source, not yet a final **GUS/CN2** build
- HS2 is intentionally broad for clarity and interpretability

---

## Next steps

- extend to 2025 when available
- move from HS2 to HS4 or CN2
- compare Poland with other EU countries
- add concentration and dependency indicators
- convert results into a one-page executive brief

---

## Interview-ready summary

> I built a sector-level trade exposure project focused on Poland's imports from China. I collected annual HS2 trade data, separated China-origin imports from total Polish imports, calculated China's sector share, and then compared 2020 with 2024 to identify the most exposed sectors, the fastest-growing areas of dependence, and the largest sectors in value terms. Finally, I turned the results into ranking tables, charts, and a short executive summary suitable for portfolio presentation.
