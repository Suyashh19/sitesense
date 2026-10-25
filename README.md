# SiteSense – Retail Expansion Intelligence Platform

Tells a retail owner **where to open the next store** in Pune. It scores every ~10-hectare hexagon of the city for the chosen business,
learns what proven locations look like, simulates customers to estimate profit as a *range*, and explains each recommendation in plain language.
Built from the SiteSense PRD (Triwizathon, Problem Statement 1).

Five categories: Sports & Gym Equipment · Food & Restaurants · Fashion & Clothing · Pharmacy & Healthcare · Electronics & Mobile.

## Run
```
run-backend.bat      # first run builds the data + models (internet, several minutes), then serves http://127.0.0.1:8000
run-frontend.bat     # React app on http://localhost:5173
```
Or build the data yourself: `cd backend && python -m app.pipeline.build` (add `--refresh` to re-download OpenStreetMap data).
The app also has a **Data & trust** page with a *Build* button, live log and the lineage of every number.
Docker: `docker compose up --build` (PostGIS optional: `--profile postgis`).

## What is real and what is estimated
| Real data | Modelled / estimated (always labelled in the UI) |
|---|---|
| Shops, offices, colleges, hospitals, bus/rail stops, roads – OpenStreetMap via Overpass (ODbL) | Population per zone – WorldPop 1 km raster (CC BY 4.0), redistributed by OSM activity |
| Growth trend – ohsome API history of OSM | Property prices of ~35 localities (`config/city_pune.yaml`), commercial rent (CatBoost M-1) |
| | Margins, fixed costs, store sizes, spend per person (`config/categories.yaml`) |

There is **no real sales data**. "Proven location" means *an established chain already trades there* (weak label); profit comes from a
Huff gravity-model simulation with Monte Carlo over uncertain inputs, so every figure is a range.

## How it works (backend/app)
| Stage | Module | PRD |
|---|---|---|
| Ingest OSM + WorldPop | `pipeline/osm.py`, `population.py` | DS-01..04 |
| H3 grid (res 9), ring features, 10 factor groups | `pipeline/grid.py`, `features.py` | FG1–FG10 |
| Rent regressor, leave-locality-out validated | `engine/rent.py` | M-1 |
| Business Opportunity Index from Retail DNA weights | `engine/scoring.py` | F-09, F-07 |
| PU viability classifier + LambdaRank ranker, spatial-block CV, leakage mask | `engine/learn.py` | M-2, M-3 |
| Gravity economics, Monte Carlo, cannibalisation | `engine/gravity.py` | M-4, M-8 |
| SHAP grouped by factor, risk rules, confidence, contrast | `engine/learn.py`, `service.py` | M-10, F-11 |
| Zone archetypes (K-means on PCA) | `engine/learn.py` | M-6 |
| Multi-store plan (CP-SAT) | `engine/optimise.py` | M-9, F-14 |
| Plain-English requests → whitelisted tool call | `engine/intent.py` | M-11 |
| API | `main.py` | |

Nothing about a city, category, tag or weight is hardcoded in code: `backend/config/city_pune.yaml` and `categories.yaml` define them
(add a category or city = add YAML). Weights must sum to 100 and are validated at load.

## Configuration (`.env`, optional)
`DATABASE_URL` (PostGIS or SQLite default), `CORS_ORIGINS`, `VITE_BACKEND_URL` (separately hosted frontend), `VITE_MAP_TILE_URL`,
`GEMINI_API_KEY` / `GROQ_API_KEY` / `ANTHROPIC_API_KEY` (optional: an LLM may only *rephrase* a computed briefing).

## Limitations
OSM completeness varies (shown as a coverage indicator and lowers confidence); population is a modelled 1 km grid; locality prices and rents are
approximate estimates; footfall is inferred from POIs; online demand, zoning and lease availability are not modelled; models show correlation, not causation.
