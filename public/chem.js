/* Surface-ocean carbonate chemistry in the browser: the same equations as code/ocean_chem.py,
   so the globe can color every grid cell by aragonite saturation (Ω) for any CO2 without
   asking the server 40,000 times. code/test_chem.py checks that this file and ocean_chem.py
   give the same numbers.

   Constants: Dickson et al. (2007), Chapter 5; aragonite Ksp from Mucci (1983).
   Concentrations are mol/kg-solution; CO2 in the air is a dry-air mole fraction in ppm.
*/

var OceanChem = (function () {
  "use strict";

  var R = 8.314472;                    // J / (K mol)
  var ATM = 101325.0;                  // Pa
  var TOTAL_ALKALINITY = 2300e-6;      // mol/kg, held constant (project assumption)
  var LN10 = Math.LN10;

  function kelvin(t) { return t + 273.15; }

  // ---- air -> water
  function waterVaporPressure(t, s) {                    // atm (Weiss and Price, 1980)
    var T = kelvin(t);
    return Math.exp(24.4543 - 67.4509 * (100 / T) - 4.8489 * Math.log(T / 100) - 0.000544 * s);
  }
  function fugacityCoefficient(t) {                      // at 1 atm (Dickson eqs 25 and 27)
    var T = kelvin(t);
    var B = -1636.75 + 12.0408 * T - 3.27957e-2 * T * T + 3.16528e-5 * T * T * T;
    var delta = 57.7 - 0.118 * T;
    return Math.exp((B + 2 * delta) * 1e-6 * ATM / (R * T));
  }
  function xco2ToFco2(xco2, t, s) {                      // ppm -> atm
    return xco2 * 1e-6 * (1 - waterVaporPressure(t, s)) * fugacityCoefficient(t);
  }

  // ---- equilibrium constants
  function k0(t, s) {                                    // Weiss 1974
    var x = kelvin(t) / 100;
    return Math.exp(93.4517 / x - 60.2409 + 23.3585 * Math.log(x) + s * (0.023517 - 0.023656 * x + 0.0047036 * x * x));
  }
  function k1(t, s) {                                    // Lueker 2000
    var T = kelvin(t);
    return Math.pow(10, -3633.86 / T + 61.2172 - 9.67770 * Math.log(T) + 0.011555 * s - 0.0001152 * s * s);
  }
  function k2(t, s) {                                    // Lueker 2000
    var T = kelvin(t);
    return Math.pow(10, -471.78 / T - 25.9290 + 3.16967 * Math.log(T) + 0.01781 * s - 0.0001122 * s * s);
  }
  function kb(t, s) {                                    // Dickson 1990
    var T = kelvin(t), rs = Math.sqrt(s);
    var num = -8966.90 - 2890.53 * rs - 77.942 * s + 1.728 * s * rs - 0.0996 * s * s;
    return Math.exp(num / T + 148.0248 + 137.1942 * rs + 1.62142 * s +
                    (-24.4344 - 25.085 * rs - 0.2474 * s) * Math.log(T) + 0.053105 * rs * T);
  }
  function kw(t, s) {                                    // Millero 1995
    var T = kelvin(t), rs = Math.sqrt(s);
    return Math.exp(-13847.26 / T + 148.9652 - 23.6521 * Math.log(T) +
                    (118.67 / T - 5.977 + 1.0495 * Math.log(T)) * rs - 0.01615 * s);
  }
  function kspAragonite(t, s) {                          // Mucci 1983
    var T = kelvin(t), rs = Math.sqrt(s);
    return Math.pow(10, -171.945 - 0.077993 * T + 2903.293 / T + 71.595 * Math.log(T) / LN10 +
                        (-0.068393 + 0.0017276 * T + 88.135 / T) * rs - 0.10018 * s + 0.0059415 * s * rs);
  }
  function totalBoron(s) { return 0.000416 * s / 35.0; }           // Uppstrom 1974
  function calcium(s) { return 0.02128 / 40.087 * s / 1.80655; }   // Riley and Tongudai 1967

  // Solve the alkalinity equation for [H+] by bisection on pH (6 to 10, 60 halvings), exactly as
  // ocean_chem.carbonate_system does. alk is total alkalinity in mol/kg (leave it out for the fixed
  // 2300 µmol/kg). Returns { pH, dic, co3, omega }.
  function carbonate(xco2, t, s, alk) {
    var target = alk === undefined ? TOTAL_ALKALINITY : alk;
    var co2 = k0(t, s) * xco2ToFco2(xco2, t, s);
    var K1 = k1(t, s), K2 = k2(t, s), KB = kb(t, s), KW = kw(t, s), BT = totalBoron(s);
    var lo = 6.0, hi = 10.0;
    for (var i = 0; i < 60; i++) {
      var mid = (lo + hi) / 2, h = Math.pow(10, -mid);
      var alk = K1 * co2 / h + 2 * K1 * K2 * co2 / (h * h) + BT * KB / (KB + h) + KW / h - h;
      if (alk > target) hi = mid; else lo = mid;
    }
    var ph = (lo + hi) / 2, hh = Math.pow(10, -ph);
    var hco3 = K1 * co2 / hh, co3 = K1 * K2 * co2 / (hh * hh);
    return { pH: ph, dic: co2 + hco3 + co3, co3: co3, omega: calcium(s) * co3 / kspAragonite(t, s) };
  }

  // Ω for every cell of a grid, given matching temperature and salinity grids (NaN = no data),
  // and optionally an alkalinity grid in µmol/kg (NaN there also means no Ω).
  function omegaGrid(xco2, temperature, salinity, alkalinity) {
    var out = new Float32Array(temperature.length);
    for (var n = 0; n < out.length; n++) {
      var t = temperature[n], s = salinity[n], a = alkalinity ? alkalinity[n] * 1e-6 : TOTAL_ALKALINITY;
      out[n] = (t === t && s === s && a === a) ? carbonate(xco2, t, s, a).omega : NaN;
    }
    return out;
  }

  return { carbonate: carbonate, omegaGrid: omegaGrid, k0: k0, k1: k1, k2: k2, kb: kb, kw: kw,
           kspAragonite: kspAragonite, xco2ToFco2: xco2ToFco2, TOTAL_ALKALINITY: TOTAL_ALKALINITY };
})();
