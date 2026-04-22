import sys
from PyQt5.QtWidgets import QApplication

from app.db import BACKUPS_PATH
from app.ui.main_window import MainWindow

import os
import subprocess
from pathlib import Path

def setup_secure_folder():
    folder = BACKUPS_PATH / ".cryptobase"
    try:
        # Создаём папку, если её нет
        folder.mkdir(parents=True, exist_ok=True)

        # Права 700 на папку (только владелец может заходить)
        if folder.stat().st_mode & 0o777 != 0o700:
            subprocess.run(["chmod", "700", str(folder)], check=True)

        # Права 600 на все файлы внутри
        changed = False
        for file in folder.glob("*"):
            if file.stat().st_mode & 0o777 != 0o600:
                subprocess.run(["chmod", "600", str(file)], check=True)
                changed = True

        if changed or not list(folder.iterdir()):
            print("[SECURE] Папка ~/.cryptobase защищена: права 700/600 установлены")
    except subprocess.CalledProcessError as e:
        print(f"[SECURE WARNING] Не удалось установить права: {e}")
    except Exception as e:
        print(f"[SECURE ERROR] Ошибка настройки безопасности: {e}")


# Вызываем при запуске приложения
setup_secure_folder()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
