import glob
import hashlib
import os
import json
import platform
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from dateutil import parser
import pytz

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QFileDialog, QInputDialog,
    QMessageBox, QComboBox, QLabel, QDialog, QHeaderView, QAbstractItemView, QMenu, QGridLayout
)
from datetime import timedelta
from PyQt5.QtWidgets import QMessageBox, QInputDialog, QFileDialog
import os
import shutil

from app.models import FileRecord, FileVersion
from app.services.file_manager import compute_hash
from app.services.integrity_manager import now_msk
from app.models import FileRecord, FileVersion
from app.services.AddFileThread import AddFileThread
from app.services.FileDropDialog import FileDropDialog
from app.services.FileEditDialog import FileEditDialog
#from app.services.crypto import decrypt_file_to_temp_and_open  # можно использовать, но ниже используем decrypt_file
from app.services.integrity_manager import check_file_integrity
# импортируем из security новые утилиты:
from app.services.security import (
    hash_password_for_db,
    verify_password_for_db,
    encrypt_file,
    decrypt_file
)
from app.reports.reporter import Reporter
from app.db import SessionLocal
from app.services.FileWatcher import FileWatcher
from app.services.file_manager import add_file, compute_hash
#from app.services.backup_manager import get_last_versions

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

db = SessionLocal()

class LocalStoragePage(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window  # сохраняем ссылку на MainWindow, если нужно
        self.setWindowTitle("Local Storage")
        self.setAcceptDrops(True)
        self.db = SessionLocal()

        # Загружаем настройки
        settings_path = os.path.join(os.path.dirname(__file__), "settings.json")

        # === Загружаем настройки ===
        try:
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                    self.max_versions = settings.get("max_versions", 5)
            else:
                self.max_versions = 5
        except Exception:
            self.max_versions = 5

        self.init_ui()
        self.load_files()

        # FileWatcher для локальных файлов
        self.watcher = FileWatcher(main_window=self, interval=5, max_versions=self.max_versions)
        self.watcher.start()

    def init_ui(self):
        layout = QVBoxLayout()

        # === Таблица файлов ===
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Имя файла", "Последнее изменение", "Статус", "Путь", "Зашифрован"
        ])
        self.table.hideColumn(0)
        layout.addWidget(self.table)

        # === Настройка ширины столбцов ===
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)

        # === Панель действий (1 ряд) ===
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(10)

        # === Основные кнопки ===
        buttons = [
            ("Добавить файл", self.add_file_dialog),
            ("Открыть", self.view_encrypted_file),
            ("Редактировать", self.edit_file_dialog),
            ("Восстановить версию", self.restore_file_dialog),
        ]

        for text, func in buttons:
            btn = QPushButton(text)
            btn.setMinimumWidth(160)
            btn.clicked.connect(func)
            actions_layout.addWidget(btn)

        actions_layout.addStretch()  # сдвигаем меню вправо

        # === Меню "⋯" ===
        from PyQt5.QtWidgets import QToolButton

        more_menu = QMenu(self)

        from PyQt5.QtWidgets import QActionGroup

        # --- Подменю версий ---
        versions_menu = QMenu("Количество версий", self)

        versions_group = QActionGroup(self)
        versions_group.setExclusive(True)  # только один выбран

        current_value = int(self.max_versions)

        for i in range(1, 10):
            act = versions_menu.addAction(str(i))
            act.setCheckable(True)
            act.setChecked(i == current_value)

            act.triggered.connect(lambda _, x=i: self.change_max_versions(str(x)))

            versions_group.addAction(act)

        more_menu.addMenu(versions_menu)
        more_menu.addSeparator()

        # --- Остальные действия ---
        raw_action = more_menu.addAction("Открыть зашифрованный Back Up")
        raw_action.triggered.connect(self.open_encrypted_raw)

        export_action = more_menu.addAction("Экспорт отчёта")
        export_action.triggered.connect(self.export_report)

        more_menu.addSeparator()

        back_action = more_menu.addAction("Назад")
        back_action.triggered.connect(self.back_to_menu)

        # === Кнопка ⋯ ===
        more_btn = QToolButton()
        more_btn.setText("⋯")
        more_btn.setFixedWidth(36)
        more_btn.setPopupMode(QToolButton.InstantPopup)
        more_btn.setMenu(more_menu)

        actions_layout.addWidget(more_btn)

        layout.addLayout(actions_layout)

        # === Drag & Drop ===
        self.setAcceptDrops(True)
        self.table.setAcceptDrops(True)
        self.table.dragEnterEvent = self.table_drag_enter
        self.table.dropEvent = self.table_drop

        self.setLayout(layout)

        # === Открытие зашифрованного бэкапа ===
    def open_encrypted_raw(self):
        backup_path, _ = QFileDialog.getOpenFileName(self, "Выберите зашифрованный бэкап", "/Users/macbook/backups")
        if not backup_path: return
        password, ok = QInputDialog.getText(self, "Пароль", "Введите пароль для расшифровки:")
        if not ok or not password: return
        try:
            data = decrypt_file(backup_path, password)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(backup_path)[1])
            tmp.write(data)
            tmp.close()
            # Открываем системным редактором
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", tmp.name])
            elif system == "Windows":
                os.startfile(tmp.name)
            else:
                subprocess.run(["xdg-open", tmp.name])
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть бэкап:\n{e}")

    # === Drag & Drop ===
    def table_drag_enter(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("background-color: #2c2c2c; border: 2px dashed #00c853;")
        else:
            event.ignore()

    def table_drop(self, event):
        self.setStyleSheet("")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    self.add_file_from_path(path)
        else:
            event.ignore()


    def change_max_versions(self, value):
        """
        Обновляет максимальное количество версий, сохраняет в app/ui/settings.json
        и удаляет лишние старые версии вместе с файлами бэкапов.
        """
        try:
            self.max_versions = int(value)
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Неверное значение для количества версий.")
            return

        # === Путь к settings.json (в той же папке, где этот модуль) ===
        settings_path = os.path.join(os.path.dirname(__file__), "settings.json")

        # === Чтение существующих настроек ===
        settings_data = {}
        try:
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings_data = json.load(f)
        except Exception as e:
            QMessageBox.warning(self, "Внимание", f"Не удалось прочитать настройки: {e}")

        # === Обновление значения и сохранение ===
        settings_data["max_versions"] = self.max_versions
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, "Внимание", f"Не удалось записать настройки: {e}")

        QMessageBox.information(self, "Настройка", f"Теперь будет храниться до {self.max_versions} версий файлов.")

        # === Обновляем watcher и backup_manager ===
        try:
            if self.watcher:
                self.watcher.max_versions = self.max_versions
                if hasattr(self.watcher, "backup_manager") and self.watcher.backup_manager is not None:
                    # если backup_manager хранит max_versions — установим
                    try:
                        self.watcher.backup_manager.max_versions = self.max_versions
                    except Exception:
                        pass
        except Exception:
            pass

        # === Обрезаем лишние версии ===
        session = SessionLocal()
        try:
            files = session.query(FileRecord).all()

            # Собираем возможные директории с бэкапами (строки)
            backup_dirs = []

            # 1) из watcher.backup_manager.local_backup / external_backup если есть
            try:
                if self.watcher and hasattr(self.watcher, "backup_manager") and self.watcher.backup_manager is not None:
                    bm = self.watcher.backup_manager
                    for attr in ("local_backup", "external_backup"):
                        try:
                            p = getattr(bm, attr, None)
                            if p:
                                p_s = str(p)
                                if p_s and p_s not in backup_dirs:
                                    backup_dirs.append(p_s)
                        except Exception:
                            continue
            except Exception:
                pass

            # 2) fallback: несколько обычных мест (включая тот, что ты использовал)
            cwd_backup = os.path.join(os.path.dirname(__file__), "..", "backups")
            cwd_backup = os.path.normpath(os.path.abspath(cwd_backup))
            if cwd_backup not in backup_dirs:
                backup_dirs.append(cwd_backup)
            if os.getcwd() not in backup_dirs:
                # fallback на рабочую директорию + "backups"
                backup_dirs.append(os.path.join(os.getcwd(), "backups"))
            # ещё жестко заданный путь, если он у тебя в проекте используется
            hardcoded = "/Users/macbook/backups"
            if hardcoded not in backup_dirs:
                backup_dirs.append(hardcoded)

            # Нормализуем и оставляем только существующие/валидные папки (но оставим и несуществующие — для попытки удаления)
            backup_dirs = [os.path.normpath(os.path.abspath(p)) for p in backup_dirs if p]

            for file in files:
                # получаем версии (новые — первыми)
                versions = (
                    session.query(FileVersion)
                    .filter(FileVersion.file_id == file.id)
                    .order_by(FileVersion.created_at.desc())
                    .all()
                )

                # если версий больше чем max_versions — удаляем самые старые
                if len(versions) <= self.max_versions:
                    continue

                to_delete = versions[self.max_versions:]  # старые версии (тут порядок: older ones)
                for old_version in to_delete:
                    # формируем типичное имя backup: "{file_id}_{YYYYMMDDhhmmss}_{basename}"
                    ts = old_version.created_at.strftime("%Y%m%d%H%M%S")
                    filename = os.path.basename(file.path)
                    expected_name = f"{old_version.file_id}_{ts}_{filename}"

                    deleted_any = False

                    # пробуем удалить точные совпадения в известных директориях
                    for bdir in backup_dirs:
                        candidate = os.path.join(bdir, expected_name)
                        if os.path.exists(candidate):
                            try:
                                os.remove(candidate)
                                deleted_any = True
                            except Exception:
                                # игнорируем отдельные ошибки удаления
                                pass

                        # также пробуем вариант, где копии лежат в подпапке с именем файла:
                        candidate2 = os.path.join(bdir, filename, expected_name)
                        if os.path.exists(candidate2):
                            try:
                                os.remove(candidate2)
                                deleted_any = True
                            except Exception:
                                pass

                    # если не нашли точные совпадения — используем glob по шаблону (на всякий случай)
                    if not deleted_any:
                        import glob
                        pattern = f"*{old_version.file_id}*{ts}*{filename}*"
                        for bdir in backup_dirs:
                            try:
                                for found in glob.glob(os.path.join(bdir, pattern)):
                                    try:
                                        os.remove(found)
                                        deleted_any = True
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                    # После попытки удалить файл бэкапа — удаляем запись версии из БД
                    try:
                        session.delete(old_version)
                    except Exception:
                        # если не удалось удалить запись — игнорируем и продолжим
                        pass

            # один коммит в конце (если что-то пошло не так, откатим)
            session.commit()

        except Exception as e:
            session.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось обрезать старые версии: {e}")
        finally:
            session.close()

        # === Обновляем таблицу в UI ===
        try:
            self.load_files()
        except Exception:
            pass

    def load_files(self):
        # Настройка поведения выделения (одна строка, выделяются целиком строки)
        try:
            self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        except Exception:
            pass

        # Если нет выбранных элементов — считаем, что пользователь снял выделение
        if not self.table.selectedItems():
            selected_row = -1
        else:
            selected_row = self.table.currentRow()

        # Перезагрузка таблицы
        self.table.setRowCount(0)
        files = self.db.query(FileRecord).all()

        for file in files:
            row = self.table.rowCount()
            self.table.insertRow(row)

            # ID (скрытый)
            self.table.setItem(row, 0, QTableWidgetItem(str(file.id)))
            # Имя файла
            self.table.setItem(row, 1, QTableWidgetItem(file.name))
            # Статус
            self.table.setItem(row, 3, QTableWidgetItem(file.status))
            # Путь
            self.table.setItem(row, 4, QTableWidgetItem(file.path))

            # Определяем дату последнего изменения
            last_version = (
                self.db.query(FileVersion)
                .filter(FileVersion.file_id == file.id)
                .order_by(FileVersion.created_at.desc())
                .first()
            )
            last_change = (
                last_version.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if last_version
                else file.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            )
            self.table.setItem(row, 2, QTableWidgetItem(last_change))

            # === Новый столбец: "Зашифрован" ===
            is_encrypted = "Да" if file.password_hash else "Нет"
            self.table.setItem(row, 5, QTableWidgetItem(is_encrypted))

        # Автоматически подгоняем ширину под содержимое
        #self.table.resizeColumnsToContents()
        if selected_row >= 0 and selected_row < self.table.rowCount():
            self.table.selectRow(selected_row)
        else:
            self.table.clearSelection()


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
                QMessageBox.information(self, "Результат", msg) if success else QMessageBox.critical(self, "Ошибка",
                                                                                                     msg),
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
                QMessageBox.information(self, "Результат", msg) if success else QMessageBox.critical(self, "Ошибка",
                                                                                                     msg),
                self.load_files()
            )
        )
        self.current_add_thread.start()

    def view_encrypted_file(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Внимание", "Выберите файл в таблице")
            return

        file_id = int(self.table.item(row, 0).text())
        file_record = self.db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            QMessageBox.warning(self, "Ошибка", "Файл не найден")
            return

        if not file_record.password_hash:
            QMessageBox.warning(self, "Файл не зашифрован", "Файл не имеет пароля и не зашифрован")
            return

        password, ok = QInputDialog.getText(
            self, "Пароль", f"Введите пароль для файла {file_record.name}:"
        )
        if not ok or not password:
            return

        try:
            # Проверяем пароль с bcrypt-хэша из БД
            if not verify_password_for_db(password, file_record.password_hash):
                raise ValueError("Неверный пароль")

            # Дешифруем файл (decrypt_file читает соль из файла и использует PBKDF2 -> Fernet)
            data = decrypt_file(file_record.path, password)

            # Создаём временный файл
            _, ext = os.path.splitext(file_record.path)
            # Создаём временный файл с НОРМАЛЬНЫМ именем
            temp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(temp_dir, f"{file_record.name}.decrypted{ext}")

            with open(tmp_path, "wb") as f:
                f.write(data)

            # Открываем
            system = platform.system()
            if system == "Darwin":
                subprocess.run(["open", tmp_path], check=False)
            elif system == "Windows":
                os.startfile(tmp_path)
            else:
                subprocess.run(["xdg-open", tmp_path], check=False)

            QMessageBox.information(self, "Готово", f"Расшифрованный файл открыт: {tmp_path}")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл:\n{e}")

    def edit_file_dialog(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Внимание", "Выберите файл в таблице")
            return
        file_id = int(self.table.item(row, 0).text())
        file_record = self.db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            QMessageBox.warning(self, "Ошибка", "Файл не найден в базе")
            return
        dialog = FileEditDialog(self.db, file_record, self)
        dialog.exec_()
        self.load_files()



    def restore_file_dialog(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Внимание", "Выберите файл в таблице")
            return

        file_id = int(self.table.item(row, 0).text())
        file_record = self.db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            QMessageBox.warning(self, "Ошибка", "Файл не найден")
            return

        # === Загружаем версии файла ===
        versions = (
            self.db.query(FileVersion)
            .filter(FileVersion.file_id == file_id)
            .order_by(FileVersion.created_at.desc())
            .limit(self.max_versions)
            .all()
        )

        if not versions:
            QMessageBox.information(self, "Информация", "Нет доступных резервных версий")
            return

        # Показываем список версий
        items = [
            f"{v.created_at.astimezone(MOSCOW_TZ).strftime('%Y-%m-%d %H:%M:%S')} | {v.comment or ''}"
            for v in versions
        ]

        item, ok = QInputDialog.getItem(self, "Выберите версию", "Версия:", items, editable=False)
        if not (ok and item):
            return

        version_index = items.index(item)
        version = versions[version_index]

        # === Получаем МСК-время версии ===
        version_msk = version.created_at.astimezone(MOSCOW_TZ)
        timestamp_str = version_msk.strftime("%Y%m%d%H%M%S")

        # === Формируем путь к бэкапу ===
        backup_root = "/Users/macbook/backups"
        filename = os.path.basename(file_record.path)

        backup_path = os.path.join(
            backup_root,
            f"{file_id}_{timestamp_str}_{filename}"
        )

        if not os.path.exists(backup_path):
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Резервная копия не найдена:\n{backup_path}"
            )
            return

        # === Куда сохранять восстановленный файл ===
        restore_path, _ = QFileDialog.getSaveFileName(
            self,
            "Куда восстановить файл",
            os.path.basename(file_record.path)
        )
        if not restore_path:
            return

        try:
            shutil.copy2(backup_path, restore_path)

            # обновляем хэш
            file_record.current_hash = compute_hash(restore_path)
            file_record.updated_at = now_msk()
            self.db.commit()

            QMessageBox.information(
                self,
                "Готово",
                f"Файл восстановлен:\n{restore_path}\n"
                f"Из резервной копии:\n{os.path.basename(backup_path)}"
            )
            self.load_files()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось восстановить файл:\n{e}")



    def export_report(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить отчёт", "report", "CSV Files (*.csv);;JSON Files (*.json);;PDF Files (*.pdf)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                Reporter.export_csv(path)
                Reporter.log_export(path)
            elif ext == ".json":
                Reporter.export_json(self.db, path)
                Reporter.log_export(self.db, "json", path)
            elif ext == ".pdf":
                Reporter.export_pdf(self.db, path)
                Reporter.log_export(self.db, "pdf", path)
            else:
                QMessageBox.warning(self, "Ошибка", "Неподдерживаемый формат")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    # === Назад ===
    def back_to_menu(self):
        self.main_window.navigate_to("menu")
