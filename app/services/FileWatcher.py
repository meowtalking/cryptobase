import os
import time
import threading
from datetime import datetime
from app.db import SessionLocal
from app.models import FileRecord, FileVersion, LogEntry
from app.services.AutoBackupManager import AutoBackupManager
from app.services.file_manager import compute_hash
from PyQt5.QtCore import QObject, pyqtSignal
from app.services.integrity_manager import now_msk


class FileWatcher(QObject):
    update_signal = pyqtSignal()  # сигнал для MainWindow

    def __init__(self, main_window=None, interval: int = 10, max_versions: int = 5):
        super().__init__()
        self.main_window = main_window
        self.interval = interval
        self.running = False
        self.max_versions = max_versions
        self.backup_manager = AutoBackupManager("/Users/macbook/PycharmProjects/cryptobase/config.json")
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        if self.main_window:
            self.update_signal.connect(self.main_window.load_files)

    def start(self):
        if not self.running:
            self.running = True
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=3)

    def _watch_loop(self):
        while self.running:
            session = SessionLocal()
            try:
                for file_record in session.query(FileRecord).all():
                    abs_path = os.path.abspath(file_record.path)

                    # === 1️⃣ Файл отсутствует ===
                    if not os.path.exists(abs_path):
                        if file_record.status != "Missing":
                            file_record.status = "Missing"
                            session.commit()
                            session.add(LogEntry(
                                action="file_missing",
                                file_name=file_record.name,
                                result="File not found",
                                user_name=os.getlogin(),
                                timestamp=datetime.utcnow()
                            ))
                            session.commit()
                        continue

                    # === 2️⃣ Проверка хэша ===
                    new_hash = compute_hash(abs_path)

                    last_hash = file_record.current_hash

                    # === 3️⃣ Если файл изменился ===
                    if new_hash != last_hash:
                        file_record.current_hash = new_hash
                        file_record.updated_at = datetime.utcnow()
                        file_record.status = "Modified"
                        session.commit()

                        # Создаём БЭКАП (и он же создаёт FileVersion)
                        try:
                            self.backup_manager.create_backup(file_record)
                            print(f"[BACKUP] Создан бэкап для {file_record.name}")
                        except Exception as err:
                            print(f"[BACKUP ERROR] Не удалось создать бэкап: {err}")

                        # Логируем
                        session.add(LogEntry(
                            action="file_changed",
                            file_name=file_record.name,
                            result="Modified",
                            user_name=os.getlogin(),
                            timestamp=now_msk()
                        ))
                        session.commit()

                        # Сигнал интерфейсу
                if self.main_window:
                         self.update_signal.emit()


            except Exception as e:
                print(f"[Ошибка FileWatcher]: {e}")
            finally:
                session.close()

            time.sleep(self.interval)
