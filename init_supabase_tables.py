#!/usr/bin/env python3
"""
Initialize Supabase database tables for ASE Trading Bot.

This script creates all necessary tables in the Supabase PostgreSQL database:
- users: User authentication and profiles
- positions: Trading positions
- orders: Trading orders
- fills: Order fills/executions
- trading_stats: Performance statistics
- risk_events: Risk management events
- trading_bots: AI bot configurations
- ai_analysis: Market analysis results
- portfolio_snapshots: Historical portfolio snapshots

Usage:
    python init_supabase_tables.py
"""

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from sqlalchemy import inspect, text

from bot.database import DatabaseManager, engine
from bot.models import Base
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_expected_tables_by_schema() -> Dict[str, List[str]]:
    """Map database schemas to expected table names from SQLAlchemy metadata."""
    tables_by_schema: Dict[str, set] = defaultdict(set)
    for table in Base.metadata.sorted_tables:
        schema = table.schema or "public"
        tables_by_schema[schema].add(table.name)
    return {schema: sorted(names) for schema, names in tables_by_schema.items()}


def check_database_connection():
    """Test database connection."""
    try:
        with DatabaseManager() as db:
            # Simple query to test connection
            result = db.session.execute(text("SELECT 1")).fetchone()
            logger.info(f"✓ Database connection successful: {result}")
            return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False


def create_all_tables():
    """Create all database tables."""
    try:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("✓ All tables created successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to create tables: {e}")
        return False


def verify_tables():
    """Verify that all tables defined in ORM metadata exist in the database."""
    expected_by_schema = get_expected_tables_by_schema()

    try:
        inspector = inspect(engine)
        all_present = True

        logger.info("\nExisting tables by schema:")
        for schema, tables in expected_by_schema.items():
            inspector_schema = schema if schema != "public" else "public"
            existing_tables = set(inspector.get_table_names(schema=inspector_schema))

            logger.info(f"\nSchema: {schema}")
            for table in sorted(existing_tables):
                status = "✓" if table in tables else "?"
                logger.info(f"  {status} {table}")

            missing_tables = [table for table in tables if table not in existing_tables]
            if missing_tables:
                all_present = False
                logger.warning(f"  ⚠ Missing tables: {', '.join(missing_tables)}")

        if all_present:
            total_expected = sum(len(tables) for tables in expected_by_schema.values())
            logger.info(f"\n✓ All {total_expected} expected tables exist")
        return all_present
    except Exception as e:
        logger.error(f"✗ Failed to verify tables: {e}")
        return False


def show_table_info():
    """Show column information for each table."""
    tables_by_schema = get_expected_tables_by_schema()
    inspector = inspect(engine)

    try:
        for schema, tables in tables_by_schema.items():
            inspector_schema = schema if schema != "public" else "public"
            for table in tables:
                logger.info(f"\n{'='*60}")
                logger.info(f"Table: {schema}.{table}")
                logger.info(f"{'='*60}")

                try:
                    columns = inspector.get_columns(table, schema=inspector_schema)
                except Exception as column_error:
                    logger.warning(f"  Unable to retrieve columns: {column_error}")
                    continue

                if columns:
                    logger.info(f"{'Column':<25} {'Type':<20} {'Nullable':<10} {'Default'}")
                    logger.info(f"{'-'*80}")
                    for column in columns:
                        default_val = column.get('default', '')
                        default_display = str(default_val)[:30] if default_val else ""
                        logger.info(
                            f"{column['name']:<25} {column['type']:<20} {str(column.get('nullable', True)):<10} {default_display}"
                        )
                else:
                    logger.warning("  No columns found (table might not exist)")

    except Exception as e:
        logger.error(f"✗ Failed to show table info: {e}")


def main():
    """Main initialization flow."""
    logger.info("="*70)
    logger.info("ASE Trading Bot - Supabase Database Initialization")
    logger.info("="*70)
    
    # Check environment variables
    db_url = os.getenv('SUPABASE_DB_URL') or os.getenv('DATABASE_URL')
    if not db_url:
        logger.error("\n✗ DATABASE_URL or SUPABASE_DB_URL environment variable not set!")
        logger.error("Please ensure .env.production is loaded or set the variable manually.")
        return 1
    
    logger.info(f"\nDatabase URL: {db_url.split('@')[0]}@***")  # Hide password
    
    # Step 1: Test connection
    logger.info("\n" + "="*70)
    logger.info("Step 1: Testing database connection...")
    logger.info("="*70)
    if not check_database_connection():
        logger.error("\n✗ Initialization aborted: Cannot connect to database")
        return 1
    
    # Step 2: Create tables
    logger.info("\n" + "="*70)
    logger.info("Step 2: Creating database tables...")
    logger.info("="*70)
    if not create_all_tables():
        logger.error("\n✗ Initialization aborted: Failed to create tables")
        return 1
    
    # Step 3: Verify tables
    logger.info("\n" + "="*70)
    logger.info("Step 3: Verifying tables...")
    logger.info("="*70)
    if not verify_tables():
        logger.warning("\n⚠ Some tables are missing, but continuing...")
    
    # Step 4: Show table structure
    logger.info("\n" + "="*70)
    logger.info("Step 4: Database schema information...")
    logger.info("="*70)
    show_table_info()
    
    logger.info("\n" + "="*70)
    logger.info("✓ Database initialization completed successfully!")
    logger.info("="*70)
    logger.info("\nNext steps:")
    logger.info("  1. Run the FastAPI application: python app.py")
    logger.info("  2. Test authentication: POST /api/auth/register")
    logger.info("  3. Check database: Query users table in Supabase dashboard")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
