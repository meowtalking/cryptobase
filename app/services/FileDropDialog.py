import os
from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QDialog, QPushButton,
    QHBoxLayout, QFileDialog, QMessageBox, QInputDialog
)
from PyQt5.QtCore import Qt
from app.services.security import encrypt_file, hash_password_for_db
from app.services import AddFileThread  # если поток добавления определён отдельно


class FileDropDialog(QDialog):
    """Окно для перетаскивания файла (Drag & Drop) или выбора вручную"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление файла")
        self.setGeometry(300, 300, 400, 250)
        self.setAcceptDrops(True)
        self.file_path = None
        self.current_add_thread = None

        layout = QVBoxLayout()

        # === Метка области перетаскивания ===
        self.label = QLabel("Перетащите файл сюда\nили выберите вручную")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 14))
        self.label.setStyleSheet(
            "QLabel { border: 3px dashed #00c853; color: #aaa; padding: 40px; }"
        )
        layout.addWidget(self.label)

        # === Кнопка выбора файла через Finder / Проводник ===
        self.choose_btn = QPushButton("Выбрать файл…")
        self.choose_btn.clicked.connect(self.choose_file)
        layout.addWidget(self.choose_btn, alignment=Qt.AlignCenter)

        # === Кнопки управления ===
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self.reject)

        self.next_btn = QPushButton("Далее")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.next_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    # ====== Drag & Drop ======
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.label.setStyleSheet(
                "QLabel { border: 3px dashed #00c853; background-color: #1b1b1b; color: white; padding: 40px; }"
            )
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.label.setStyleSheet(
            "QLabel { border: 3px dashed #00c853; color: #aaa; padding: 40px; }"
        )

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    self.file_path = path
                    self.label.setText(f"Файл готов к добавлению:\n{os.path.basename(path)}")
                    self.next_btn.setEnabled(True)
                    break
        self.label.setStyleSheet(
            "QLabel { border: 3px dashed #00c853; color: #aaa; padding: 40px; }"
        )

    # ====== Новый метод: выбор файла вручную ======
    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите файл", os.path.expanduser("~"))
        if path and os.path.isfile(path):
            self.file_path = path
            self.label.setText(f"Файл выбран:\n{os.path.basename(path)}")
            self.next_btn.setEnabled(True)

    # ====== Добавление файла (как раньше) ======
    def add_file_dialog(self):
        dialog = FileDropDialog(self)
        if dialog.exec_() != QDialog.Accepted or not dialog.file_path:
            return

        path = os.path.abspath(dialog.file_path)
        password_hash = None

        password, ok = QInputDialog.getText(
            self, "Пароль", "Введите пароль для защиты (оставьте пустым если не нужен):"
        )
        if ok and password:
            password_hash = hash_password_for_db(password)
            try:
                encrypt_file(path, password)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось зашифровать файл: {e}")
                return

        # Сохраняем поток как атрибут, чтобы GC не уничтожил его
        self.current_add_thread = AddFileThread(path, password_hash)
        self.current_add_thread.finished.connect(
            lambda success, msg: (
                QMessageBox.information(self, "Результат", msg)
                if success else QMessageBox.critical(self, "Ошибка", msg),
                self.load_files()
            )
        )
        self.current_add_thread.start()

    def add_file_from_path(self, path: str):
        path = os.path.abspath(path)
        password_hash = None

        password, ok = QInputDialog.getText(
            self, "Пароль", "Введите пароль для защиты (оставьте пустым если не нужен):"
        )
        if ok and password:
            password_hash = hash_password_for_db(password)
            try:
                encrypt_file(path, password)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось зашифровать файл: {e}")
                return

        self.current_add_thread = AddFileThread(path, password_hash)
        self.current_add_thread.finished.connect(
            lambda success, msg: (
                QMessageBox.information(self, "Результат", msg)
                if success else QMessageBox.critical(self, "Ошибка", msg),
                self.load_files()
            )
        )
        self.current_add_thread.start()
