"""Build public/data/alkalinity_1deg.json, the surface total alkalinity grid the globe draws.

Reads GLODAPv2.2016b.TAlk.nc from the GLODAPv2.2016b mapped climatology (Lauvset et al., 2016,
CC BY 4.0; download "GLODAPv2.2016b_MappedClimatologies.tar" from https://glodap.info and unpack
it). It holds total alkalinity mapped onto a 1-degree grid from bottle measurements made in
1972-2013, at 33 depths. The globe uses the top one, 0 m.

The mapped product leaves out some seas (Hudson Bay, most of the Gulf of Mexico, the Red Sea, and
parts of the Caribbean, the Beaufort Sea and the water around the North Pole). It also fills in
three enclosed seas that were hardly measured with values carried over from the open sea next door:
the Black Sea and the Persian Gulf (1 and 0 cells with measurements) and the Baltic (2), whose real
alkalinity is far from the mapped ~2300-2600 (the Black Sea's is about 3200, the brackish Baltic's
much lower). MASKS removes those three. All these cells stay empty (null): the globe shows them as
"no alkalinity data" rather than guessing a value.

The grid matches public/data/surface_1deg.json: 180 rows from the south (latitude -89.5) to
the north (89.5), 360 columns from the west (longitude -179.5) to the east (179.5), written row
by row, in whole µmol/kg. GLODAP's longitudes run 20.5 to 379.5, so the columns are reordered.

Run from the project root (needs h5py: pip install -r code/requirements/requirements-dev.txt):
    python3 code/build_alkalinity_data.py --talk PATH/TO/GLODAPv2.2016b.TAlk.nc
"""

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
NLAT, NLON = 180, 360
FILL = -999.0
# Enclosed seas the mapping filled in without measurements: (lowest lat, highest lat), (west lon, east lon) of cell centers.
MASKS = {
    "Black Sea": ((41.5, 47.5), (27.5, 41.5)),
    "Persian Gulf": ((23.5, 30.5), (47.5, 56.5)),
    "Baltic Sea (east of the Danish straits)": ((53.5, 65.5), (13.5, 30.5)),
}


def read_surface(path, name="TAlk"):
    """The 0 m layer of a GLODAP mapped field as a 180 x 360 array (south to north, -179.5 to 179.5), NaN where empty."""
    with h5py.File(path, "r") as f:
        depth = f["Depth"][:]
        assert depth[0] == 0, f"expected the first depth to be 0 m, got {depth[0]}"
        lat, lon = f["lat"][:], f["lon"][:]
        values = f[name][0].astype(float)
    assert values.shape == (NLAT, NLON), values.shape
    assert np.allclose(lat, np.arange(-89.5, 90)), "expected latitudes -89.5 to 89.5"
    values[values == FILL] = np.nan
    order = np.argsort(((lon + 180) % 360) - 180)     # 20.5 ... 379.5 -> -179.5 ... 179.5
    assert np.allclose(((lon[order] + 180) % 360) - 180, np.arange(-179.5, 180))
    return values[:, order]


def apply_masks(grid):
    """A copy of a 180 x 360 grid with the MASKS seas set to NaN."""
    out = grid.copy()
    lat, lon = np.arange(-89.5, 90), np.arange(-179.5, 180)
    for (lat_lo, lat_hi), (lon_lo, lon_hi) in MASKS.values():
        out[np.ix_((lat >= lat_lo) & (lat <= lat_hi), (lon >= lon_lo) & (lon <= lon_hi))] = np.nan
    return out


def encode(grid):
    """Flatten row by row into whole numbers, None for no data."""
    return [None if np.isnan(v) else int(round(v)) for v in grid.ravel()]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--talk", required=True, type=Path, help="GLODAPv2.2016b.TAlk.nc")
    parser.add_argument("--out", default=ROOT / "public/data/alkalinity_1deg.json", type=Path)
    args = parser.parse_args()

    raw = read_surface(args.talk)
    grid = apply_masks(raw)
    print(f"masked {int((~np.isnan(raw)).sum() - (~np.isnan(grid)).sum())} cells in: {', '.join(MASKS)}")
    valid = grid[~np.isnan(grid)]
    print(f"alkalinity: {valid.size} cells with data, range {valid.min():.0f} to {valid.max():.0f} µmol/kg, "
          f"median {np.median(valid):.0f}")

    data = {
        "source": ("GLODAPv2.2016b mapped climatology (Lauvset et al., 2016, Earth Syst. Sci. Data 8, 325-340, "
                   "doi:10.5194/essd-8-325-2016; CC BY 4.0): total alkalinity at 0 m, mapped from measurements made in 1972-2013; "
                   "the Black Sea, Persian Gulf and Baltic Sea are left out (filled in by the mapping, not measured)"),
        "grid": {"rows": NLAT, "cols": NLON, "first_lat": -89.5, "first_lon": -179.5, "step": 1,
                 "order": "south to north, then west to east"},
        "unit": "µmol/kg",
        "alkalinity_umol_kg": encode(grid),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1000:.0f} kB)")


if __name__ == "__main__":
    main()
