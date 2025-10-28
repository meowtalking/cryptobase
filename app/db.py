from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from .models import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Получение сессии
def get_session():
    return SessionLocal()
