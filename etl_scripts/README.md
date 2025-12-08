# Clarification of load.py Files

Three separate loaders exist due to dataset size and performance requirements. The data is sourced from Q1 2022 to Q2 2025 this totals about 1.35M records. A single unified loader would bottleneck the entire pipeline, resulting in a 4+ hour completion time.

Each loader is optimized for its dataset's specific scale, no unnecessary abstraction or complexity. The tradeoff: ORM safety vs raw speed per data source.

## The three loaders.

### "load.py" Deals with Fund × Sector × Quarter Allocations
- **Dataset Size**: 59,312 records
- **Strategy**: SQLAlchemy ORM `bulk_insert_mappings()`
- **Approach**: 
  - FK lookups via `get_or_create_fund()` and `get_or_create_sector()` 
  - a 3 - layer deduplication (dict  DB query bulk insert new only)
  - Session management with flush() for relationship handling
- **Performance**: ~40 seconds
- **ORM**: Small volume makes overhead acceptable; provides type safety and session control

### "load_assets.py" Deals mostly with ISIN's and security.
- **Dataset Size**: about 15,000–28,000 unique ISINs
- **Strategy**: SQLAlchemy ORM with row-by-row iteration
- **Approach**:
  - Country - sector mapping (US→Technology, SE→Industrials, etc.)
  - Per row deduplication checks via session queries
  - Ticker validation (handles NaN & empty strings)
- **Performance**: close to 8 seconds
- **ORM**: Medium volume, the complex per record logic requires session context

### "load_holdings.py" Deals with Large portfolio holdings
- **Dataset Size**: 1,350,000+ rows
- **Strategy**: Psycopg2 (Python library) raw driver + PostgreSQL `COPY + UPSERT`
- **Approach**:
  - Pre loading fund/asset ID maps in Python dicts (hashmap) (O(1) in lookups)
  - Pandas vectorized deduplication on DataFrame
  - Raw `COPY` command (bypasses Python, uses PostgreSQL native bulk loader instead)
  - `ON CONFLICT DO NOTHING` for database level conflict handling
  - Staging file cleanup after completion
- **Performance**: 9 seconds COPY: 0.4s + UPSERT: 8.5s
- **Why Raw Driver**: 1.35M records would take 4–12 hours via ORM.

## Design Decision

Splitting into three files avoids the performance cliff of 1.35M rows through ORM. Each loader is self contained, testable, and optimized independently. No shared abstraction layer that would force compromise on either small or large datasets. Reason for doing it this way was because i tried to run it as one file.
