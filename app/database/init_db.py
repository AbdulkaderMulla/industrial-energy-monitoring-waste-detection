from app.database.connection import Base, engine
from app.database import models  # noqa: F401

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Database schema initialized.")
