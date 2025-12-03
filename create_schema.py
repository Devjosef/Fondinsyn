import yaml
from sqlalchemy import create_engine, text
from database.models import Base

config = yaml.safe_load(open('config/config.yaml'))
conn_str = (f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@"
            f"{config['database']['host']}:{config['database']['port']}/{config['database']['db_name']}")

engine = create_engine(conn_str)

# NOTES to self: Create schemas FIRST (SQLAlchemy 2.0 - autocommits)
with engine.begin() as conn:  # begin() = auto-commit
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS control"))

# Create tables
Base.metadata.create_all(engine)
print(" All tables + schemas created")
engine.dispose()
