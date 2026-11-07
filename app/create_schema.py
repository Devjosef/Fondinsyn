from sqlalchemy import text

from app.database.connection import create_database_engine
from app.database.models import Base


def main() -> None:
    engine = create_database_engine()

    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS control"))

    Base.metadata.create_all(engine)
    print("All tables and schemas created")
    engine.dispose()


if __name__ == "__main__":
    main()
