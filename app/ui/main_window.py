from PyQt5.QtWidgets import QMainWindow, QStackedWidget, QWidget, QVBoxLayout
from app.ui.main_menu import MainMenuWindow
from app.ui.local_storage_page import LocalStoragePage
from app.ui.cloud_storage_page import CloudStoragePage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CryptoBase Navigator")

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        # создаём страницы
        self.menu_page = MainMenuWindow(main_window=self)
        self.local_page = LocalStoragePage(main_window=self)
        self.cloud_page = CloudStoragePage(main_window=self)

        # добавляем их в стек
        self.stack.addWidget(self.menu_page)
        self.stack.addWidget(self.local_page)
        self.stack.addWidget(self.cloud_page)

        # стартовое меню
        self.navigate_to("menu")

    def navigate_to(self, page_name: str):
        if page_name == "menu":
            self.stack.setCurrentWidget(self.menu_page)
            # явно фиксируем размер окна под меню
            self.setFixedSize(300, 130)  # подбираешь под кнопки

        elif page_name == "local":
            self.stack.setCurrentWidget(self.local_page)
            self.setFixedSize(1000, 600)

        elif page_name == "cloud":
            self.stack.setCurrentWidget(self.cloud_page)
            self.setFixedSize(1000, 600)


