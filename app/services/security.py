import hashlib
import bcrypt
import xxhash
import os


# ==============================
# 🔐 Алгоритмы хэширования файлов
# ==============================

def compute_hash(file_path: str, algorithm: str = "sha256") -> str:
    """
    Вычисляет хэш для указанного файла выбранным алгоритмом.
    Поддерживает: sha256, sha512, blake2b, md5, xxhash.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    # Определяем размер блока для чтения (чтобы не грузить память)
    block_size = 65536

    # Выбор алгоритма
    if algorithm.lower() == "sha256":
        hasher = hashlib.sha256()
    elif algorithm.lower() == "sha512":
        hasher = hashlib.sha512()
    elif algorithm.lower() == "blake2b":
        hasher = hashlib.blake2b()
    elif algorithm.lower() == "md5":
        hasher = hashlib.md5()
    elif algorithm.lower() == "xxhash":
        hasher = xxhash.xxh64()
    else:
        raise ValueError(f"Неподдерживаемый алгоритм: {algorithm}")

    # Читаем файл по блокам
    with open(file_path, "rb") as f:
        while chunk := f.read(block_size):
            hasher.update(chunk)

    # Возвращаем итоговый хэш в hex
    return hasher.hexdigest()


# ==================================
# 🔒 Хэширование и проверка паролей
# ==================================

def hash_password(password: str) -> str:
    """
    Хэширует пароль с использованием bcrypt + соль.
    Возвращает строку, которую можно хранить в БД.
    """
    if not password:
        raise ValueError("Пароль не может быть пустым.")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """
    Проверяет, совпадает ли введённый пароль с сохранённым хэшем.
    """
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False
