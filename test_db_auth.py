import os
import sys
import psycopg2
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

load_dotenv()

db_url = os.getenv("DATABASE_URL")
parsed = urlparse(db_url)

username = parsed.username
password = unquote(parsed.password) # Decode the password
hostname = parsed.hostname
port = parsed.port
database = parsed.path[1:] # Remove leading /

print(f"Attempting connection to {hostname}:{port} as {username}")
print(f"Database: {database}")
# print(f"Password (first 2 chars): {password[:2]}...") 

try:
    conn = psycopg2.connect(
        host=hostname,
        user=username,
        password=password,
        port=port,
        dbname=database,
        sslmode='require'
    )
    print("✅ Authentication successful!")
    conn.close()
except Exception as e:
    print(f"❌ Authentication failed: {e}")
