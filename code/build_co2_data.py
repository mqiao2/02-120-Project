"""Build public/data/co2_yearly.json, the yearly CO2 averages the CO2 graph draws.

Reads the Mauna Loa daily record (sources/mauna_loa_co2.csv, columns date and value in
ppm). Each year's value is the average of its twelve monthly averages, so a month with
many measurements does not count more than one with few. Years without all twelve
months (1958, which starts in March; 1964, which has a four-month gap; and the current,
unfinished year) are left out, because the seasonal swing of about 6 ppm would bias them.

Run from the project root (needs pandas: pip install -r code/requirements/requirements-dev.txt):
    python3 code/build_co2_data.py
    python3 code/build_co2_data.py --csv PATH
"""

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def yearly_means(csv_path):
    """{year: mean of the 12 monthly means} for every year that has all 12 months."""
    daily = pd.read_csv(csv_path, parse_dates=["date"])
    monthly = daily.groupby([daily["date"].dt.year, daily["date"].dt.month])["value"].mean()
    months = monthly.groupby(level=0).size()
    full = months[months == 12].index
    return monthly.groupby(level=0).mean().loc[full].round(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    default = next((p for p in (ROOT / "sources/mauna_loa_co2.csv", ROOT / "sources/mauna_loa_CO2.csv") if p.exists()),
                   ROOT / "sources/mauna_loa_co2.csv")
    parser.add_argument("--csv", default=default, type=Path)
    parser.add_argument("--out", default=ROOT / "public/data/co2_yearly.json", type=Path)
    args = parser.parse_args()
    means = yearly_means(args.csv)
    data = {
        "source": "NOAA Mauna Loa Observatory, daily CO2; yearly average of the 12 monthly averages, full years only",
        "unit": "ppm",
        "years": [int(y) for y in means.index],
        "ppm": [float(v) for v in means.values],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(means)} years, {means.index[0]}-{means.index[-1]}, {means.iloc[0]} to {means.iloc[-1]} ppm; wrote {args.out}")


if __name__ == "__main__":
    main()
