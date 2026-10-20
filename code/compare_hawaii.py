"""Compare modeled surface pH near Hawaii (Station ALOHA, 22.75N 158W)
with Hawaii Ocean Time-series measurements, using yearly averages.

The model uses the WOA23 annual-mean T and S for the cells around ALOHA and
the Mauna Loa yearly-mean CO2. Yearly averaging removes the seasonal CO2
cycle, which the fixed-T, fixed-S model cannot pair with the real seasonal
temperature cycle. Run from the project root: python3 code/compare_hawaii.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))   # shared modules live in code/

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import ocean_chem as oc
from build_grid import load_surface

# Annual-mean T and S: average the four 1-degree cells around 22.75N, 158W
cells = [(22.5, -158.5), (22.5, -157.5), (23.5, -158.5), (23.5, -157.5)]
temp = load_surface(ROOT / "sources/woa23_decav_t00mn01.csv")
sal = load_surface(ROOT / "sources/woa23_decav_s00mn01.csv")
T = np.mean([temp[c] for c in cells])
S = np.mean([sal[c] for c in cells])
print(f"WOA23 surface near ALOHA: T = {T:.2f} C, S = {S:.2f}")

co2 = pd.read_csv(ROOT / "sources/mauna_loa_co2.csv", parse_dates=["date"])
co2_year = co2.groupby(co2["date"].dt.year)["value"].mean()

obs = pd.read_csv(ROOT / "sources/seawater-ph.csv", parse_dates=["Day"])
obs_year = obs.groupby(obs["Day"].dt.year)["Monthly average"].agg(["mean", "count"])
obs_year = obs_year[obs_year["count"] >= 6]    # skip years with sparse sampling
years = obs_year.index.intersection(co2_year.index)
obs_ph = obs_year.loc[years, "mean"].to_numpy()
co2_ppm = co2_year.loc[years].to_numpy()
model_ph = oc.carbonate_system(co2_ppm, T, S)["pH"]

slope_obs = np.polyfit(years, obs_ph, 1)[0]
slope_mod = np.polyfit(years, model_ph, 1)[0]
bias = model_ph - obs_ph
print(f"{len(years)} years, {years.min()}-{years.max()}; "
      f"CO2 {co2_ppm.min():.0f} to {co2_ppm.max():.0f} ppm")
print(f"Trend, observed: {slope_obs * 10:+.4f} pH per decade")
print(f"Trend, model:    {slope_mod * 10:+.4f} pH per decade")
print(f"Mean offset (model - obs): {bias.mean():+.4f}  (std {bias.std():.4f})")
print(f"RMS error: {np.sqrt((bias ** 2).mean()):.4f}")

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(years, obs_ph, "o", alpha=0.7, label="HOT measured (yearly mean)")
ax.plot(years, model_ph, "-", color="C3", label="model (yearly mean CO$_2$)")
ax.set_ylabel("surface pH"); ax.set_title("Hawaii: model vs. measured pH")
ax.legend(); fig.tight_layout()
(ROOT / "results").mkdir(exist_ok=True)
fig.savefig(ROOT / "results/hawaii_comparison.png", dpi=150)
