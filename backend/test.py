import psycopg
conn = psycopg.connect('postgresql://postgres:2JI23CS123@localhost:5432/warehouse_db')
cur = conn.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'inventory';")
for row in cur.fetchall():
    print(row)

cur = conn.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'batches';")
for row in cur.fetchall():
    print(row)
