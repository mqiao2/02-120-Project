"""Build public/data/ssp_co2.json, the future CO2 pathways the CO2 graph can show.

Reads the Our World in Data download of the Shared Socioeconomic Pathways (SSP) baseline
CO2 concentrations (Riahi et al. 2017), in
atmospheric-concentrations-of-carbon-dioxide.filtered/atmospheric-concentrations-of-carbon-dioxide.csv.
Each row is one pathway ("SSP1 - Baseline" ... "SSP5 - Baseline"), one year (2005, 2010,
2020, 2030, ... 2100) and a global CO2 concentration in ppm, plus the pathway's story name.

"Baseline" means no new climate policy, so even SSP1 keeps rising to about 610 ppm by 2100.

Run from the project root (standard library only):
    python3 code/build_ssp_data.py
"""

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "atmospheric-concentrations-of-carbon-dioxide.filtered"
VALUE = "CO2 concentration - Region: global"
STORY = VALUE + " (Annotations)"


def read_pathways(csv_path):
    """[{id, name, story, years, ppm}] for SSP1..SSP5, each sorted by year."""
    rows = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            match = re.fullmatch(r"(SSP[1-5]) - Baseline", row["Entity"])
            if not match:
                raise ValueError(f"unexpected pathway {row['Entity']!r}")
            p = rows.setdefault(match.group(1), {"story": row[STORY], "points": {}})
            year = int(row["Year"])
            if year in p["points"]:
                raise ValueError(f"{match.group(1)} has {year} twice")
            p["points"][year] = round(float(row[VALUE]), 2)
    if sorted(rows) != ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"]:
        raise ValueError(f"expected SSP1-SSP5, found {sorted(rows)}")
    pathways = []
    for pid in sorted(rows):
        story = rows[pid]["story"]                         # e.g. "Sustainability - Taking the Green Road"
        name, _, tagline = story.partition(" - ")
        years = sorted(rows[pid]["points"])
        pathways.append({"id": pid, "name": name, "tagline": tagline, "years": years,
                         "ppm": [rows[pid]["points"][y] for y in years]})
    return pathways


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--csv", default=SOURCE_DIR / "atmospheric-concentrations-of-carbon-dioxide.csv", type=Path)
    parser.add_argument("--out", default=ROOT / "public/data/ssp_co2.json", type=Path)
    args = parser.parse_args()
    pathways = read_pathways(args.csv)
    data = {
        "source": "Riahi et al. (2017), Shared Socioeconomic Pathways, baseline (no new climate policy) scenarios; "
                  "global CO2 concentration, processed by Our World in Data (CC BY 4.0)",
        "unit": "ppm",
        "pathways": pathways,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    for p in pathways:
        print(f"{p['id']} {p['name']}: {p['years'][0]}-{p['years'][-1]}, {p['ppm'][0]} to {p['ppm'][-1]} ppm")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
