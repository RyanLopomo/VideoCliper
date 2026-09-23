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
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS last_completed_step VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS current_job_id VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS processing_progress INTEGER
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS processing_message VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS last_progress_at TIMESTAMP
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMP
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS error_type VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS publication_plan_enabled BOOLEAN NOT NULL DEFAULT FALSE
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS publication_max_per_day INTEGER
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS publication_start_date VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS publication_times TEXT
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS publication_timezone VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS publication_plan_applied_at TIMESTAMP
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS editing_style VARCHAR NOT NULL DEFAULT 'AUTO'
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS target_clip_count INTEGER
            """))

            conn.execute(text("""
                ALTER TABLE videos
                ADD COLUMN IF NOT EXISTS target_clip_duration INTEGER NOT NULL DEFAULT 60
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS editing_style VARCHAR NOT NULL DEFAULT 'AUTO'
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS applied_preset VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS ai_style_recommendation VARCHAR
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS ai_style_confidence FLOAT
            """))

            conn.execute(text("""
                ALTER TABLE clips
                ADD COLUMN IF NOT EXISTS ai_style_reason TEXT
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

            conn.execute(text("""
                ALTER TABLE publications
                ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP
            """))

            conn.execute(text("""
                ALTER TABLE publications
                ADD COLUMN IF NOT EXISTS manual BOOLEAN NOT NULL DEFAULT FALSE
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    event_key VARCHAR NOT NULL UNIQUE,
                    type VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    message TEXT NOT NULL,
                    video_id INTEGER,
                    clip_id INTEGER,
                    publication_id INTEGER,
                    platform VARCHAR,
                    url VARCHAR,
                    read BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.commit()

            print("Database migration completed.")

        except Exception as e:
            print(f"Migration error: {e}")
