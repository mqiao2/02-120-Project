"""Surface-ocean carbonate chemistry.

Given atmospheric CO2 (ppm), temperature (C), salinity, and a fixed total
alkalinity, solve for pH, DIC, carbonate ion and aragonite saturation (omega).

Constants K0, K1, K2, KB, KW come from Dickson et al. (2007), Chapter 5,
section 7. Aragonite Ksp is from Mucci (1983) (not in the Dickson guide).
All functions accept numpy arrays. Concentrations are mol/kg-solution.
"""

import numpy as np

R = 8.314472          # J / (K mol)  (Dickson ch. 5, sec. 1)
ATM = 101325.0        # Pa
TOTAL_ALKALINITY = 2300e-6   # mol/kg, held constant (project assumption)


def kelvin(t_c):
    return np.asarray(t_c, dtype=float) + 273.15


# ---------------------------------------------------------------- air -> water

def water_vapor_pressure(t_c, s):
    """Seawater vapor pressure in atm (Weiss and Price, 1980)."""
    T = kelvin(t_c)
    return np.exp(24.4543 - 67.4509 * (100 / T) - 4.8489 * np.log(T / 100)
                  - 0.000544 * s)


def fugacity_coefficient(t_c, p_atm=1.0):
    """CO2 fugacity coefficient in air (Dickson ch. 5, eqs 25 and 27)."""
    T = kelvin(t_c)
    B = -1636.75 + 12.0408 * T - 3.27957e-2 * T**2 + 3.16528e-5 * T**3   # cm3/mol
    delta = 57.7 - 0.118 * T                                              # cm3/mol
    return np.exp((B + 2 * delta) * 1e-6 * p_atm * ATM / (R * T))


def xco2_to_fco2(xco2_ppm, t_c, s, p_atm=1.0):
    """Dry-air mole fraction (ppm) -> CO2 fugacity (atm) over seawater."""
    pco2 = xco2_ppm * 1e-6 * (p_atm - water_vapor_pressure(t_c, s))
    return pco2 * fugacity_coefficient(t_c, p_atm)


# ------------------------------------------------------ equilibrium constants

def k0(t_c, s):
    """CO2 solubility, mol/(kg atm) (Weiss 1974; Dickson eq 30)."""
    T = kelvin(t_c)
    x = T / 100
    ln_k0 = (93.4517 / x - 60.2409 + 23.3585 * np.log(x)
             + s * (0.023517 - 0.023656 * x + 0.0047036 * x**2))
    return np.exp(ln_k0)


def k1(t_c, s):
    """First dissociation of carbonic acid (Lueker 2000; Dickson eq 40)."""
    T = kelvin(t_c)
    return 10 ** (-3633.86 / T + 61.2172 - 9.67770 * np.log(T)
                  + 0.011555 * s - 0.0001152 * s**2)


def k2(t_c, s):
    """Second dissociation of carbonic acid (Lueker 2000; Dickson eq 43)."""
    T = kelvin(t_c)
    return 10 ** (-471.78 / T - 25.9290 + 3.16967 * np.log(T)
                  + 0.01781 * s - 0.0001122 * s**2)


def kb(t_c, s):
    """Boric acid dissociation (Dickson 1990; eq 37)."""
    T = kelvin(t_c)
    rs = np.sqrt(s)
    num = (-8966.90 - 2890.53 * rs - 77.942 * s + 1.728 * s * rs - 0.0996 * s**2)
    ln_kb = (num / T + 148.0248 + 137.1942 * rs + 1.62142 * s
             + (-24.4344 - 25.085 * rs - 0.2474 * s) * np.log(T)
             + 0.053105 * rs * T)
    return np.exp(ln_kb)


def kw(t_c, s):
    """Water dissociation (Millero 1995; eq 62)."""
    T = kelvin(t_c)
    rs = np.sqrt(s)
    ln_kw = (-13847.26 / T + 148.9652 - 23.6521 * np.log(T)
             + (118.67 / T - 5.977 + 1.0495 * np.log(T)) * rs - 0.01615 * s)
    return np.exp(ln_kw)


def ksp_aragonite(t_c, s):
    """Aragonite solubility product, (mol/kg)^2 (Mucci 1983)."""
    T = kelvin(t_c)
    rs = np.sqrt(s)
    log10_ksp = (-171.945 - 0.077993 * T + 2903.293 / T + 71.595 * np.log10(T)
                 + (-0.068393 + 0.0017276 * T + 88.135 / T) * rs
                 - 0.10018 * s + 0.0059415 * s * rs)
    return 10 ** log10_ksp


def total_boron(s):
    """Total boric acid, mol/kg (Uppstrom 1974)."""
    return 0.000416 * s / 35.0


def calcium(s):
    """Calcium ion, mol/kg (conservative with salinity)."""
    return 0.01028 * s / 35.0


# --------------------------------------------------------------------- solver

def carbonate_system(xco2_ppm, t_c, s, alk=TOTAL_ALKALINITY):
    """Solve the alkalinity equation for [H+] (total scale) by bisection.

    Alkalinity ~ [HCO3-] + 2[CO3--] + [B(OH)4-] + [OH-] - [H+]
    (sulfate, fluoride and phosphate terms are negligible at seawater pH).

    Returns dict with pH, dic (mol/kg), co3 (mol/kg), omega.
    """
    xco2_ppm, t_c, s = np.broadcast_arrays(
        np.asarray(xco2_ppm, float), np.asarray(t_c, float), np.asarray(s, float))
    co2 = k0(t_c, s) * xco2_to_fco2(xco2_ppm, t_c, s)
    K1, K2, KB, KW = k1(t_c, s), k2(t_c, s), kb(t_c, s), kw(t_c, s)
    BT = total_boron(s)

    def alk_of(h):
        hco3 = K1 * co2 / h
        co3 = K1 * K2 * co2 / h**2
        borate = BT * KB / (KB + h)
        return hco3 + 2 * co3 + borate + KW / h - h

    # alk_of rises with pH, so bisect on pH (6 to 10).
    lo = np.full(co2.shape, 6.0)    # low pH  -> alk_of too low
    hi = np.full(co2.shape, 10.0)   # high pH -> alk_of too high
    for _ in range(60):
        mid = (lo + hi) / 2
        too_high = alk_of(10.0 ** -mid) > alk
        hi = np.where(too_high, mid, hi)
        lo = np.where(too_high, lo, mid)
    ph = (lo + hi) / 2
    h = 10.0 ** -ph
    hco3 = K1 * co2 / h
    co3 = K1 * K2 * co2 / h**2
    return {
        "pH": ph,
        "dic": co2 + hco3 + co3,
        "co3": co3,
        "omega": calcium(s) * co3 / ksp_aragonite(t_c, s),
    }
