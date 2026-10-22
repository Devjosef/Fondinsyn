# SwedFund ETL – Swedish Index Funds Pipeline

**BLUF:** En automatiserad ETL-pipeline och terminal-dashboard som hämtar, transformerar och lagrar innehavsdata från Finansinspektionen (FI) för alla registrerade svenska fonder.

---

## Architecture & Data Flow

```text
[Finansinspektionen XML]
        │
        ▼
[fetch_fi_data.py] ── Hämtar & packar upp ZIP-arkiv
        │
        ▼
[transform.py] ── Rensar, skalare vikter (/10 000), market-cap bucketing
        │
        ▼
┌────────────────────────────────────────────────────────┐
│                 3-Tier Loader Strategy                 │
├─────────────────┬──────────────────┬───────────────────┤
│ load.py         │ load_assets.py   │ load_holdings.py  │
│ (ORM Bulk       │ (Row-by-row ORM  │ (Raw PostgreSQL   │
│  Insert, ~60k)  │  ~20k assets)    │  COPY, 1.35M+)    │
└─────────────────┴──────────────────┴───────────────────┘
        │
        ▼
[PostgreSQL Database] ── analytics.mv_holdings_by_quarter
        │
        ▼
[FastAPI + HTMX Dashboard] ── http://localhost:8000
```

---

## Projektöversikt & Syfte

Projektet automatiserar den kvartalsvisa hanteringen av fondinnehav publicerade av Finansinspektionen (FI). Syftet är att eliminera manuell nedladdning och tolkning av råa XML-filer, samt erbjuda en historisk bild av vad svenska fonder faktiskt äger.

Genom att standardisera sektormappningar och storleksklasser (market-cap buckets) över tid blir det enkelt att följa trender, analysera risker och jämföra fonders sammansättning.

---

## Domänspecifika Affärsregler

Pipelinen hanterar flera regelverk och datastrukturer specifika för Finansinspektionens rapportering:

- **Vikt-skalning (`weight_pct`):** Rådata från FI anger portföljvikter i en fast punkt-skala. Pipelinen dividerar värden med `10 000` för att erhålla faktiska procentvärden.
- **Börsvärdeskategorisering (Market Cap Bucketing):** Bolag sorteras dynamiskt i *Small*, *Mid*, och *Large Cap* baserat på relativ rankning/percentiler (0–40 %, 40–80 %, 80–100 %).
- **Sektormappning:** Länder och värdepapper utan explicita branschkoder mappas via heuristik till primära sektorer (*Technology*, *Industrials*, *Financials*, m.fl.).

---

## Prestanda & Inläsningsstrategi

För att undvika prestandaflaskhalsar vid hantering av över 1,35 miljoner rader är inläsningen uppdelad i tre optimerade laddare:

| Skript | Måldata | Volym | Metod | Tid |
| :--- | :--- | :--- | :--- | :--- |
| `load.py` | Fond- och sektorallokeringar | ~60k rader | SQLAlchemy ORM Bulk Insert | ~40 s |
| `load_assets.py` | Värdepapper och ISIN:er | ~20k rader | Row-by-row ORM (validering) | ~8 s |
| `load_holdings.py` | Portföljinnehav | 1,35M+ rader | Raw PostgreSQL `COPY` + Upsert | ~9 s |

---

## Snabbstart & Körning

### 1. Förutsättningar

- Python 3.10+
- Docker och Docker Compose

### 2. Starta databasen

```bash
docker-compose up -d
```

### 3. Kör ETL-pipelinen

```bash
# Hämta och transformera data från FI
python run_pipeline.py
```

### 4. Starta terminal-dashboarden

```bash
python dashboard_main.py
```

Öppna [http://localhost:8000](http://localhost:8000) för att söka i innehav via HTMX-gränssnittet.

---

## Teknisk Stack

- **Språk & ramverk:** Python 3, Pandas, FastAPI, HTMX, Jinja2
- **Databas:** PostgreSQL 15, SQLAlchemy, Psycopg2
- **Infrastruktur:** Docker, Docker Compose
- **Konfiguration:** PyYAML

---

## Friskrivning

Detta projekt är ett självständigt initiativ och har ingen officiell koppling till Finansinspektionen.