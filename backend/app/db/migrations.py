from sqlalchemy import text
from app.db.database import engine


def run_migrations():
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS processing_stage VARCHAR DEFAULT 'PENDING'
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS last_completed_clip INTEGER DEFAULT 0
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0
            """))

            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'clips'
                        AND column_name = 'tittle'
                    )
                    AND NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'clips'
                        AND column_name = 'title'
                    )
                    THEN
                        ALTER TABLE clips
                        RENAME COLUMN tittle TO title;
                    END IF;
                END $$;
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS title VARCHAR
            """))

            conn.commit()

            print("Database migration completed.")

        except Exception as e:
            print(f"Migration error: {e}")
