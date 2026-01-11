import glob

from PyQt5.QtWidgets import (
    QVBoxLayout, QInputDialog, QMessageBox, QLabel, QDialog, QPushButton, QFileDialog, QLineEdit
)
import os, platform, subprocess, tempfile, shutil
from datetime import datetime
from app.models import FileRecord, FileVersion, LogEntry
from app.db import SessionLocal
from app.services.security import hash_password_for_db, verify_password_for_db, encrypt_file, decrypt_file
from app.services.integrity_manager import compute_hash, now_msk, MOSCOW_TZ
from app.services.AutoBackupManager import AutoBackupManager
from PyQt5.QtCore import QProcess, QTimer
db = SessionLocal()

class FileEditDialog(QDialog):
    """Редактирование файла + открытие зашифрованных бэкапов"""

    def __init__(self, db, file_record: FileRecord, parent=None):
        super().__init__(parent)
        self.db = db
        self.file_record = file_record
        self.backup_mgr = AutoBackupManager("config.json")

        self.setWindowTitle(f"Файл: {file_record.name}")
        self.setGeometry(400, 400, 400, 300)
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Файл: {file_record.name}"))

        # Кнопки
        btn_edit = QPushButton("Редактировать содержимое")
        btn_edit.clicked.connect(self.edit_file_content)
        layout.addWidget(btn_edit)

        btn_password = QPushButton("Сменить пароль")
        btn_password.clicked.connect(self.change_password)
        layout.addWidget(btn_password)

        btn_delete_version = QPushButton("Удалить версию")
        btn_delete_version.clicked.connect(self.delete_version)
        layout.addWidget(btn_delete_version)

        btn_delete = QPushButton("Удалить файл")
        btn_delete.clicked.connect(self.delete_file)
        layout.addWidget(btn_delete)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self.setLayout(layout)

    def delete_version(self):
        try:
            file_record = self.file_record
            file_id = file_record.id
            file_name = file_record.name

            # Загружаем версии
            versions = (
                self.db.query(FileVersion)
                .filter(FileVersion.file_id == file_id)
                .order_by(FileVersion.created_at.desc())
                .all()
            )
            if not versions:
                QMessageBox.information(self, "Информация", "Нет доступных версий для удаления")
                return

            # Выбор версии
            items = [
                f"{v.created_at.astimezone(MOSCOW_TZ).strftime('%Y-%m-%d %H:%M:%S')} | {v.comment or ''}"
                for v in versions
            ]
            item, ok = QInputDialog.getItem(
                self, "Удалить версию", "Выберите версию для удаления:", items, editable=False
            )
            if not (ok and item):
                return

            version_index = items.index(item)
            version = versions[version_index]

            # --- Проверка пароля для зашифрованного файла ---
            password = None
            if file_record.password_hash:
                password, ok = QInputDialog.getText(
                    self,
                    "Подтверждение",
                    "Файл зашифрован. Введите пароль для удаления версии:",
                    QLineEdit.Password
                )
                if not ok or not password or not verify_password_for_db(password, file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return

            # --- Подтверждение удаления ---
            confirm = QMessageBox.question(
                self,
                "Удаление версии",
                f"Удалить выбранную версию файла {file_name}?\n"
                f"Дата версии: {version.created_at.astimezone(MOSCOW_TZ).strftime('%Y-%m-%d %H:%M:%S')}",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

            # --- Путь к бэкапу ---
            backup_root = "/Users/macbook/backups"
            timestamp_str = version.created_at.astimezone(MOSCOW_TZ).strftime("%Y%m%d%H%M%S")
            filename = os.path.basename(file_record.path)
            backup_path = os.path.join(backup_root, f"{file_id}_{timestamp_str}_{filename}")

            # --- Удаляем файл с диска ---
            if os.path.exists(backup_path):
                os.remove(backup_path)

            # --- Удаляем запись в БД ---
            self.db.delete(version)

            # --- Добавляем запись в логи ---
            log = LogEntry(
                action="delete_version",
                file_name=file_name,
                result=f"Версия {timestamp_str} удалена",
                user_name=os.getlogin()
            )
            self.db.add(log)

            self.db.commit()
            QMessageBox.information(self, "Готово", "Версия удалена успешно")

        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить версию:\n{e}")

    # === Редактирование файла ===
    def edit_file_content(self):
        try:
            was_encrypted = bool(self.file_record.password_hash)
            password = None

            # === Проверка пароля ===
            if was_encrypted:
                password, ok = QInputDialog.getText(
                    self, "Введите пароль", "Файл зашифрован. Введите пароль:"
                )
                if not ok or not password or not verify_password_for_db(password, self.file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return

            # === Временный файл для расшифрованной версии ===
            if was_encrypted:
                data = decrypt_file(self.file_record.path, password)
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(self.file_record.path)[1])
                tmp.write(data)
                tmp.close()
                temp_path = tmp.name
            else:
                temp_path = self.file_record.path

            # === Создание бэкапа ===
            backup_path = self.backup_mgr.create_backup(self.file_record, password if was_encrypted else None)

            before_hash = compute_hash(temp_path)

            # === Открываем редактор без ожидания закрытия ===
            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", temp_path])
            elif system == "Windows":
                os.startfile(temp_path)
            else:
                subprocess.Popen(["xdg-open", temp_path])

            # === Спрашиваем пользователя вручную ===
            QMessageBox.information(self, "Редактирование", "Сохраните файл и нажмите OK.")
            ok = QMessageBox.question(self, "Подтверждение",
                                      "Вы сохранили изменения?",
                                      QMessageBox.Yes | QMessageBox.No)

            if ok != QMessageBox.Yes:
                if was_encrypted:
                    os.remove(temp_path)
                return

            # === Проверка изменений ===
            after_hash = compute_hash(temp_path)
            if before_hash == after_hash:
                QMessageBox.information(self, "Без изменений", "Файл не изменился.")
                if was_encrypted:
                    os.remove(temp_path)
                return

            # === Сохранение изменений ===
            with open(temp_path, "rb") as f:
                data = f.read()

            if was_encrypted:
                with open(self.file_record.path, "wb") as f:
                    f.write(data)
                encrypt_file(self.file_record.path, password)
                os.remove(temp_path)
            else:
                with open(self.file_record.path, "wb") as f:
                    f.write(data)

            # === Обновление хэша в БД ===
            self.file_record.current_hash = compute_hash(self.file_record.path)
            self.db.commit()

            QMessageBox.information(self, "Успех", "Изменения сохранены.")

            # === Создание версии в БД ===
            if backup_path and backup_path.exists():
                version = FileVersion(
                    file_id=self.file_record.id,
                    version_hash=compute_hash(backup_path),
                    created_at=now_msk(),
                    comment="Бэкап перед редактированием",
                    location=str(backup_path)
                )
                self.db.add(version)
                self.db.commit()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Редактирование не удалось:\n{e}")

    def _after_edit(self, temp_path, before_hash, password, was_encrypted):
        after_hash = compute_hash(temp_path)

        if before_hash == after_hash:
            QMessageBox.information(self, "Без изменений", "Файл не изменился. Бэкап не создан.")
            if was_encrypted:
                os.remove(temp_path)
            return

        # === Сохраняем изменения ===
        with open(temp_path, "rb") as f:
            data = f.read()

        if was_encrypted:
            with open(self.file_record.path, "wb") as f:
                f.write(data)
            encrypt_file(self.file_record.path, password)
            os.remove(temp_path)
        else:
            with open(self.file_record.path, "wb") as f:
                f.write(data)

        self.file_record.current_hash = compute_hash(self.file_record.path)
        self.db.commit()

        # === Создаём бэкап ===
        backup_path = self.backup_mgr.create_backup(self.file_record, password if was_encrypted else None)
        if backup_path and os.path.exists(backup_path):
            version = FileVersion(
                file_id=self.file_record.id,
                version_hash=compute_hash(backup_path),
                created_at=now_msk(),
                comment="Бэкап перед редактированием",
                location=str(backup_path)
            )
            self.db.add(version)
            self.db.commit()

        QMessageBox.information(self, "Успех", "Изменения сохранены и бэкап создан.")


    # === Смена пароля ===
    def change_password(self):
        try:
            old_password = None
            if self.file_record.password_hash:
                old_password, ok = QInputDialog.getText(self, "Старый пароль", "Введите текущий пароль:")
                if not ok or not verify_password_for_db(old_password, self.file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return

            new_password, ok = QInputDialog.getText(self, "Новый пароль",
                                                    "Введите новый пароль (оставьте пустым для снятия):")
            if not ok: return

            # Перешифровка существующего файла
            if old_password:
                data = decrypt_file(self.file_record.path, old_password)
                with open(self.file_record.path, "wb") as f: f.write(data)

            backup_root = "/Users/macbook/backups"
            file_id = self.file_record.id
            filename = os.path.basename(self.file_record.path)
            for backup_path in sorted(glob.glob(os.path.join(backup_root, f"{file_id}_*_{filename}"))):
                # дешифруем старый бэкап
                if old_password:
                    data = decrypt_file(backup_path, old_password)
                    with open(backup_path, "wb") as f: f.write(data)
                # шифруем новым паролем
                if new_password:
                    encrypt_file(backup_path, new_password)
                # обновляем хэш в БД
                version = self.db.query(FileVersion).filter(
                    FileVersion.file_id == file_id,
                    FileVersion.location == str(backup_path)
                ).first()
                if version:
                    version.version_hash = compute_hash(backup_path)

            self.db.commit()

            # Перешифровка самого файла
            if new_password:
                encrypt_file(self.file_record.path, new_password)
                self.file_record.password_hash = hash_password_for_db(new_password)
            else:
                self.file_record.password_hash = None

            self.file_record.current_hash = compute_hash(self.file_record.path)
            self.db.commit()
            QMessageBox.information(self, "Успех", "Пароль обновлён.")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось изменить пароль:\n{e}")

    # === Удаление файла ===
    def delete_file(self):
        try:
            password = None

            # === 1. Проверка пароля для зашифрованного файла ===
            if self.file_record.password_hash:
                password, ok = QInputDialog.getText(
                    self,
                    "Подтверждение",
                    "Файл зашифрован. Введите пароль:",
                    QLineEdit.Password
                )
                if (
                        not ok
                        or not password
                        or not verify_password_for_db(password, self.file_record.password_hash)
                ):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return

            # === 2. Основной выбор ===
            choice = QMessageBox.question(
                self,
                "Удаление файла",
                "Удалить файл полностью?\n\n"
                "Да — удалить файл, все бэкапы и данные\n"
                "Нет — удалить только из приложения",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if choice == QMessageBox.Cancel:
                return

            delete_original = (choice == QMessageBox.Yes)

            # === Пути ===
            backup_root = "/Users/macbook/backups"
            file_id = self.file_record.id
            file_name = self.file_record.name
            file_path = self.file_record.path
            filename_only = os.path.basename(file_path)

            backup_files = glob.glob(
                os.path.join(backup_root, f"{file_id}_*_{filename_only}")
            )

            # === 3. Если удаляем только из приложения ===
            if not delete_original:
                restore = QMessageBox.question(
                    self,
                    "Восстановление версий",
                    "Восстановить все сохранённые версии файла перед удалением?",
                    QMessageBox.Yes | QMessageBox.No
                )

                if restore == QMessageBox.Yes:
                    restore_dir = QFileDialog.getExistingDirectory(
                        self, "Куда восстановить версии?"
                    )
                    if not restore_dir:
                        return

                    for bp in backup_files:
                        # Из имени бэкапа достаём timestamp и оригинальное имя
                        parts = os.path.basename(bp).split("_", 2)
                        timestamp_part = parts[1] if len(parts) > 2 else datetime.now().strftime("%Y%m%d%H%M%S")
                        orig_name = parts[2] if len(parts) > 2 else filename_only

                        # Формируем уникальное имя для восстановления
                        out_name = f"{timestamp_part}_{orig_name}"
                        out_path = os.path.join(restore_dir, out_name)

                        try:
                            if password:
                                # Расшифровка версии
                                data = decrypt_file(bp, password)
                                with open(out_path, "wb") as f:
                                    f.write(data)
                            else:
                                # Копирование без расшифровки
                                shutil.copy2(bp, out_path)
                        except Exception as e:
                            QMessageBox.warning(
                                self,
                                "Ошибка восстановления",
                                f"Не удалось восстановить {os.path.basename(bp)}:\n{e}"
                            )

            # === 4. Удаление оригинального файла (если выбрано) ===
            if delete_original and os.path.exists(file_path):
                os.remove(file_path)

            # === 5. УДАЛЯЕМ БЭКАПЫ В ЛЮБОМ СЛУЧАЕ ===
            for bp in backup_files:
                if os.path.exists(bp):
                    os.remove(bp)

            # === 6. Чистим БД ===
            # версии (можно и не делать — cascade, но оставляем явно)
            self.db.query(FileVersion).filter(
                FileVersion.file_id == file_id
            ).delete()

            # логи — ТОЛЬКО ПО ИМЕНИ ФАЙЛА
            self.db.query(LogEntry).filter(
                LogEntry.file_name == file_name
            ).delete()

            # сам файл
            self.db.delete(self.file_record)
            self.db.commit()

            QMessageBox.information(
                self,
                "Готово",
                "Файл удалён корректно."
            )
            self.accept()

        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось удалить файл:\n{e}"
            )

