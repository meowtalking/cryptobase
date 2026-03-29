import os
import bcrypt
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def hash_password_for_db(password: str) -> str:
    """Создаёт bcrypt-хэш для хранения в базе."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password_for_db(password: str, stored_hash: str) -> bool:
    """Проверяет введённый пароль с хэшем из базы."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except Exception:
        return False

def derive_key(password: str, salt: bytes) -> bytes:
    """Генерирует ключ для Fernet по паролю и соли"""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def decrypt_file_from_bytes(encrypted_data: bytes, password: str) -> bytes:
    """
    Расшифровывает байты файла, используя соль из первых 16 байт.
    """
    if len(encrypted_data) < 16:
        raise ValueError("Повреждённые зашифрованные данные")

    salt = encrypted_data[:16]
    ciphertext = encrypted_data[16:]

    key = derive_key(password, salt)  # твоя функция derive_key (PBKDF2 или что у тебя)
    fernet = Fernet(key)
    return fernet.decrypt(ciphertext)

def encrypt_file(file_path: str, password: str):
    """Шифрует файл, сохраняет соль + зашифрованные данные"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")

    salt = os.urandom(16)
    key = derive_key(password, salt)
    fernet = Fernet(key)

    with open(file_path, "rb") as f:
        data = f.read()

    encrypted = fernet.encrypt(data)
    with open(file_path, "wb") as f:
        f.write(salt + encrypted)

def decrypt_file(file_path: str, password: str) -> bytes:
    """Дешифрует файл, используя соль из файла"""
    with open(file_path, 'rb') as f:
        data = f.read()
    salt = data[:16]
    encrypted = data[16:]
    key = derive_key(password, salt)
    fernet = Fernet(key)
    return fernet.decrypt(encrypted)
