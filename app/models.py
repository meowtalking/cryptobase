from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from sqlalchemy import create_engine
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # путь к app/
DATABASE_PATH = os.path.join(BASE_DIR, "cryptobase.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# --- Базовый класс для моделей ---
Base = declarative_base()

# --- Модель файлов ---
class FileRecord(Base):
    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False, unique=True)
    algorithm = Column(String, nullable=False)
    current_hash = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)  # для защиты паролем
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="OK")  # OK / Modified / Missing

    # Связь с версиями
    versions = relationship(
        "FileVersion", back_populates="file", cascade="all, delete-orphan", order_by="FileVersion.created_at.desc()"
    )

    def __repr__(self):
        return f"<FileRecord(name='{self.name}', path='{self.path}', algorithm='{self.algorithm}')>"

# --- Модель версий файлов ---
class FileVersion(Base):
    __tablename__ = "file_versions"

    id = Column(Integer, primary_key=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False)
    version_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    comment = Column(String, default="")         # комментарий к версии
    location = Column(String, default="local")  # local / server

    file = relationship("FileRecord", back_populates="versions")

    def __repr__(self):
        return f"<FileVersion(file_id={self.file_id}, created_at={self.created_at}, location='{self.location}')>"

# --- Модель системных логов ---
class LogEntry(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    action = Column(String, nullable=False)     # add_file, delete_file, check_integrity, backup и т.д.
    file_name = Column(String, nullable=True)
    result = Column(String, nullable=False)
    user_name = Column(String, nullable=True)   # имя пользователя, выполнившего действие
    timestamp = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<LogEntry(action='{self.action}', file='{self.file_name}', user='{self.user_name}', result='{self.result}')>"

# --- Модель настроек программы ---
class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    value = Column(String, nullable=False)

    def __repr__(self):
        return f"<Setting(key='{self.key}', value='{self.value}')>"


# Создаем движок и сессию
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    print("🔧 Initializing database...")
    Base.metadata.create_all(engine)
    print("✅ Database initialized!")

if __name__ == "__main__":
    init_db()
