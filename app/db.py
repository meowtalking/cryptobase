from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from .models import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Получение сессии
def get_session():
    return SessionLocal()

from pathlib import Path
from platformdirs import user_data_dir, user_config_dir

# Главная директория приложения
APP_NAME = "CryptoBase"
APP_AUTHOR = "Name"          # можно оставить пустым

DATA_DIR = Path(user_data_dir(APP_NAME, APP_AUTHOR))      # данные + backups.enc
CONFIG_DIR = Path(user_config_dir(APP_NAME, APP_AUTHOR))  # настройки, salt и т.д.

DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Пути к важным файлам
BACKUPS_PATH = DATA_DIR / "backups.enc"
MASTER_SALT_PATH = CONFIG_DIR / "master_salt.bin"
MASTER_HASH_PATH = CONFIG_DIR / "master_hash.bin"
DB_PATH = DATA_DIR / "cryptobase.db"
SETTINGS_PATH = CONFIG_DIR / "settings.json"