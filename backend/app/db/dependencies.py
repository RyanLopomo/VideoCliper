from app.db.database import SesionLocal

def get_db():
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()