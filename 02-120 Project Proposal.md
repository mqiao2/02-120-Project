Michael Qiao  
02-120 Programming for Scientists  
Oct. 6, 2026

Scientific question: *How has rising atmospheric CO₂ changed surface ocean acidity since preindustrial times, and why are polar waters affected first?*  
My {repository}: [https\://github.com/mqiao2/02-120-Project](https://github.com/mqiao2/02-120-Project)

This project is inspired by Orr et al. (2005) {ocean\_acidification}, which projected that rising atmospheric CO₂ will make polar surface waters corrosive to the aragonite shells of organisms such as pteropods within this century. I will build a model of open-ocean surface chemistry that explains how this occurs and why the poles reach this threshold before the rest of the ocean.

The model combines atmospheric CO₂ measured at the Mauna Loa Observatory {mauna\_loa\_co2} with the long-term average surface temperature {woa23\_decav\_t} and salinity {woa23\_decav\_s} at locations around the world. Because CO₂ is well mixed in the atmosphere away from areas of high output i.e. cities, this single remote station closely represents the air above all oceans. Total alkalinity is 2300 µmol/kg. Assuming surface water is in equilibrium with the atmosphere, the model uses the temperature and salinity-dependent equilibrium constants in {CO2\_guide} to calculate dissolved inorganic carbon, pH, carbonate ion concentration, and aragonite saturation state (Ω). For each latitude band, it will find the CO₂ level at which Ω falls below 1, showing how the varying conditions of the Earth’s oceans affect CO₂ solubility, carbonate equilibrium, and aragonite solubility. This provides a solution of how the temperature and salinity of a water cause it to behave differently.

**Checks:** The model's predicted pH trend at Hawaii should match three decades of measurements from the Hawaii Ocean Time-series {seawater-ph}. The CO₂ levels at which polar waters become undersaturated should be consistent with those reported in Orr et al. (2005). The model applies to open-ocean surface water so coastal zones and rivers/lakes are outside its scope.

