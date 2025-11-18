import os
from sqlalchemy import create_engine, text
from datetime import datetime


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    try:
        with open("/opt/trading-bot/.env.db", "r") as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.strip().split("=", 1)[1]
    except FileNotFoundError:
        pass
    raise RuntimeError("DATABASE_URL not found")


def main():
    url = get_database_url()
    engine = create_engine(url)
    now = datetime.utcnow()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO research_articles (
                    source, source_url, title, summary, topic, symbol,
                    scraped_at, sentiment_score, relevance, credibility, raw_json
                ) VALUES (
                    :source, :url, :title, :summary, :topic, :symbol,
                    :scraped_at, :sentiment, :relevance, :cred, :raw
                )
                """
            ),
            {
                "source": "smoke_test",
                "url": "http://example.com/test",
                "title": "Smoke Test Insert",
                "summary": "Inserted by automated smoke test",
                "topic": "market",
                "symbol": "BTCUSDT",
                "scraped_at": now,
                "sentiment": 0.1,
                "relevance": 0.5,
                "cred": 0.9,
                "raw": "{\"test\": true}",
            },
        )

        rows = conn.execute(
            text(
                """
                SELECT id, source, title, symbol, sentiment_score, scraped_at
                FROM research_articles
                WHERE source = 'smoke_test'
                ORDER BY id DESC
                LIMIT 3
                """
            )
        ).fetchall()

    print("ROWS:", [dict(r._mapping) for r in rows])


if __name__ == "__main__":
    main()
