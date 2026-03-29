import os
import sys
import json
from pathlib import Path

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox
from PyQt5.QtCore import QTimer

from app.services.FileWatcher import FileWatcher
from app.services.backup_container import BackupContainer
from app.ui.local_storage_page import LocalStoragePage
from app.ui.login_dialog import LoginDialog, SALT_FILE

from app.db import SessionLocal
from app.models import LogEntry
from app.services.integrity_manager import now_msk


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CryptoBase")
        self.setFixedSize(1000, 600)

        self.master_key = None
        self.auto_lock_timer = QTimer(self)
        self.auto_lock_timer.setSingleShot(True)
        self.auto_lock_timer.timeout.connect(self.lock_app)

        # Аутентификация ДО интерфейса
        if not self.authenticate_user():
            sys.exit(0)

        # После успешной аутентификации master_key уже установлен
        # (предполагается, что LoginDialog вызывает set_password_for_key)

        # Читаем настройки (max_versions, auto_lock)
        settings_path = Path(__file__).parent / "settings.json"
        self.auto_lock_minutes = 30
        self.max_versions = 5

        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    self.auto_lock_minutes = settings.get("auto_lock_minutes", 30)
                    self.max_versions = settings.get("max_versions", 5)
            except Exception as e:
                print(f"Ошибка чтения settings.json: {e}")

        # Создаём только локальное хранилище
        self.local_page = LocalStoragePage(main_window=self)
        self.setCentralWidget(self.local_page)

        # Кэш контейнера
        # self._container_cache = None

        # ←←← ЗАПУСК FileWatcher — здесь самое правильное место
        self.file_watcher = FileWatcher(
            main_window=self,
            local_page=self.local_page,     # для сигнала обновления таблицы
            interval=10                     # или 5–15 секунд для тестов
        )
        self.file_watcher.start()
        print("[MAIN] FileWatcher запущен (interval = {} сек)".format(self.file_watcher.interval))

        self.start_auto_lock_timer(minutes=self.auto_lock_minutes)

        # Отладочная информация (можно оставить или убрать позже)
        print("Master key length:", len(self.master_key))
        container = self.get_container()
        print("Файлы в контейнере:", container.list_files())
        for file_id in container.list_files():
            versions = container.get_all_versions(file_id)
            print(f"  Файл ID {file_id}: {len(versions)} версий")

    def get_container(self):
        if not self.master_key:
            raise RuntimeError("Master key not available")
        return BackupContainer(self.master_key)  # всегда новый, всегда читает с диска

    def authenticate_user(self) -> bool:
        dialog = LoginDialog(parent=self)
        result = dialog.exec_()

        # Логируем попытку входа
        try:
            session = SessionLocal()
            if result == LoginDialog.Accepted:
                session.add(LogEntry(
                    action="login_success",
                    file_name=None,
                    result="Успешный вход в приложение",
                    user_name=os.getlogin()
                ))
                print("[LOG] Успешный вход")
            else:
                session.add(LogEntry(
                    action="login_failed",
                    file_name=None,
                    result="Неверный мастер-пароль или отмена",
                    user_name=os.getlogin()
                ))
                print("[LOG] Неудачная попытка входа")
            session.commit()
        except Exception as e:
            print(f"[LOG ERROR] Не удалось записать лог входа: {e}")
        finally:
            session.close()

        return result == LoginDialog.Accepted

    def start_auto_lock_timer(self, minutes: int):
        if minutes <= 0:
            return
        self.auto_lock_timer.start(minutes * 60 * 1000)

    def lock_app(self):
        self.master_key = None
        self.auto_lock_timer.stop()

        if not self.authenticate_user():
            sys.exit(0)
        else:
            self.start_auto_lock_timer(minutes=30)
            # После повторного входа ничего не делаем — уже на LocalStoragePage

    def set_password_for_key(self, password: str):
        """Генерирует master_key из пароля + соли"""
        from argon2.low_level import hash_secret_raw, Type

        if not SALT_FILE.exists():
            QMessageBox.critical(self, "Ошибка", "Соль для ключа не найдена")
            QApplication.quit()
            return

        with open(SALT_FILE, "rb") as f:
            salt = f.read()

        master_key = hash_secret_raw(
            secret=password.encode('utf-8'),
            salt=salt,
            time_cost=4,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            type=Type.ID
        )

        self.master_key = master_key

    def get_max_versions(self) -> int:
        return self.max_versions

    def get_auto_lock_minutes(self) -> int:
        return self.auto_lock_minutes

    def set_auto_lock_minutes(self, value: int):
        self.auto_lock_minutes = value
        settings_path = Path(__file__).parent / "settings.json"
        settings = {}
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        settings["auto_lock_minutes"] = value
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

    def set_max_versions(self, value: int):
        self.max_versions = value
        settings_path = Path(__file__).parent / "settings.json"
        settings = {}
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
        settings["max_versions"] = value
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)