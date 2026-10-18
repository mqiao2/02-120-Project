"""Precompute pH, DIC and aragonite omega on the WOA23 1-degree grid for
CO2 = 250..1000 ppm in steps of 5. Saves output/grid_results.npz.

Run: python3 build_grid.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

import ocean_chem as oc

ROOT = Path(__file__).parent
CO2_LEVELS = np.arange(250, 1001, 5)


def load_surface(path):
    """Surface (0 m) values from a WOA23 csv, indexed by (lat, lon)."""
    df = pd.read_csv(path, comment="#", header=None, usecols=[0, 1, 2],
                     names=["lat", "lon", "value"])
    return df.set_index(["lat", "lon"])["value"]


def main():
    temp = load_surface(ROOT / "sources/woa23_decav_t00mn01.csv")
    sal = load_surface(ROOT / "sources/woa23_decav_s00mn01.csv")
    both = pd.concat({"t": temp, "s": sal}, axis=1, join="inner").dropna()
    lat = both.index.get_level_values("lat").to_numpy()
    lon = both.index.get_level_values("lon").to_numpy()
    t, s = both["t"].to_numpy(), both["s"].to_numpy()
    print(f"{len(both)} ocean cells with both temperature and salinity")

    n = len(CO2_LEVELS)
    ph = np.empty((n, len(t)), dtype=np.float32)
    omega = np.empty_like(ph)
    dic = np.empty_like(ph)
    for i, co2 in enumerate(CO2_LEVELS):
        r = oc.carbonate_system(co2, t, s)
        ph[i], omega[i], dic[i] = r["pH"], r["omega"], r["dic"] * 1e6  # umol/kg

    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    np.savez_compressed(out / "grid_results.npz", co2=CO2_LEVELS, lat=lat,
                        lon=lon, temp=t, sal=s, pH=ph, omega=omega, dic=dic)
    print(f"saved {out / 'grid_results.npz'}")


if __name__ == "__main__":
    main()
