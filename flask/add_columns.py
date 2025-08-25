import sqlite3

DB_PATH = "workers.db"
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Добавяне на колони, ако не съществуват
try:
    c.execute("ALTER TABLE workers ADD COLUMN rank TEXT DEFAULT 'Стандартен'")
except sqlite3.OperationalError:
    print("Колоната rank вече съществува")

try:
    c.execute("ALTER TABLE workers ADD COLUMN special_rate REAL DEFAULT 50")
except sqlite3.OperationalError:
    print("Колоната special_rate вече съществува")

conn.commit()
conn.close()
print("Колоните rank и special_rate са добавени или вече съществуват")