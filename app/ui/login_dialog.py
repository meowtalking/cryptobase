# app/ui/login_dialog.py
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton, QLabel, QMessageBox
# from app.services.firebase_auth import login, register
from requests.exceptions import HTTPError

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Вход в CryptoBase")
        self.setGeometry(400, 400, 300, 150)

        layout = QVBoxLayout()
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email")
        layout.addWidget(self.email_input)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Пароль")
        layout.addWidget(self.password_input)

        self.login_btn = QPushButton("Войти")
        self.login_btn.clicked.connect(self.handle_login)
        layout.addWidget(self.login_btn)

        self.register_btn = QPushButton("Регистрация")
        self.register_btn.clicked.connect(self.handle_register)
        layout.addWidget(self.register_btn)

        self.setLayout(layout)


    #
    # def handle_login(self):
    #     email = self.email_input.text()
    #     password = self.password_input.text()
    #     try:
    #         login(email, password)
    #         QMessageBox.information(self, "Успех", f"Вы вошли как {email}")
    #         self.accept()
    #     except HTTPError as e:
    #         QMessageBox.critical(self, "Ошибка", str(e))
    #
    # def handle_register(self):
    #     email = self.email_input.text()
    #     password = self.password_input.text()
    #     try:
    #         register(email, password)
    #         QMessageBox.information(self, "Успех", f"Пользователь {email} зарегистрирован")
    #         self.accept()
    #     except HTTPError as e:
    #         QMessageBox.critical(self, "Ошибка", str(e))
