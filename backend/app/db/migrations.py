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

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS publication_accounts (
                    id SERIAL PRIMARY KEY,
                    platform VARCHAR NOT NULL DEFAULT 'YOUTUBE',
                    account_name VARCHAR NOT NULL,
                    platform_account_id VARCHAR NOT NULL,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    credential_path VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS publications (
                    id SERIAL PRIMARY KEY,
                    clip_id INTEGER NOT NULL REFERENCES clips(id),
                    platform VARCHAR NOT NULL DEFAULT 'YOUTUBE',
                    status VARCHAR NOT NULL DEFAULT 'PENDING',
                    error_type VARCHAR,
                    error_details TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry TIMESTAMP,
                    platform_post_id VARCHAR,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    published_at TIMESTAMP,
                    CONSTRAINT uq_publication_clip_platform UNIQUE (clip_id, platform)
                )
            """))

            conn.execute(text("""
                ALTER TABLE publications
                ADD COLUMN IF NOT EXISTS thumbnail_uploaded_at TIMESTAMP
            """))

            conn.execute(text("""
                ALTER TABLE publications
                ADD COLUMN IF NOT EXISTS publication_account_id INTEGER REFERENCES publication_accounts(id)
            """))

            conn.commit()

            print("Database migration completed.")

        except Exception as e:
            print(f"Migration error: {e}")
