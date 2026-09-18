import psycopg
conn = psycopg.connect('postgresql://postgres:2JI23CS123@localhost:5432/warehouse_db')
cur = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
for row in cur.fetchall():
    print(row)
