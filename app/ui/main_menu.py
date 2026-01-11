from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QSizePolicy
from app.ui.local_storage_page import LocalStoragePage as LocalStorageWindow
from app.ui.cloud_storage_page import CloudStoragePage as CloudStorageWindow
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel

class MainMenuWindow(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setWindowTitle("CryptoBase — Главное меню")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        label = QLabel("Выберите режим работы:")
        layout.addWidget(label)

        # Кнопка — локальное хранилище
        local_btn = QPushButton("Локальное хранилище")
        local_btn.clicked.connect(lambda: self.main_window.navigate_to("local"))
        layout.addWidget(local_btn)
        # Кнопка — облачное хранилище
        cloud_btn = QPushButton("Облачное хранилище (Google Drive)")
        cloud_btn.clicked.connect(lambda: self.main_window.navigate_to("cloud"))
        layout.addWidget(cloud_btn)

        layout.addStretch()
        self.setLayout(layout)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.adjustSize()

    def open_local_storage(self):
        self.local_window = LocalStorageWindow(parent=self)
        self.local_window.show()
        self.hide()

    def open_cloud_storage(self):
        self.cloud_window = CloudStorageWindow(parent=self)
        self.cloud_window.show()
        self.hide()
