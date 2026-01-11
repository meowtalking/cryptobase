# AddFileThread.py
import os
from PyQt5.QtCore import QThread, pyqtSignal
from app.services.file_manager import add_file

class AddFileThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, path, password_hash=None):
        super().__init__()
        self.path = os.path.abspath(path)
        self.password_hash = password_hash
        self._cancel_requested = False

    def run(self):
        try:
            if self._cancel_requested:
                self.finished.emit(False, "Операция отменена пользователем")
                return
            add_file(self.path, password_hash=self.password_hash)
            if self._cancel_requested:
                self.finished.emit(False, "Операция отменена пользователем")
                return
            self.finished.emit(True, f"Файл {os.path.basename(self.path)} добавлен")
        except Exception as e:
            self.finished.emit(False, str(e))

    def cancel(self):
        self._cancel_requested = True
