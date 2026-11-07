# Fondinsyn — Quarterly Swedish Fund-Holdings Explorer

**A Swedish-language historical quarterly fund-holdings explorer built on public data from Finansinspektionen (FI).**

Fondinsyn presents reported fund holdings as historical quarter-end snapshots for informational and analysis purposes.

## Architecture

- **Application:** Python, FastAPI, Jinja2, HTMX
- **Data store:** PostgreSQL
- **Deployment:** Docker
- **ETL:** FI quarterly XML archives are fetched, parsed, transformed, and loaded to PostgreSQL. Analytics materialized views are refreshed after the load.

```text
FI quarterly XML -> ETL -> PostgreSQL -> FastAPI / HTMX Fondinsyn
                                  \-> optional Superset analytics
```

Superset is an optional analyst-facing layer. The Fondinsyn application remains the primary interface. ETL synchronization provisions its quarterly dashboard from the refreshed analytics views.

## Data and capabilities

- Automated parsing and ingestion of Finansinspektionen quarterly XML data.
- `/datastatus` lists available quarters, ingestion states, FI source URLs, source filenames, and available publication metadata.
- `/compare` compares two reported quarter-end snapshots, including QoQ market-value and portfolio-weight changes and the labels **Ny position**, **Ökad position**, **Minskad position**, and **Avslutad position**.
- Holdings search results include FI source URL and filename and a publication date derived from the archive filename when present.
- The current control schema does not record distinct download timestamps or PostgreSQL upsert timestamps. The UI identifies these as unrecorded rather than presenting fetch completion as an upsert time.
- Holdings are ingested idempotently using quarter, fund, and instrument identifiers. Records missing an ISIN are excluded by the current loader; FI's source files are not changed.

## Routes

| Route | Purpose |
|---|---|
| `/` | Latest available quarterly holdings and HTMX search |
| `/datastatus` | Quarterly release and ingestion status |
| `/compare` | Side-by-side comparison of two historical quarters |
| `/api/search` | Search results as an HTML fragment |
| `/api/diagnostics` | Database connectivity and latest-quarter diagnostics |
| `/api/kpis` | Latest-quarter reported holdings market value and fund count |

## Local development

Requirements: Python 3.10+, PostgreSQL 15+, and (for Docker execution) Docker.

1. Create a local `.env` file containing a `DATABASE_URL` for your PostgreSQL instance. `.env` is ignored by Git; do not commit credentials.
2. Install dependencies and start the application:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./Fondinsyn
```

Open [http://localhost:8000](http://localhost:8000). If `DATABASE_URL` is unset or PostgreSQL is unavailable, the interface falls back to mock data for local UI testing.

Run the layout and comparison checks with:

```bash
python -m pytest -q
```

To run the ETL, set `DATABASE_URL` in the local, Git-ignored `.env` file. Keep any non-secret ETL settings in the local, Git-ignored `config/config.yaml`, then run:

```bash
python -m app.run_pipeline
```

To start the application and PostgreSQL together in Docker:

```bash
cp .env.example .env
# Set a private POSTGRES_PASSWORD in .env before starting
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). To run only the application image, use `docker build -t fondinsyn-web .` followed by `docker run --rm --env-file .env -p 8000:8000 fondinsyn-web`.

## Repository layout

- `app/`: FastAPI server, database models and SQL, ETL pipeline, and operational tools.
- `templates/`: Jinja2/HTMX pages and fragments.
- `static/`: Static assets, including images.
- `docs/`: Product, system, and pipeline documentation.
- `tests/`: Automated layout and application checks.
- Root: application configuration, Docker files, dependencies, and this README.

## Compliance and data source

Data source: [Finansinspektionen open data](https://www.fi.se/sv/om-fi/om-webbplatsen/oppen-data/).

### Viktig information

Datakälla: Finansinspektionen (FI). Uppgifterna hämtas från FI:s offentligt tillgängliga data.
Källa och hämtningsdatum anges för respektive datamängd.

Fondinsyn är ett oberoende projekt och är inte affilierat med, godkänt av eller utgivet av Finansinspektionen.
Finansinspektionen ansvarar inte för innehåll, beräkningar, tolkningar eller beslut baserade på denna tjänst.

Informationen avser kvartalsvisa innehav och kan vara ofullständig, fördröjd eller innehålla fel.
Tjänsten är endast avsedd för informations- och analysändamål och utgör inte investeringsrådgivning, finansiell rådgivning eller ett rekommendationsunderlag.
