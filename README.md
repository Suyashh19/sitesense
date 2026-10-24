# Retail Expansion Intelligence Platform

AI platform that tells a retail owner **where to open the next store**. It learns from the owner's existing
stores, predicts sales for every vacant zone in a city, ranks sites, and explains each recommendation.

## Stack
| Layer | Tech |
|---|---|
| Frontend | React + TypeScript (Vite), Leaflet + OpenStreetMap, Recharts |
| Backend | FastAPI (Python) |
| AI / ML | XGBoost, scikit-learn (K-Means, PCA, k-NN, cross-validation), pandas, NumPy, SciPy |
| Database | PostgreSQL + PostGIS (set `DATABASE_URL`); SQLite fallback with zero setup |

## Run (two terminals)
```
run-backend.bat      # FastAPI on http://127.0.0.1:8000   (uses the .venv in this folder)
run-frontend.bat     # React on   http://localhost:5173
```
Open http://localhost:5173. The first load takes a few seconds while the demand model trains.

Optional PostGIS: `set DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/retail` before starting the backend
(needs a Postgres server with the PostGIS extension). Zones are then stored as `geometry(Point,4326)` with a GiST index
and the nearby-stores query uses `ST_DWithin`.

API smoke test: `cd backend` then `..\.venv\Scripts\python.exe test_api.py`.

### Configuration (`.env`)
Nothing is hardcoded: copy `.env.example` to `.env` in the project root (git-ignored). Backend and frontend both read it.
- `VITE_BACKEND_URL` - backend base URL for a separately hosted frontend (e.g. the Render backend). Leave empty locally
  (Vite proxies `/api`) and in Docker (nginx proxies `/api`). On a static host, set it as a build-time env var.
- `GEMINI_API_KEY` / `GROQ_API_KEY` / `ANTHROPIC_API_KEY` - optional; one key turns on AI-written executive briefings.
  Test with `cd backend && python -m app.llm`. Without a key the briefing is built from templates.
- `DATABASE_URL`, `CORS_ORIGINS`, `VITE_MAP_TILE_URL`, `VITE_MAP_ATTRIBUTION` - optional, see `.env.example`.

Parameter defaults and slider ranges are defined once in the backend (`Params` / `SimParams` in `app/main.py`) and
served by `/api/meta`.

### Docker
```
docker compose up --build                     # http://localhost:5173 (SQLite)
docker compose --profile postgis up --build   # with PostGIS; set DATABASE_URL in .env
```

## Tabs
1. **Top 5 Locations** - map (profit heat-map, competition, stores) with factor-wise evidence, strengths, risks, comparison,
   and an executive briefing (optionally rewritten by Gemini/Groq/Claude from the computed facts only).
2. **Zone Clusters** - labelled K-Means archetypes, PCA map, radar, domain fit.
3. **Simulation & What-If** - Monte-Carlo (4,000 futures) and scenario lab; click the map to drop competitor stores
   (each one within 1 km of a site counts as an extra competitor there).
4. **Compare & Ranking** - score breakdown, head-to-head, CSV export.
5. **Model & Assumptions** - validation, feature importance, assumptions, limitations.

## Data & limitations
Zone attributes are **simulated** (real city coordinates, synthetic data); the revenue process is hidden from the model.
Margins, store sizes, fixed costs, capex and ramp-up are stated assumptions. The PostGIS path is implemented but was not
tested against a live PostGIS server (the SQLite path is tested). No paid APIs or keys are required; an LLM key is optional.
