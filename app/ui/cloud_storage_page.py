from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QMessageBox
from app.services import google_drive_service
import json

class CloudStoragePage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.setWindowTitle("CryptoBase — Облачное хранилище")
        self.setGeometry(100, 100, 900, 500)
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        back_btn = QPushButton("← Назад в меню")
        back_btn.clicked.connect(self.back_to_menu)
        layout.addWidget(back_btn)

        login_btn = QPushButton("Войти в Google Drive")
        login_btn.clicked.connect(self.google_login)
        layout.addWidget(login_btn)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Имя", "Путь", "Статус", "Алгоритм", "Последнее изменение"])
        layout.addWidget(self.table)

        self.setLayout(layout)

    def google_login(self):
        try:
            google_drive_service.get_drive_service()
            QMessageBox.information(self, "Успех", "Вы вошли в Google Drive")
            self.load_cloud_files()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось войти: {e}")

    def load_cloud_files(self):
        self.table.setRowCount(0)
        files = google_drive_service.list_files()
        for f in files:
            if not f["name"].endswith(".json"):
                continue
            try:
                content = google_drive_service.download_file(f["id"])
                data = json.loads(content)
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(data.get("name", f["name"])))
                self.table.setItem(row, 1, QTableWidgetItem(data.get("path", "")))
                self.table.setItem(row, 2, QTableWidgetItem(data.get("status", "")))
                self.table.setItem(row, 3, QTableWidgetItem(data.get("algorithm", "")))
                self.table.setItem(row, 4, QTableWidgetItem(f.get("modifiedTime", "")))
            except Exception as e:
                print(f"Ошибка чтения {f['name']}: {e}")

    def back_to_menu(self):
        self.main_window.navigate_to("menu")
