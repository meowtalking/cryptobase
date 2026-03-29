# AddFileThread.py
import os
from PyQt5.QtCore import QThread, pyqtSignal
from app.services.file_manager import add_file_new

class AddFileThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, path, password=None, master_key=None):
        super().__init__()
        self.path = os.path.abspath(path)
        self.password = password  # plaintext или None
        self.master_key = master_key
        self._cancel_requested = False

    def run(self):
        try:
            if self._cancel_requested:
                self.finished.emit(False, "Операция отменена пользователем")
                return

            # Передаём plaintext пароль
            add_file_new(
                self.path,
                password=self.password,     # ← plaintext!
                master_key=self.master_key
            )

            if self._cancel_requested:
                self.finished.emit(False, "Операция отменена пользователем")
                return

            self.finished.emit(True, f"Файл {os.path.basename(self.path)} добавлен")

        except Exception as e:
            self.finished.emit(False, str(e))

    def cancel(self):
        self._cancel_requested = True