import os

from sqlalchemy import create_engine, text
database_url = os.getenv("DATABASE_URL")
if not database_url:
    raise SystemExit("Set DATABASE_URL to the database to inspect.")

engine = create_engine(database_url)
with engine.connect() as connection:
    result = connection.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'inventory';"))
    for row in result:
        print(row)

    result = connection.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'batches';"))
    for row in result:
        print(row)
