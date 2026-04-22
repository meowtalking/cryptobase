# app/ui/login_dialog.py

import os
import re
from pathlib import Path
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from argon2 import PasswordHasher, low_level
from argon2.exceptions import VerifyMismatchError
import secrets

from app.db import BACKUPS_PATH

# Константы
CONFIG_DIR = BACKUPS_PATH / ".cryptobase"
SALT_FILE = CONFIG_DIR / "master_salt.bin"
HASH_FILE = CONFIG_DIR / "master_hash.bin"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CryptoBase — Вход")
        self.setFixedSize(420, 220)
        self.is_first_time = not HASH_FILE.exists()

        self.layout = QVBoxLayout()
        self.init_ui()
        self.setLayout(self.layout)

    def init_ui(self):
        if self.is_first_time:
            self.setWindowTitle("CryptoBase — Установка мастер-пароля")
            title_text = "Установите мастер-пароль для защиты данных"
        else:
            title_text = "Введите мастер-пароль"

        self.label = QLabel(title_text)
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.layout.addWidget(QLabel("Пароль:"))
        self.layout.addWidget(self.password_edit)

        if self.is_first_time:
            self.confirm_edit = QLineEdit()
            self.confirm_edit.setEchoMode(QLineEdit.Password)
            self.layout.addWidget(QLabel("Подтвердите пароль:"))
            self.layout.addWidget(self.confirm_edit)

        btn = QPushButton("Подтвердить")
        btn.clicked.connect(self.try_accept)
        self.layout.addWidget(btn)

    def try_accept(self):
        password = self.password_edit.text().strip()

        if not password:
            QMessageBox.warning(self, "Ошибка", "Пароль не может быть пустым")
            return

        if self.is_first_time:
            confirm = self.confirm_edit.text().strip()
            if password != confirm:
                QMessageBox.warning(self, "Ошибка", "Пароли не совпадают")
                return

            if not self.is_password_strong(password):
                self.show_password_requirements()
                return

            # Генерируем и сохраняем соль (16 байт)
            salt = secrets.token_bytes(16)
            with open(SALT_FILE, "wb") as f:
                f.write(salt)

            # Хэш пароля для проверки (хранится отдельно)
            ph = PasswordHasher(time_cost=4, memory_cost=65536, parallelism=4)
            hash_value = ph.hash(password)

            with open(HASH_FILE, "wb") as f:
                f.write(hash_value.encode('utf-8'))

            # Передаём пароль родительскому окну для генерации master_key
            self.parent().set_password_for_key(password)

            QMessageBox.information(self, "Успех", "Мастер-пароль установлен!")
            self.accept()

        else:
            if not HASH_FILE.exists():
                QMessageBox.critical(self, "Ошибка", "Файл хэша не найден")
                self.reject()
                return

            with open(HASH_FILE, "rb") as f:
                stored_hash = f.read().decode('utf-8').strip()

            ph = PasswordHasher()
            try:
                ph.verify(stored_hash, password)
                # Передаём пароль родителю для генерации ключа
                self.parent().set_password_for_key(password)
                self.accept()
            except VerifyMismatchError:
                QMessageBox.critical(self, "Ошибка", "Неверный мастер-пароль")

    @staticmethod
    def is_password_strong(pw: str) -> bool:
        if len(pw) < 8: return False
        if not re.search(r'[a-z]', pw): return False
        if not re.search(r'[A-Z]', pw): return False
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\'\\:"|<,./<>?`~]', pw): return False
        return True

    def show_password_requirements(self):
        msg = (
            "Требования к паролю:\n\n"
            "• Минимум 8 символов\n"
            "• Хотя бы одна строчная буква (a–z)\n"
            "• Хотя бы одна заглавная буква (A–Z)\n"
            "• Хотя бы один специальный символ (!@#$%^&*()_+-= и т.п.)"
        )
        QMessageBox.warning(self, "Слабый пароль", msg)

    def reject(self):
        # При любом закрытии диалога (крестик, Esc) — просто возвращаем Rejected
        # Выход обрабатывается в MainWindow
        super().reject()