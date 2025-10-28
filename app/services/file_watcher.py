import os
import time
import threading
from datetime import datetime
from app.db import SessionLocal
from app.models import FileRecord, FileVersion, LogEntry
from app.services.auto_backup_manager import AutoBackupManager
from app.services.file_manager import compute_hash  # твоя функция хеширования
from PyQt5.QtCore import QObject, pyqtSignal


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
        self.running = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()

    def _watch_loop(self):
        while self.running:
            session = SessionLocal()
            try:
                files = session.query(FileRecord).all()
                for file in files:
                    if not os.path.exists(file.path):
                        # Если файл пропал — обновим статус
                        if file.status != "Missing":
                            file.status = "Missing"
                            session.commit()

                            log = LogEntry(
                                action="file_missing",
                                file_name=file.name,
                                result="File not found",
                                user_name=os.getlogin()
                            )
                            session.add(log)
                            session.commit()
                        continue

                    new_hash = compute_hash(file.path, file.algorithm)

                    # Берём последнюю версию
                    last_version = session.query(FileVersion) \
                        .filter(FileVersion.file_id == file.id) \
                        .order_by(FileVersion.created_at.desc()) \
                        .first()
                    last_hash = last_version.version_hash if last_version else None

                    # Только если хэш реально новый
                    if new_hash != last_hash:
                        # Обновляем статус и хэш
                        file.current_hash = new_hash
                        file.updated_at = datetime.utcnow()
                        file.status = "Modified"
                        session.commit()

                        # Создаём резервную копию
                        backup_path = self.backup_manager.create_backup(file.path, file.id)

                        # Создаём новую версию
                        version = FileVersion(
                            file_id=file.id,
                            version_hash=new_hash,
                            created_at=datetime.utcnow(),
                            comment="Изменение обнаружено системой",
                            location="local"
                        )
                        session.add(version)
                        session.commit()

                        # Ограничиваем количество версий
                        versions = session.query(FileVersion) \
                            .filter(FileVersion.file_id == file.id) \
                            .order_by(FileVersion.created_at.desc()) \
                            .all()
                        for old_version in versions[self.max_versions:]:
                            old_backup_name = f"{old_version.file_id}_{old_version.created_at.strftime('%Y%m%d%H%M%S')}_{os.path.basename(file.path)}"
                            old_backup_path = self.backup_manager.local_backup / old_backup_name
                            if old_backup_path.exists():
                                old_backup_path.unlink()
                            session.delete(old_version)
                        session.commit()

                        # Логируем изменение
                        log = LogEntry(
                            action="file_changed",
                            file_name=file.name,
                            result="Modified",
                            user_name=os.getlogin(),
                            timestamp=datetime.utcnow()
                        )
                        session.add(log)
                        session.commit()

                # Обновляем GUI
                if self.main_window:
                    self.update_signal.emit()

            except Exception as e:
                print(f"[Ошибка FileWatcher]: {e}")
            finally:
                session.close()

            time.sleep(self.interval)
