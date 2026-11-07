**A Swedish-language quarterly fund-holdings explorer built on public data from Finansinspektionen.**

The ETL uses three separate loaders to prevent a 4+ hour performance bottleneck caused by processing 1.35M records through a single ORM. Each loader matches strategy to scale.

---

### The Three Loaders

1. **`load.py` (Allocations)**
* **Scale:** ~60k records
* **Method:** SQLAlchemy ORM bulk insert
* **Time:** ~40s


2. **`load_assets.py` (Assets & ISINs)**
* **Scale:** ~20k records
* **Method:** Row-by-row ORM (handles mapping & validation)
* **Time:** ~8s


3. **`load_holdings.py` (Portfolio Holdings)**
* **Scale:** 1.35M+ records
* **Method:** Raw PostgreSQL `COPY` + Python hashmap lookup
* **Time:** ~9s *(ORM would take 4–12 hours)*