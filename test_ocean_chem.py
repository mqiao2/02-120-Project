"""Tests for ocean_chem.py. Run: python3 test_ocean_chem.py"""

import numpy as np
import ocean_chem as oc


def close(a, b, tol, name):
    assert abs(a - b) <= tol, f"{name}: got {a}, expected {b} (tol {tol})"
    print(f"ok  {name}: {a:.5g}")


# 1. Constants vs. worked values in Dickson ch. 5 (25 C, S = 35)
close(np.log(oc.k0(25, 35)), -3.5617, 1e-3, "ln K0")
close(np.log10(oc.k1(25, 35)), -5.8472, 1e-3, "log10 K1")
close(np.log10(oc.k2(25, 35)), -8.9660, 1e-3, "log10 K2")
close(np.log(oc.kb(25, 35)), -19.7964, 1e-3, "ln KB")
close(np.log(oc.kw(25, 35)), -30.434, 1e-3, "ln KW")
close(oc.water_vapor_pressure(25, 35) * 101.325, 3.1106, 0.02, "H2O vapor kPa")
close(oc.fugacity_coefficient(25), 0.9964, 0.0005, "CO2 fugacity coeff")

# 2. Aragonite Ksp at 25 C, S = 35: literature ~ 6.7e-7 (mol/kg)^2
close(oc.ksp_aragonite(25, 35) / 1e-7, 6.65, 0.3, "Ksp aragonite (1e-7)")

# 3. Solver reproduces the alkalinity it was given
r = oc.carbonate_system(400, 25, 35)
h = 10.0 ** -r["pH"]
co2 = oc.k0(25, 35) * oc.xco2_to_fco2(400, 25, 35)
alk = (oc.k1(25, 35) * co2 / h + 2 * r["co3"]
       + oc.total_boron(35) * oc.kb(25, 35) / (oc.kb(25, 35) + h)
       + oc.kw(25, 35) / h - h)
close(alk * 1e6, 2300, 1e-3, "alkalinity round trip (umol/kg)")

# 4. Sanity: modern warm surface water
close(r["pH"], 8.05, 0.1, "pH warm water, 400 ppm")
assert 3.0 < r["omega"] < 5.0, r["omega"]
print(f"ok  omega warm water, 400 ppm: {float(r['omega']):.3f}")

# 5. Physics directions: more CO2 -> lower pH, lower omega, higher DIC
lo_, hi_ = oc.carbonate_system(280, 15, 35), oc.carbonate_system(800, 15, 35)
assert hi_["pH"] < lo_["pH"] and hi_["omega"] < lo_["omega"] and hi_["dic"] > lo_["dic"]
print("ok  more CO2 -> lower pH, lower omega, higher DIC")

# 6. Cold water has lower omega than warm water at the same CO2
cold, warm = oc.carbonate_system(400, 0, 34), oc.carbonate_system(400, 28, 35)
assert cold["omega"] < warm["omega"]
print(f"ok  omega cold {float(cold['omega']):.2f} < warm {float(warm['omega']):.2f}")

# 7. Arrays work
a = oc.carbonate_system(np.array([280, 400, 800]), 10, 35)
assert a["pH"].shape == (3,) and np.all(np.diff(a["pH"]) < 0)
print("ok  array input")

print("\nAll tests passed.")
