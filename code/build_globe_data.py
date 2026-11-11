"""Build public/data/surface_1deg.json, the temperature and salinity grids the globe draws.

Reads the two World Ocean Atlas 2023 one-degree annual climatology files (the average of
all measurements from 1955 to 2022; download them from
https://www.ncei.noaa.gov/access/world-ocean-atlas-2023/ as "all decades, 1.00 degree,
annual, statistical mean" CSV files for temperature and salinity). Each row holds one
grid cell and its value at a series of depths. The globe shows the surface, which is the
0 m value, or the 5 m or 10 m value in the few cells (mostly in the Arctic) where the 0 m
value is blank, so the data are "the top 10 m".

Both fields go on one grid: 180 rows from the south (latitude -89.5) to the north (89.5),
360 columns from the west (longitude -179.5) to the east (179.5), written row by row.
Values are stored as whole numbers, value / 0.01, and as null where there is no data
(land, or ocean the atlas does not cover). The result is a few hundred kilobytes, small
enough to commit and to serve from the website.

Run from the project root (needs pandas: pip install -r code/requirements/requirements-dev.txt):
    python3 code/build_globe_data.py
    python3 code/build_globe_data.py --temperature PATH --salinity PATH
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
NLAT, NLON, SCALE = 180, 360, 0.01


def load_top_10m(path):
    """Read a World Ocean Atlas csv: for each (lat, lon) the 0 m value, else the 5 m, else the 10 m."""
    df = pd.read_csv(path, comment="#", header=None, usecols=[0, 1, 2, 3, 4],
                     names=["lat", "lon", "d0", "d5", "d10"])
    value = df[["d0", "d5", "d10"]].bfill(axis=1)["d0"]    # first value that is not blank, left to right
    value.index = pd.MultiIndex.from_arrays([df["lat"], df["lon"]], names=["lat", "lon"])
    return value, int(df["d0"].notna().sum())


def to_grid(surface):
    """Turn a (lat, lon)-indexed series into a 180 x 360 array, NaN where there is no data."""
    lat = surface.index.get_level_values("lat").to_numpy()
    lon = surface.index.get_level_values("lon").to_numpy()
    assert np.allclose(lat % 1, 0.5) and np.allclose(lon % 1, 0.5), "expected 1-degree cell centers"
    rows = np.floor(lat + 90).astype(int)     # the cell centered on -89.5 covers -90 to -89
    cols = np.floor(lon + 180).astype(int)
    assert rows.min() >= 0 and rows.max() < NLAT and cols.min() >= 0 and cols.max() < NLON
    grid = np.full((NLAT, NLON), np.nan)
    ok = surface.notna().to_numpy()
    grid[rows[ok], cols[ok]] = surface.to_numpy()[ok]
    return grid


def encode(grid):
    """Flatten row by row into whole numbers (value / SCALE), None for no data."""
    return [None if np.isnan(v) else int(round(v / SCALE)) for v in grid.ravel()]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--temperature", default=ROOT / "sources/woa23_decav_t00mn01.csv", type=Path)
    parser.add_argument("--salinity", default=ROOT / "sources/woa23_decav_s00mn01.csv", type=Path)
    parser.add_argument("--out", default=ROOT / "public/data/surface_1deg.json", type=Path)
    args = parser.parse_args()

    grids = {}
    for name, path in (("temperature", args.temperature), ("salinity", args.salinity)):
        surface, at_surface = load_top_10m(path)
        if len(surface) < 30000:
            sys.exit(f"{path} has only {len(surface)} rows: it looks like an empty stub, "
                     f"not the real World Ocean Atlas file. Pass the real one with --{name}.")
        grids[name] = to_grid(surface)
        valid = grids[name][~np.isnan(grids[name])]
        print(f"{name}: {valid.size} cells with data ({valid.size - at_surface} of them from 5 m or 10 m), "
              f"range {valid.min():.2f} to {valid.max():.2f}")

    data = {
        "source": ("NOAA World Ocean Atlas 2023, one-degree annual climatology "
                   "(average of all measurements, 1955-2022), surface: the 0 m value, or the 5 m or 10 m value where 0 m is blank"),
        "grid": {"rows": NLAT, "cols": NLON, "first_lat": -89.5, "first_lon": -179.5, "step": 1,
                 "order": "south to north, then west to east"},
        "scale": SCALE,
        "temperature_c": encode(grids["temperature"]),
        "salinity_psu": encode(grids["salinity"]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1000:.0f} kB)")


if __name__ == "__main__":
    main()
