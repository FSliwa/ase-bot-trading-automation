#!/usr/bin/env python3
"""Test database connection on different ports."""
import psycopg2
from urllib.parse import quote_plus

password = quote_plus('MIlik112!@4')

# Test port 5432 (direct - currently broken)
print("=" * 50)
print("Testing PORT 5432 (direct connection)...")
conn_string_5432 = f'postgresql://postgres:{password}@db.iqqmbzznwpheqiihnjhz.supabase.co:5432/postgres'
try:
    conn = psycopg2.connect(conn_string_5432, connect_timeout=5)
    cursor = conn.cursor()
    cursor.execute('SELECT NOW()')
    result = cursor.fetchone()
    print(f'✅ Port 5432 SUCCESS! Server time: {result[0]}')
    conn.close()
except Exception as e:
    print(f'❌ Port 5432 FAILED: {e}')

# Test port 6543 (pooler)
print("=" * 50)
print("Testing PORT 6543 (connection pooler)...")
conn_string_6543 = f'postgresql://postgres:{password}@db.iqqmbzznwpheqiihnjhz.supabase.co:6543/postgres'
try:
    conn = psycopg2.connect(conn_string_6543, connect_timeout=5)
    cursor = conn.cursor()
    cursor.execute('SELECT NOW()')
    result = cursor.fetchone()
    print(f'✅ Port 6543 SUCCESS! Server time: {result[0]}')
    conn.close()
except Exception as e:
    print(f'❌ Port 6543 FAILED: {e}')

print("=" * 50)
print("Test complete!")
