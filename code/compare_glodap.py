"""Check the model against GLODAP's measured surface chemistry, and test its two assumptions.

GLODAPv2.2016b (Lauvset et al., 2016) maps measured total alkalinity (TA), dissolved inorganic
carbon (DIC) and the aragonite saturation state (Ω) onto the same 1-degree grid as the globe.
Its DIC and Ω are adjusted to the year 2002, so the model is run at 2002's Mauna Loa CO2,
with World Ocean Atlas temperature and salinity, as on the website.

  1. How far is the model's Ω from GLODAP's Ω, with fixed (2300) or GLODAP alkalinity?
  2. Is the surface water in equilibrium with the air? From GLODAP's TA and DIC, and GLODAP's own
     temperature and salinity (from the same water samples), work out the water's CO2 fugacity
     and divide it by the air's. 1 means equilibrium; below 1, the water holds less CO2 than the
     air would put there, so its real Ω is higher than the model's. Polar samples come mostly from
     summer cruises, so these are summer-weighted.

Cells in build_alkalinity_data.MASKS (enclosed seas the mapping filled in) are left out, as on the website.

The page's notes quote these numbers. Run from the project root (needs h5py):
    python3 code/compare_glodap.py --glodap-dir PATH/TO/GLODAPv2.2016b_MappedClimatologies
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ocean_chem as oc  # noqa: E402
from build_alkalinity_data import apply_masks, read_surface  # noqa: E402

BANDS = {"Arctic (north of 66°N)": (66, 90), "North, 30-66°N": (30, 66), "Tropics, 30°S-30°N": (-30, 30),
         "South, 30-60°S": (-60, -30), "Southern Ocean (south of 60°S)": (-90, -60)}


def load_woa():
    data = json.loads((ROOT / "public/data/surface_1deg.json").read_text(encoding="utf-8"))
    def grid(key):
        return np.array([np.nan if v is None else v * data["scale"] for v in data[key]]).reshape(180, 360)
    return grid("temperature_c"), grid("salinity_psu")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--glodap-dir", required=True, type=Path)
    args = parser.parse_args()
    path = lambda name: args.glodap_dir / f"GLODAPv2.2016b.{name}.nc"   # noqa: E731
    ta, dic, omega = apply_masks(read_surface(path("TAlk"))), read_surface(path("TCO2"), "TCO2"), read_surface(path("OmegaA"), "OmegaA")
    gt, gs = read_surface(path("temperature"), "temperature"), read_surface(path("salinity"), "salinity")
    T, S = load_woa()
    co2 = json.loads((ROOT / "public/data/co2_yearly.json").read_text(encoding="utf-8"))
    xco2 = co2["ppm"][co2["years"].index(2002)]
    lat = np.repeat(np.arange(-89.5, 90)[:, None], 360, axis=1)

    ocean = ~np.isnan(T) & ~np.isnan(S) & (S >= 20)          # the cells the globe gives an Ω
    print(f"Ocean cells: {ocean.sum()}; with GLODAP alkalinity: {(ocean & ~np.isnan(ta)).sum()}")
    m = ocean & ~np.isnan(ta) & ~np.isnan(omega) & ~np.isnan(dic) & ~np.isnan(gt) & ~np.isnan(gs)
    fixed = oc.carbonate_system(xco2, T[m], S[m])["omega"]
    local = oc.carbonate_system(xco2, T[m], S[m], alk=ta[m] * 1e-6)["omega"]
    ratio = oc.fco2_from_alk_dic(ta[m] * 1e-6, dic[m] * 1e-6, gt[m], gs[m]) / oc.xco2_to_fco2(xco2, gt[m], gs[m])

    print(f"\nAt {xco2} ppm (2002), {m.sum()} cells. Model Ω minus GLODAP Ω, as RMS (bias):")
    print(f"{'':32} {'fixed 2300':>15} {'GLODAP TA':>15}   water CO2 / air CO2 (median, 5-95%)")
    rows = [("All cells", np.ones(m.sum(), bool))] + [(n, (lat[m] >= a) & (lat[m] < b)) for n, (a, b) in BANDS.items()]
    for name, k in rows:
        cols = []
        for x in (fixed, local):
            d = x[k] - omega[m][k]
            cols.append(f"{np.sqrt(np.mean(d**2)):.2f} ({np.mean(d):+.2f})")
        r = ratio[k]
        print(f"{name:32} {cols[0]:>15} {cols[1]:>15}   {np.median(r):.2f} ({np.percentile(r, 5):.2f}-{np.percentile(r, 95):.2f})")


if __name__ == "__main__":
    main()
