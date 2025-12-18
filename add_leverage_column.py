
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
DATABASE_URL = SUPABASE_DB_URL or os.getenv("DATABASE_URL")
if "sslmode" not in DATABASE_URL and "sqlite" not in DATABASE_URL:
    DATABASE_URL += "?sslmode=require"

engine = create_engine(DATABASE_URL)

def add_column():
    with engine.connect() as conn:
        try:
            print("Adding leverage column...")
            conn.execute(text("ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage FLOAT DEFAULT 1.0"))
            conn.commit()
            print("✅ Column added.")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    add_column()
