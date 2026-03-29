import os
from PyQt5.QtCore import QThread, pyqtSignal
from app.db import SessionLocal
from app.models import FileRecord, FileVersion, LogEntry
from app.services.backup_container import BackupContainer
from app.services.file_manager import now_msk


class DeleteFileThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, file_id: int, delete_original: bool = False, container=None):
        super().__init__()
        self.file_id = file_id
        self.delete_original = delete_original
        self.container = container  # готовый контейнер из главного потока
        self._cancel_requested = False

    def run(self):
        session = SessionLocal()
        try:
            if self._cancel_requested:
                self.finished.emit(False, "Удаление отменено пользователем")
                return

            # Загружаем file_record в новой сессии
            file_record = session.query(FileRecord).filter(FileRecord.id == self.file_id).first()
            if not file_record:
                self.finished.emit(False, "Файл не найден в БД")
                return

            file_name = file_record.name
            file_path = file_record.path

            if self._cancel_requested:
                self.finished.emit(False, "Удаление отменено пользователем")
                return

            # Удаление из контейнера (используем готовый)
            file_id_str = str(self.file_id)
            if file_id_str in self.container.data["files"]:
                del self.container.data["files"][file_id_str]
                self.container._save()
                print(f"[DELETE] Все версии удалены из контейнера для ID {file_id_str}")

            # Удаление из БД
            deleted_versions = session.query(FileVersion).filter(FileVersion.file_id == self.file_id).delete()
            session.delete(file_record)
            session.commit()
            print(f"[DELETE] Удалено {deleted_versions} версий из БД для ID {file_id_str}")

            # Удаление основного файла
            if self.delete_original and os.path.exists(file_path):
                os.remove(file_path)

            # Лог
            log_msg = f"Файл '{file_name}' удалён из приложения"
            if self.delete_original:
                log_msg += " + оригинальный файл с диска"
            session.add(LogEntry(
                action="delete_file",
                file_name=file_name,
                result=log_msg,
                user_name=os.getlogin(),
                timestamp=now_msk()
            ))

            session.commit()
            self.finished.emit(True, f"Файл {file_name} успешно удалён")

        except Exception as e:
            session.rollback()
            self.finished.emit(False, f"Ошибка удаления: {str(e)}")
        finally:
            session.close()

    def cancel(self):
        self._cancel_requested = True


