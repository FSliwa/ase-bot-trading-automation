import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.append(str(Path(__file__).parent))

load_dotenv()

# Get database URL
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL not set")
    sys.exit(1)

if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)

def list_api_keys():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM api_keys LIMIT 1"))
        print("\nColumns in api_keys table:")
        print("-" * 50)
        for key in result.keys():
            print(key)
        print("-" * 50)

if __name__ == "__main__":
    list_api_keys()
