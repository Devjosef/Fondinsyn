import yaml
from pathlib import Path
from sqlalchemy import create_engine, text
from app.database.models import Base

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    config = yaml.safe_load(open(PROJECT_ROOT / 'config' / 'config.yaml'))
    conn_str = (
        f"postgresql://CREDENTIAL_REMOVED_9bcf166e240683cd1b72a7f9d05b8274@"
        f"{config['database']['host']}:{config['database']['port']}/{config['database']['db_name']}"
    )
    engine = create_engine(conn_str)

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS control"))

    Base.metadata.create_all(engine)
    print("All tables and schemas created")
    engine.dispose()


if __name__ == "__main__":
    main()
