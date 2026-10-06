# Who I am

This is the semester project for Programming for Scientists, an application-based introductory course on using Python to solve scientific problems. I am a first-year college undergraduate with minimal programming experience, and this course accounts for the lack of experience by making the project based on interaction with Claude. That is, Claude will be doing most of the programming while I manage. 

# How I learn

I'm very bad at reading, so I prefer concise dialogue and feedback. I am especially not afraid of criticism, especially as this is my first major CS project. I can also get very carried away with details and forgot the big picture, so make sure to stop occasionally and ask if I truly understand what's being discussed.


# What I am building

A website, published online, that models ocean acidification and lets users
explore it with their own inputs and scenarios. The question: How has rising atmospheric CO₂ changed surface ocean chemistry since preindustrial times, and why do polar waters become corrosive to shell-building organisms first? (Inspired by Orr et al., 2005.)

For each ocean location (1° grid cell or latitude band), the model combines:

- Atmospheric CO2 from the Mauna Loa Observatory record. Convert the dry-air mole fraction to partial pressure.
- Surface temperature and salinity from World Ocean Atlas 2023 annual
  climatologies (long-term averages, 1955–2022).
- Total alkalinity, held constant at 2300 µmol/kg.

Assuming the surface ocean is in equilibrium with the atmosphere, the model uses
the temperature- and salinity-dependent equilibrium constants in the Dickson
guide to solve the alkalinity equation for [H+], then calculates pH, dissolved inorganic carbon (DIC) concentrations, and aragonite saturation state (Ω).

Temperature and salinity are long-term averages for each location. They set the
equilibrium constants, so they determine where acidification is most severe.
Change over time comes from rising CO₂. Ocean warming over these decades is
small compared with the 30°C difference between tropics and poles, so it is
left out of the core model.
