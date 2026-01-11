# import os
# import tempfile
# import subprocess
# from typing import Optional, Tuple
# import platform
# from app.services.security import decrypt_file
# from cryptography.hazmat.primitives.ciphers.aead import AESGCM
#
# def _derive_key_from_password(password: str, key_len: int = 32) -> bytes:
#     """
#     Простой способ получить ключ из пароля: здесь мы используем SHA256(password).
#     Если у тебя уже есть KDF (PBKDF2/scrypt) в проекте — подменишь эту функцию.
#     """
#     import hashlib
#     if not password:
#         raise ValueError("Пароль не может быть пустым для дешифрования.")
#     h = hashlib.sha256(password.encode('utf-8')).digest()
#     if key_len == 32:
#         return h
#     return h[:key_len]
#
# def decrypt_file_to_text(file_path: str, password: str) -> Tuple[Optional[str], Optional[bytes]]:
#     """
#     Пытается дешифровать файл и вернуть строку (если это UTF-8 текст) или байты.
#     Возвращает (text, raw_bytes). Если text не None — это utf-8 раскодированный текст.
#     Если оба None — ошибка/не поддерживаемый формат.
#     Формат ожидается: [12 байт nonce][ciphertext+tag]
#     """
#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"Файл не найден: {file_path}")
#
#     # Читаем весь файл
#     with open(file_path, "rb") as f:
#         data = f.read()
#
#     if len(data) < 13:
#         raise ValueError("Файл слишком маленький для ожидаемого формата (nonce+ciphertext).")
#
#     # 12 байт nonce (IV) — стандарт для AESGCM
#     nonce = data[:12]
#     ciphertext = data[12:]
#
#     key = _derive_key_from_password(password, 32)  # 256-bit key
#
#     aesgcm = AESGCM(key)
#     try:
#         plain = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
#     except Exception as e:
#         # неверный пароль или неподходящий формат
#         raise ValueError(f"Не удалось дешифровать файл: {e}")
#
#     # Попытка распарсить как utf-8 текст
#     try:
#         text = plain.decode('utf-8')
#         return text, plain
#     except UnicodeDecodeError:
#         return None, plain
#
#
# def decrypt_file_to_temp_and_open(file_path: str, password: str) -> str:
#     """
#     Дешифрует зашифрованный файл в временную директорию и открывает его в стандартном приложении ОС.
#     Возвращает путь к временно созданному файлу.
#     """
#     if not os.path.exists(file_path):
#         raise FileNotFoundError(f"Файл не найден: {file_path}")
#
#     # Получаем содержимое в байтах
#     try:
#         data = decrypt_file(file_path, password)
#     except Exception as e:
#         raise ValueError(f"Не удалось дешифровать файл: {e}")
#
#     # Создаём временный файл с оригинальным именем
#     _, ext = os.path.splitext(file_path)
#     tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
#     tmp_file.write(data)
#     tmp_file.close()
#
#     # Открываем файл через стандартное приложение ОС
#     system = platform.system()
#     try:
#         if system == "Darwin":  # macOS
#             subprocess.run(["open", tmp_file.name], check=False)
#         elif system == "Windows":
#             os.startfile(tmp_file.name)
#         else:  # Linux и другие
#             subprocess.run(["xdg-open", tmp_file.name], check=False)
#     except Exception as e:
#         raise RuntimeError(f"Не удалось открыть файл: {e}")
#
#     return tmp_file.name
