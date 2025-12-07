import sqlite3
import os

db_path = "Automatyczny Stock Market 1.0/trading.db"
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List tables
print("Tables:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for table in tables:
    print(f"- {table[0]}")

# Check profiles if exists
target_tables = ["profiles", "api_keys", "trading_settings"]
for target in target_tables:
    found = False
    for table in tables:
        if table[0] == target or table[0].endswith(f"_{target}"):
            found = True
            print(f"\n--- Content of {table[0]} ---")
            try:
                # Get columns
                cursor.execute(f"PRAGMA table_info({table[0]})")
                columns = [col[1] for col in cursor.fetchall()]
                print(f"Columns: {columns}")
                
                cursor.execute(f"SELECT * FROM {table[0]}")
                rows = cursor.fetchall()
                print(f"Row count: {len(rows)}")
                for row in rows:
                    print(row)
            except Exception as e:
                print(f"Error reading {table[0]}: {e}")
    
    if not found:
        print(f"\n❌ Table '{target}' not found.")

conn.close()
