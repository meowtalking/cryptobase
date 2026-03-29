import os
import platform
import subprocess
import tempfile
import time
from datetime import datetime

from PyQt5.QtWidgets import (
    QVBoxLayout, QInputDialog, QLineEdit, QMessageBox, QLabel, QDialog, QPushButton, QLineEdit, QFileDialog, QProgressDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, Qt

from app.models import FileRecord, FileVersion, LogEntry
from app.db import SessionLocal
from app.services.file_manager import now_msk
from app.services.security import (
    hash_password_for_db, verify_password_for_db, encrypt_file, decrypt_file, decrypt_file_from_bytes
)
from app.services.integrity_manager import compute_hash, MOSCOW_TZ
from app.services.backup_container import BackupContainer  # ← основной импорт для контейнера
from app.services.DeleteFileThread import DeleteFileThread

db = SessionLocal()

class FileEditDialog(QDialog):
    """Редактирование файла + управление версиями в контейнере backups.enc"""

    def __init__(self, db, file_record: FileRecord, parent=None, master_key=None):
        super().__init__(parent)
        self.db = db
        self.file_record = file_record
        self.master_key = master_key


        self.setWindowTitle(f"Файл: {file_record.name}")
        self.setGeometry(400, 400, 400, 300)
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Файл: {file_record.name}"))

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
            file_id = self.file_record.id
            file_name = self.file_record.name

            # Получаем контейнер
            container = BackupContainer(self.master_key) # master_key из MainWindow

            versions_data = container.get_all_versions(str(file_id))
            if not versions_data:
                QMessageBox.information(self, "Информация", "Нет доступных версий в контейнере")
                return

            # Сортировка по дате (от новых к старым)
            versions_data.sort(key=lambda v: datetime.fromisoformat(v["created_at"]), reverse=True)

            # Список для выбора
            items = []
            for v in versions_data:
                dt = datetime.fromisoformat(v["created_at"])
                items.append(f"{dt.strftime('%Y-%m-%d %H:%M:%S')} | {v.get('comment', '')}")

            item, ok = QInputDialog.getItem(
                self, "Удалить версию", "Выберите версию:", items, editable=False
            )
            if not (ok and item):
                return

            version_index = items.index(item)
            selected_version = versions_data[version_index]

            # Проверка пароля, если файл зашифрован
            password = None
            if self.file_record.password_hash:
                password, ok = QInputDialog.getText(
                    self, "Подтверждение", "Введите пароль для удаления версии:", QLineEdit.Password
                )
                if not ok or not password or not verify_password_for_db(password, self.file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return

            # Подтверждение
            confirm = QMessageBox.question(
                self,
                "Удаление версии",
                f"Удалить версию от {selected_version['created_at']}?\nКомментарий: {selected_version.get('comment', '')}",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm != QMessageBox.Yes:
                return

            # Запускаем асинхронное удаление с прогресс-баром
            self._start_version_deleting_process(container, selected_version, password)

        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить версию:\n{e}")

    def _start_version_deleting_process(self, container, selected_version, password=None):
        """Запускает процесс удаления версии с прогресс-баром и поддержкой отмены"""
        progress = QProgressDialog("Удаление версии...", "Отмена", 0, 100, self)
        progress.setWindowTitle("Удаление версии")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        class VersionDeleteWorker(QThread):
            progress_updated = pyqtSignal(int, str)
            finished = pyqtSignal(bool, str)

            def __init__(self, container, selected_version, file_id, file_name, password=None):
                super().__init__()
                self.container = container
                self.selected_version = selected_version
                self.file_id = file_id
                self.file_name = file_name
                self.password = password
                self._is_cancelled = False

            def cancel(self):
                self._is_cancelled = True

            def run(self):
                try:
                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем")
                        return

                    self.progress_updated.emit(10, "Подготовка к удалению...")
                    
                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем")
                        return

                    self.progress_updated.emit(30, "Удаление из контейнера...")
                    
                    # Удаляем версию из контейнера
                    versions_data = self.container.get_all_versions(str(self.file_id))
                    versions_data.sort(key=lambda v: datetime.fromisoformat(v["created_at"]), reverse=True)
                    
                    # Находим индекс версии для удаления
                    version_to_delete = None
                    for i, v in enumerate(versions_data):
                        if v["created_at"] == self.selected_version["created_at"]:
                            version_to_delete = i
                            break
                    
                    if version_to_delete is not None:
                        del versions_data[version_to_delete]
                        if versions_data:
                            self.container.data["files"][str(self.file_id)] = versions_data
                        else:
                            if str(self.file_id) in self.container.data["files"]:
                                del self.container.data["files"][str(self.file_id)]
                        self.container._save()

                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем")
                        return

                    self.progress_updated.emit(60, "Удаление из БД...")
                    
                    # Удаляем запись из БД
                    db_session = SessionLocal()
                    try:
                        db_version = db_session.query(FileVersion).filter(
                            FileVersion.file_id == self.file_id,
                            FileVersion.created_at == datetime.fromisoformat(self.selected_version["created_at"])
                        ).first()
                        if db_version:
                            db_session.delete(db_version)
                            db_session.commit()
                        
                        # Лог
                        log = LogEntry(
                            action="delete_version",
                            file_name=self.file_name,
                            result=f"Версия {self.selected_version['created_at']} удалена из контейнера и БД",
                            user_name=os.getlogin(),
                            timestamp=now_msk()
                        )
                        db_session.add(log)
                        db_session.commit()
                        
                    finally:
                        db_session.close()

                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем")
                        return

                    self.progress_updated.emit(100, "Готово!")
                    self.finished.emit(True, "Версия удалена из контейнера")
                    
                except Exception as e:
                    self.finished.emit(False, f"Ошибка удаления версии: {str(e)}")

        worker = VersionDeleteWorker(
            container, selected_version, self.file_record.id, self.file_record.name, password
        )
        self._current_worker = worker
        self._current_progress = progress

        @pyqtSlot(int, str)
        def update_progress(value, text):
            if not progress.wasCanceled():
                progress.setValue(value)
                progress.setLabelText(text)

        @pyqtSlot(bool, str)
        def on_operation_finished(success, message):
            progress.close()
            self._current_worker = None
            self._current_progress = None
            self._on_version_deleted(success, message)

        worker.progress_updated.connect(update_progress)
        worker.finished.connect(on_operation_finished)
        progress.canceled.connect(worker.cancel)
        progress.destroyed.connect(self._cleanup_worker)
        worker.start()

    def _on_version_deleted(self, success, message):
        """Обработка результата удаления версии"""
        if success:
            QMessageBox.information(self, "Готово", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)

    def edit_file_content(self):
        try:
            was_encrypted = bool(self.file_record.password_hash)

            # Запрещаем редактирование незашифрованных файлов
            if not was_encrypted:
                QMessageBox.warning(
                    self,
                    "Запрещено",
                    "Редактирование незашифрованных файлов через приложение запрещено.\n\n"
                    "Откройте файл обычным способом через Finder/Explorer."
                )
                return

            password, ok = QInputDialog.getText(
                self, "Пароль", "Файл зашифрован. Введите пароль:", QLineEdit.Password
            )
            if not ok or not password or not verify_password_for_db(password, self.file_record.password_hash):
                QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                return

            # Подготовка временного файла
            data = decrypt_file(self.file_record.path, password)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(self.file_record.path)[1])
            tmp.write(data)
            tmp.close()
            edit_path = tmp.name

            before_hash = compute_hash(edit_path)

            # Открываем редактор
            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", edit_path])
            elif system == "Windows":
                os.startfile(edit_path)
            else:
                subprocess.Popen(["xdg-open", edit_path])

            QMessageBox.information(self, "Редактирование",
                                    "Отредактируйте и сохраните файл.\nКогда закончите — нажмите OK.")

            # СРАЗУ закрываем временный файл после нажатия OK
            try:
                after_hash = compute_hash(edit_path)
            except Exception as e:
                print(f"[EDIT ERROR] Не удалось прочитать временный файл: {e}")
                QMessageBox.critical(self, "Ошибка", "Не удалось прочитать временный файл. Возможно, он все еще открыт в редакторе.")
                try:
                    os.unlink(edit_path)
                except:
                    pass
                return

            if before_hash == after_hash:
                QMessageBox.information(self, "Без изменений", "Файл не изменился.")
                try:
                    os.unlink(edit_path)
                except:
                    pass
                return

            # Сохраняем изменения
            with open(edit_path, "rb") as f:
                new_content = f.read()

            # СРАЗУ удаляем временный файл
            try:
                os.unlink(edit_path)
            except:
                pass

            # Записываем новый контент в оригинальный файл (plaintext)
            with open(self.file_record.path, "wb") as f:
                f.write(new_content)

            # Шифруем оригинальный файл (теперь plaintext → encrypted)
            encrypt_file(self.file_record.path, password)

            time.sleep(1.5)  # даём ОС время

            # Обновляем хэш
            self.file_record.current_hash = compute_hash(self.file_record.path)
            self.db.commit()

            # Принудительно создаём новую версию в контейнере и БД
            try:
                container = BackupContainer(self.master_key)
                file_id_str = str(self.file_record.id)

                version_data = {
                    "version_id": len(container.get_all_versions(file_id_str)) + 1,
                    "created_at": now_msk().isoformat(),
                    "hash": self.file_record.current_hash,
                    "comment": "Редактирование через диалог",
                    "content": new_content.hex()  # Сохраняем plaintext для консистентности
                }

                container.add_version(file_id_str, version_data)
                container._save()
                print("[EDIT] Принудительная версия добавлена в контейнер")

                # Добавляем запись в FileVersion
                new_version = FileVersion(
                    file_id=self.file_record.id,
                    version_hash=self.file_record.current_hash,
                    created_at=now_msk(),
                    comment=version_data["comment"],
                    location="container:backups.enc"
                )
                self.db.add(new_version)
                self.db.commit()
                print("[EDIT] Новая версия добавлена в БД")

            except Exception as e:
                print(f"[EDIT BACKUP ERROR] {e}")

            # Обрезка версий (только после гарантированного добавления)
            try:
                container = BackupContainer(self.master_key)
                all_versions = container.get_all_versions(file_id_str)

                print(f"[DEBUG] Версий перед обрезкой: {len(all_versions)}")

                max_versions = self.parent().get_max_versions()
                if len(all_versions) > max_versions:
                    # Если достигнут лимит, обрезаем старые версии (включая initial)
                    # Сортируем от новых к старым
                    all_versions.sort(key=lambda v: datetime.fromisoformat(v["created_at"]), reverse=True)
                    container.data["files"][file_id_str] = all_versions[:max_versions]
                    container._save()
                    print(f"[EDIT CLEANUP] Достигнут лимит {max_versions} - обрезка старых версий")

                # Обрезка БД
                db_versions = (
                    self.db.query(FileVersion)
                    .filter(FileVersion.file_id == self.file_record.id)
                    .order_by(FileVersion.created_at.desc())
                    .all()
                )

                if len(db_versions) > max_versions:
                    to_delete = db_versions[max_versions:]
                    for v in to_delete:
                        self.db.delete(v)
                    self.db.commit()
                    print(f"[EDIT CLEANUP DB] Удалено {len(to_delete)} старых версий из БД")

            except Exception as e:
                print(f"[EDIT CLEANUP ERROR] {e}")

            QMessageBox.information(self, "Успех", "Изменения сохранены.\nВерсия создана и обрезана.")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Редактирование не удалось:\n{e}")
            if 'edit_path' in locals():
                os.unlink(edit_path)

    def change_password(self):
        try:
            old_password = None
            if self.file_record.password_hash:
                old_password_input, ok = QInputDialog.getText(
                    self, "Старый пароль", "Введите текущий пароль:", QLineEdit.Password
                )
                if not ok or not old_password_input:
                    QMessageBox.critical(self, "Ошибка", "Операция отменена или пароль не введён")
                    return

                if not verify_password_for_db(old_password_input, self.file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return

                old_password = old_password_input  # сохраняем только если проверка прошла

            new_password_input, ok = QInputDialog.getText(
                self, "Новый пароль", "Новый пароль (пусто — снять шифрование):", QLineEdit.Password
            )
            if not ok:
                return

            # Если пользователь ничего не ввёл — считаем, что хочет снять шифрование
            new_password = new_password_input if new_password_input else None

            print("[CHANGE PASS DEBUG] Начало смены пароля")
            print(f"[CHANGE PASS DEBUG] Старый пароль введён и проверен: {bool(old_password)}")
            print(f"[CHANGE PASS DEBUG] Новый пароль: {'задан' if new_password else 'снимаем шифрование'}")

            # 1. Предварительно обновляем хэш в БД до начала операций с файлом
            # Это предотвратит создание дублирующей версии FileWatcher
            try:
                current_hash = compute_hash(self.file_record.path)
                print(f"[CHANGE PASS DEBUG] Текущий хэш файла: {current_hash[:12]}...")
                self.file_record.current_hash = current_hash
                self.file_record.updated_at = now_msk()
                self.db.commit()
                print("[CHANGE PASS DEBUG] Хэш в БД обновлён до начала операций")
            except Exception as hash_err:
                print(f"[CHANGE PASS ERROR] Ошибка обновления хэша: {hash_err}")
                raise

            container = BackupContainer(self.master_key)

            file_id_str = str(self.file_record.id)
            print(f"[CHANGE PASS DEBUG] file_id: {file_id_str}")
            versions = container.get_all_versions(file_id_str)
            print(f"[CHANGE PASS DEBUG] Версий в контейнере до обработки: {len(versions)}")

            # 1. Расшифровка основного файла (если был старый пароль)
            if old_password:
                print("[CHANGE PASS DEBUG] Расшифровываем основной файл...")
                try:
                    data = decrypt_file(self.file_record.path, old_password)
                    with open(self.file_record.path, "wb") as f:
                        f.write(data)
                    print("[CHANGE PASS DEBUG] Основной файл успешно расшифрован")
                except Exception as dec_err:
                    print(f"[CHANGE PASS ERROR] Ошибка расшифровки основного файла: {dec_err}")
                    raise

            # 2. Перешифровка версий в контейнере (всегда храним plaintext)
            if file_id_str in container.data["files"]:
                for idx, version in enumerate(container.data["files"][file_id_str]):
                    print(f"[CHANGE PASS DEBUG] Обрабатываем версию {idx + 1}/{len(versions)}")

                    content_hex = version["content"]
                    try:
                        content_bytes = bytes.fromhex(content_hex)
                    except ValueError as hex_err:
                        print(f"[CHANGE PASS ERROR] Ошибка декодирования hex версии {idx + 1}: {hex_err}")
                        raise

                    # Расшифровка версии, если она была зашифрована (старые версии)
                    if old_password:
                        print(f"  → Пытаемся расшифровать версию {idx + 1}")
                        try:
                            content_bytes = decrypt_file_from_bytes(content_bytes, old_password)
                            print(f"  → Версия {idx + 1} успешно расшифрована")
                        except Exception as dec_ver_err:  # InvalidTag или другая крипто-ошибка
                            print(f"  → Версия {idx + 1} уже plaintext или повреждена — оставляем как есть ({dec_ver_err})")

                    # Всегда храним plaintext в контейнере для консистентности
                    print(f"  → Версия {idx + 1} сохраняется как plaintext")
                    version["content"] = content_bytes.hex()

            print("[CHANGE PASS DEBUG] Все версии обработаны")
            try:
                container._save()
                print("[CHANGE PASS DEBUG] Контейнер сохранён после перешифровки версий")
            except Exception as save_err:
                print(f"[CHANGE PASS ERROR] Ошибка сохранения контейнера: {save_err}")
                raise

            # 3. Шифрование основного файла (если новый пароль задан)
            if new_password:
                print("[CHANGE PASS DEBUG] Шифруем основной файл новым паролем...")
                try:
                    encrypt_file(self.file_record.path, new_password)
                    print("[CHANGE PASS DEBUG] Основной файл зашифрован новым паролем")
                except Exception as enc_main_err:
                    print(f"[CHANGE PASS ERROR] Ошибка шифрования основного файла: {enc_main_err}")
                    raise

                self.file_record.password_hash = hash_password_for_db(new_password)
            else:
                print("[CHANGE PASS DEBUG] Снимаем шифрование — пароль = None")
                self.file_record.password_hash = None

            # 4. Финальное обновление хэша после всех операций с файлом
            try:
                final_hash = compute_hash(self.file_record.path)
                print(f"[CHANGE PASS DEBUG] Финальный хэш файла: {final_hash[:12]}...")
                self.file_record.current_hash = final_hash
                self.file_record.updated_at = now_msk()
                self.db.commit()
                print("[CHANGE PASS DEBUG] Финальный хэш и пароль обновлены в БД")
            except Exception as hash_err:
                print(f"[CHANGE PASS ERROR] Ошибка финального обновления хэша: {hash_err}")
                raise

            # 5. Лог
            session = SessionLocal()
            if new_password:
                result_text = "Пароль файла изменён"
            else:
                result_text = "Пароль файла снят (все версии расшифрованы)"
            session.add(LogEntry(
                action="file_password_change",
                file_name=self.file_record.name,
                result=result_text,
                user_name=os.getlogin(),
                timestamp=now_msk()
            ))
            session.commit()
            session.close()

            QMessageBox.information(self, "Успех", "Пароль обновлён. Все версии перешифрованы/расшифрованы.")

        except Exception as e:
            import traceback
            print("[CHANGE PASS CRASH] Полный traceback:")
            traceback.print_exc()
            QMessageBox.critical(self, "Ошибка", f"Не удалось изменить пароль:\n{str(e)}")

    def delete_file(self):
        try:
            # 1. Проверка пароля, если файл был зашифрован
            if self.file_record.password_hash:
                password, ok = QInputDialog.getText(
                    self,
                    "Подтверждение доступа",
                    "Файл зашифрован. Введите пароль для подтверждения удаления:",
                    QLineEdit.Password
                )
                if not ok or not password or not verify_password_for_db(password, self.file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль или отмена")
                    return

            # 2. Спрашиваем стратегию удаления
            choice = QMessageBox.question(
                self,
                "Удаление файла",
                "Удалить файл полностью?\n\n"
                "Да — удалить ВСЁ: файл с диска + все версии из контейнера + запись из базы\n"
                "Нет — оставить оригинальный файл на диске, но удалить запись из базы и ВСЕ версии из контейнера\n"
                "Отмена — ничего не делать",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if choice == QMessageBox.Cancel:
                return

            delete_original = (choice == QMessageBox.Yes)

            # 3. Если НЕ удаляем оригинал → предлагаем сохранить версии перед удалением из контейнера
            restored_count = 0
            if not delete_original:
                container_temp = BackupContainer(self.master_key)  # временный, только для чтения версий
                file_id_str = str(self.file_record.id)
                versions_data = container_temp.get_all_versions(file_id_str)

                if versions_data:
                    restore = QMessageBox.question(
                        self,
                        "Сохранение версий перед удалением",
                        f"В контейнере есть {len(versions_data)} версий.\n"
                        "Сохранить их на диск перед удалением из контейнера?\n"
                        "(в том виде, в каком они хранятся — зашифрованные или открытые)",
                        QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
                    )

                    if restore == QMessageBox.Cancel:
                        # Пользователь нажал "Отмена" - полностью отменяем операцию удаления
                        return  # Полная отмена операции удаления

                    if restore == QMessageBox.Yes:
                        restore_dir = QFileDialog.getExistingDirectory(
                            self, "Выберите папку для сохранения версий"
                        )
                        if restore_dir:
                            base_name = os.path.splitext(self.file_record.name)[0]
                            ext = os.path.splitext(self.file_record.path)[1]
                            target_folder = os.path.join(restore_dir, base_name)
                            os.makedirs(target_folder, exist_ok=True)

                            # Если оригинальный файл был зашифрован, запрашиваем пароль один раз
                            password = None
                            if self.file_record.password_hash:
                                password, ok = QInputDialog.getText(
                                    self, "Пароль для версий", 
                                    "Введите пароль для восстановления версий:", 
                                    QLineEdit.Password
                                )
                                if not ok or not password:
                                    QMessageBox.warning(self, "Предупреждение", "Операция отменена")
                                    return
                                
                                if not verify_password_for_db(password, self.file_record.password_hash):
                                    QMessageBox.warning(self, "Ошибка", "Неверный пароль")
                                    return

                            for v in versions_data:
                                dt = datetime.fromisoformat(v["created_at"])
                                safe_name = f"{dt.strftime('%Y%m%d_%H%M%S')}_{base_name}{ext}"
                                out_path = os.path.join(target_folder, safe_name)

                                content_bytes = bytes.fromhex(v["content"])
                                
                                # Если оригинальный файл был зашифрован, все версии должны быть зашифрованы
                                if self.file_record.password_hash:
                                    # Пробуем расшифровать версию
                                    try:
                                        content_bytes = decrypt_file_from_bytes(content_bytes, password)
                                        # Если получилось, значит версия была plaintext - шифруем ее
                                        tmp = tempfile.NamedTemporaryFile(delete=False)
                                        tmp.write(content_bytes)
                                        tmp.close()
                                        try:
                                            encrypt_file(tmp.name, password)
                                            with open(tmp.name, "rb") as f:
                                                content_bytes = f.read()
                                        finally:
                                            os.unlink(tmp.name)
                                    except Exception:
                                        # Версия уже зашифрована, оставляем как есть
                                        pass
                                else:
                                    # Оригинальный файл не зашифрован - все версии должны быть plaintext
                                    pass

                                with open(out_path, "wb") as f:
                                    f.write(content_bytes)
                                restored_count += 1

                            QMessageBox.information(
                                self, "Сохранено", f"Сохранено {restored_count} версий в {target_folder}"
                            )

            # 4. Запускаем асинхронное удаление с DeleteFileThread
            self._start_file_deleting_process(delete_original)

        except Exception as e:
            QMessageBox.critical(self, "Критическая ошибка", f"Не удалось начать удаление:\n{str(e)}")

    def _start_file_deleting_process(self, delete_original):
        """Запускает процесс удаления файла с прогресс-баром и поддержкой отмены"""
        progress = QProgressDialog("Удаление файла...", "Отмена", 0, 100, self)
        progress.setWindowTitle("Удаление файла")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        class FileDeleteWorker(QThread):
            progress_updated = pyqtSignal(int, str)
            finished = pyqtSignal(bool, str)

            def __init__(self, file_id, delete_original, master_key):
                super().__init__()
                self.file_id = file_id
                self.delete_original = delete_original
                self.master_key = master_key
                self._is_cancelled = False
                self._delete_thread = None

            def cancel(self):
                self._is_cancelled = True
                if self._delete_thread and self._delete_thread.isRunning():
                    self._delete_thread.cancel()

            def run(self):
                try:
                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем")
                        return

                    self.progress_updated.emit(10, "Подготовка к удалению...")
                    
                    # Получаем контейнер
                    container = BackupContainer(self.master_key)
                    
                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем")
                        return

                    self.progress_updated.emit(30, "Удаление из контейнера и БД...")
                    
                    # Создаем и запускаем DeleteFileThread
                    self._delete_thread = DeleteFileThread(
                        self.file_id, 
                        self.delete_original, 
                        container
                    )
                    
                    # Подключаем сигналы
                    self._delete_thread.finished.connect(self._on_delete_thread_finished)
                    
                    # Запускаем удаление
                    self._delete_thread.start()
                    
                    # Ожидаем завершения с проверкой отмены
                    while self._delete_thread.isRunning():
                        if self._is_cancelled:
                            self._delete_thread.cancel()
                            self._delete_thread.wait(2000)
                            self.finished.emit(False, "Операция отменена пользователем")
                            return
                        
                        self.msleep(100)  # Небольшая задержка
                    
                    self.progress_updated.emit(100, "Готово!")
                    
                except Exception as e:
                    import traceback
                    print(f"[ERROR] Ошибка в FileDeleteWorker: {e}")
                    traceback.print_exc()
                    self.finished.emit(False, f"Ошибка: {str(e)}")

            def _on_delete_thread_finished(self, success, message):
                """Обработка завершения DeleteFileThread"""
                if self._is_cancelled:
                    self.finished.emit(False, "Операция отменена пользователем")
                else:
                    self.finished.emit(success, message)

        worker = FileDeleteWorker(self.file_record.id, delete_original, self.master_key)
        self._current_worker = worker
        self._current_progress = progress

        @pyqtSlot(int, str)
        def update_progress(value, text):
            if not progress.wasCanceled():
                progress.setValue(value)
                progress.setLabelText(text)

        @pyqtSlot(bool, str)
        def on_operation_finished(success, message):
            progress.close()
            self._current_worker = None
            self._current_progress = None
            self._on_delete_finished(success, message)

        worker.progress_updated.connect(update_progress)
        worker.finished.connect(on_operation_finished)
        progress.canceled.connect(worker.cancel)
        progress.destroyed.connect(self._cleanup_worker)
        worker.start()

    def _on_delete_finished(self, success, message):
        if success:
            QMessageBox.information(self, "Успешно", message)
            self.accept()
            if hasattr(self.parent(), 'load_files'):
                self.parent().load_files()
        else:
            QMessageBox.critical(self, "Ошибка", message)

    def _cleanup_worker(self):
        """Очистка ресурсов при уничтожении диалога"""
        if hasattr(self, '_current_worker') and self._current_worker:
            if self._current_worker.isRunning():
                self._current_worker.cancel()
                self._current_worker.wait(2000)  # Ждём до 2 секунд
            self._current_worker = None
        if hasattr(self, '_current_progress'):
            self._current_progress = None
