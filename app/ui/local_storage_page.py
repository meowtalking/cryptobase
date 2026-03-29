import json
import platform
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
import pytz

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHBoxLayout, QHeaderView, QAbstractItemView, QMenu, QLineEdit
)
from PyQt5.QtWidgets import QMessageBox, QInputDialog, QFileDialog
import os
from app.models import LogEntry
from app.services.backup_container import BackupContainer
from app.models import FileRecord, FileVersion
from app.services.FileEditDialog import FileEditDialog
from app.services.integrity_manager import now_msk
from app.services.security import (
    verify_password_for_db,
    encrypt_file,
    decrypt_file
)
from app.reports.reporter import Reporter
from app.db import SessionLocal
from app.services.file_manager import compute_hash
from app.services.file_manager_new import add_file_new

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
            ("Добавить файл", self.add_file_dialog_new),
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

        auto_lock_action = more_menu.addAction("Автоблокировка...")
        auto_lock_action.triggered.connect(self.change_auto_lock)

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
                subprocess.run(["open", tmp.name], check=False)
            elif system == "Windows":
                os.startfile(tmp.name)
            else:
                subprocess.run(["xdg-open", tmp.name], check=False)
            
            QMessageBox.information(self, "Готово", f"Расшифрованный файл открыт: {tmp.name}\n\nВнимание: временный файл будет удалён при закрытии приложения.")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть бэкап:\n{e}")

    def change_auto_lock(self):
        options = ["15 минут", "30 минут", "1 час", "2 часа", "Никогда"]
        values = [15, 30, 60, 120, 0]

        current = self.main_window.get_auto_lock_minutes()  # метод добавим в MainWindow

        current_idx = values.index(current) if current in values else 1

        choice, ok = QInputDialog.getItem(
            self,
            "Автоблокировка",
            "Выберите время бездействия до блокировки:",
            options,
            current_idx,
            False
        )

        if ok:
            minutes = values[options.index(choice)]
            self.main_window.set_auto_lock_minutes(minutes)
            self.main_window.start_auto_lock_timer(minutes)
            self._save_settings(minutes)

    def _save_settings(self, minutes: int):
        import json
        settings_path = Path(__file__).parent / "settings.json"

        settings = {}
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)

        settings["auto_lock_minutes"] = minutes

        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)

    def change_max_versions(self, value):
        """
        Обновляет максимальное количество версий, сохраняет в settings.json
        и удаляет лишние старые версии из контейнера и БД.
        """
        try:
            new_max = int(value)
            if new_max < 1:
                raise ValueError
            self.max_versions = new_max
        except Exception:
            QMessageBox.critical(self, "Ошибка", "Количество версий должно быть целым числом ≥ 1")
            return

        # Сохранение в settings.json
        settings_path = Path(__file__).parent / "settings.json"
        settings_data = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings_data = json.load(f)
            except Exception as e:
                QMessageBox.warning(self, "Внимание", f"Не удалось прочитать настройки: {e}")

        settings_data["max_versions"] = self.max_versions
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, "Внимание", f"Не удалось сохранить настройки: {e}")
            return

        QMessageBox.information(self, "Настройка", f"Теперь будет храниться до {self.max_versions} версий файлов.")

        # Обновляем watcher
        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.max_versions = self.max_versions

        # Обрезаем версии в контейнере и БД
        if not hasattr(self.main_window, 'master_key') or not self.main_window.master_key:
            QMessageBox.warning(self, "Внимание", "Мастер-ключ недоступен — обрезка в контейнере пропущена")
            self.load_files()
            return

        try:
            container = BackupContainer(self.main_window.master_key)
            session = SessionLocal()

            for file_record in session.query(FileRecord).all():
                file_id_str = str(file_record.id)

                # === Обрезка в контейнере ===
                if file_id_str in container.data["files"]:
                    versions = container.data["files"][file_id_str]

                    # Сортируем по created_at (от старых к новым)
                    versions.sort(key=lambda v: datetime.fromisoformat(v["created_at"]))

                    if len(versions) > self.max_versions:
                        # Если достигнут лимит, обрезаем старые версии (включая initial)
                        # Оставляем самые новые (последние N)
                        container.data["files"][file_id_str] = versions[-self.max_versions:]
                        if not container.data["files"][file_id_str]:
                            del container.data["files"][file_id_str]
                        print(f"[CLEANUP] Достигнут лимит {self.max_versions} - обрезка старых версий в контейнере для {file_record.name}")

                # === Обрезка в БД ===
                db_versions = (
                    session.query(FileVersion)
                    .filter(FileVersion.file_id == file_record.id)
                    .order_by(FileVersion.created_at.desc())
                    .all()
                )

                if len(db_versions) > self.max_versions:
                    to_delete = db_versions[self.max_versions:]  # старые в начале списка
                    for v in to_delete:
                        session.delete(v)
                    print(f"[CLEANUP] Удалено {len(to_delete)} старых версий из БД для {file_record.name}")

            # Сохраняем изменения
            container._save()
            session.commit()
            print(f"[CLEANUP] Обрезка завершена. Текущий лимит: {self.max_versions}")

        except Exception as e:
            if 'session' in locals():
                session.rollback()
            QMessageBox.critical(self, "Ошибка", f"Не удалось обрезать версии:\n{e}")
        finally:
            if 'session' in locals():
                session.close()

        self.load_files()

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

    def add_file_dialog_new(self):
        """Новое добавление файла с поддержкой отмены и Drag&Drop"""
        from PyQt5.QtWidgets import QProgressDialog, QFileDialog, QInputDialog, QDialog, QVBoxLayout, QPushButton, \
            QLabel, QHBoxLayout
        from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

        # Создаём диалог с возможностью Drag&Drop
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавление файла")
        dialog.setMinimumWidth(400)
        dialog.setAcceptDrops(True)  # Включаем Drag&Drop для диалога

        layout = QVBoxLayout()

        # Область для Drag&Drop
        self.drop_area = QLabel("Перетащите файл сюда\n\nили")
        self.drop_area.setAlignment(Qt.AlignCenter)
        self.drop_area.setStyleSheet("""
            background-color: #f8f9fa;
            border: 2px dashed #6c757d;
            padding: 40px;
            font-size: 16px;
            color: #6c757d;
        """)
        layout.addWidget(self.drop_area)

        # Кнопка выбора файла
        self.select_btn = QPushButton("Выбрать файл")
        self.select_btn.clicked.connect(lambda: self._handle_file_selection(dialog))
        layout.addWidget(self.select_btn)

        # Кнопки управления
        button_layout = QHBoxLayout()
        self.next_btn = QPushButton("Далее")
        self.next_btn.setEnabled(False)  # Изначально кнопка неактивна
        self.next_btn.clicked.connect(lambda: self._show_password_dialog(dialog))

        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(dialog.reject)

        button_layout.addStretch()
        button_layout.addWidget(self.next_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        dialog.setLayout(layout)

        # Обработчики Drag&Drop для диалога
        dialog.dragEnterEvent = self._dialog_drag_enter
        dialog.dropEvent = self._dialog_drop

        result = dialog.exec_()

        if hasattr(self, '_selected_file_path'):
            delattr(self, '_selected_file_path')

    def _dialog_drag_enter(self, event):
        """ Обработка входа Drag & Drop на диалог """
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_area.setStyleSheet("""
        background - color:  # e9ecef;
        border: 2
        px
        solid  # 00c853;
        padding: 40
        px;
        font - size: 16
        px;
        color:  # 00c853;
        font - weight: bold;
        """)
        else:
            event.ignore()


    def _dialog_drop(self, event):
        """Обработка Drop на диалоге"""
        self.drop_area.setStyleSheet("""
            background-color: #f8f9fa;
            border: 2px dashed #6c757d;
            padding: 40px;
            font-size: 16px;
            color: #6c757d;
        """)

        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path):
                    self._selected_file_path = file_path
                    # Обновляем надпись с названием файла
                    file_name = os.path.basename(file_path)
                    self.drop_area.setText(f"Выбран файл:\n\n{file_name}")
                    self.next_btn.setEnabled(True)  # Активируем кнопку «Далее»
                    self.select_btn.hide()  # Скрываем кнопку «Выбрать файл»
                    event.accept()
                    break  # Обрабатываем только первый файл
        else:
            event.ignore()

    def _handle_file_selection(self, dialog):
        """ Обрабатывает выбор файла через диалог """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите файл", "", "Все файлы (*)"
        )
        if file_path:
            self._selected_file_path = file_path
            # Обновляем надпись с названием файла
            file_name = os.path.basename(file_path)
            self.drop_area.setText(f"Выбран файл:\n\n{file_name}")
            self.next_btn.setEnabled(True)  # Активируем кнопку «Далее»
            self.select_btn.hide()  # Скрываем кнопку «Выбрать файл»

    def _show_password_dialog(self, parent_dialog):
        """ Показывает диалог ввода пароля после выбора файла """
        from PyQt5.QtWidgets import QInputDialog

        password, ok = QInputDialog.getText(
            self, "Пароль", "Введите пароль для защиты (оставьте пустым если не нужен):", QLineEdit.Password
        )
        if not ok:
            return

        parent_dialog.accept()  # Закрываем окно выбора файла

        # Запускаем процесс добавления файла с прогресс‑диалогом
        self._start_file_adding_process(self._selected_file_path, password)

    def _start_file_adding_process(self, file_path, password=None):
        if not hasattr(self.main_window, 'master_key') or not self.main_window.master_key:
            QMessageBox.critical(self, "Ошибка", "Мастер-ключ недоступен. Невозможно добавить файл.")
            return

        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot

        progress = QProgressDialog("Добавление файла...", "Отмена", 0, 100, self)
        progress.setWindowTitle("Добавление файла")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        class FileAddWorker(QThread):
            progress_updated = pyqtSignal(int, str)
            finished = pyqtSignal(bool, str, object)

            def __init__(self, file_path, password, master_key):
                super().__init__()
                self.file_path = file_path
                self.password = password
                self.master_key = master_key
                self._is_cancelled = False

            def cancel(self):
                self._is_cancelled = True

            def run(self):
                try:
                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем", None)
                        return self.progress_updated.emit(10, "Чтение файла...")
                    file_record = add_file_new(
                        self.file_path,
                        self.password.strip() if self.password else None,
                        self.master_key
                    )

                    if self._is_cancelled:
                        self.finished.emit(False, "Операция отменена пользователем", None)
                    else:
                        self.progress_updated.emit(80, "Сохранение в БД...")
                        self.progress_updated.emit(100, "Готово!")
                        self.finished.emit(True, f"Файл '{file_record.name}' добавлен", file_record)
                except Exception as e:
                    import traceback
                    print(f"[ERROR] Ошибка в FileAddWorker: {e}")
                    traceback.print_exc()
                    self.finished.emit(False, f"Ошибка: {str(e)}", None)

        worker = FileAddWorker(file_path, password, self.main_window.master_key)
        self._current_worker = worker
        self._current_progress = progress

        @pyqtSlot(int, str)
        def update_progress(value, text):
            if not progress.wasCanceled():
                progress.setValue(value)
                progress.setLabelText(text)

        @pyqtSlot(bool, str, object)
        def on_operation_finished(success, message, file_record):
            progress.close()
            self._current_worker = None
            self._current_progress = None
            self._on_file_added_new(success, message, file_record)

        worker.progress_updated.connect(update_progress)
        worker.finished.connect(on_operation_finished)
        progress.canceled.connect(worker.cancel)
        progress.destroyed.connect(self._cleanup_worker)
        worker.start()

    def _start_file_deleting_process(self, file_id, delete_original=False):
        """Запускает процесс удаления файла с прогресс-баром и поддержкой отмены"""
        if not hasattr(self.main_window, 'master_key') or not self.main_window.master_key:
            QMessageBox.critical(self, "Ошибка", "Мастер-ключ недоступен. Невозможно удалить файл.")
            return

        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
        from app.services.DeleteFileThread import DeleteFileThread
        from app.services.backup_container import BackupContainer

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

                    self.progress_updated.emit(30, "Удаление из контейнера...")
                    
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

        worker = FileDeleteWorker(file_id, delete_original, self.main_window.master_key)
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
            self._on_file_deleted(success, message)

        worker.progress_updated.connect(update_progress)
        worker.finished.connect(on_operation_finished)
        progress.canceled.connect(worker.cancel)
        progress.destroyed.connect(self._cleanup_worker)
        worker.start()


    def _cleanup_worker(self):
            """Очистка ресурсов при уничтожении диалога"""
            if hasattr(self, '_current_worker') and self._current_worker:
                # Если поток ещё выполняется, отменяем и ждём завершения
                if self._current_worker.isRunning():
                    self._current_worker.cancel()
                    self._current_worker.wait(2000)  # Ждём до 2 секунд
                # Освобождаем ресурсы
                self._current_worker = None
            if hasattr(self, '_current_progress'):
                self._current_progress = None

    def _on_file_added_new(self, success, message, file_record):
            """Обработка результата добавления файла"""
            if success:
                QMessageBox.information(self, "Успех", message)
                if file_record:
                    print(f"[ADD_FILE_NEW] Файл добавлен: {file_record.name} (ID: {file_record.id})")
            else:
                QMessageBox.critical(self, "Ошибка", message)

            self.load_files()

    def _on_file_deleted(self, success, message):
        """Обработка результата удаления файла"""
        if success:
            QMessageBox.information(self, "Успех", message)
            print(f"[DELETE_FILE] Операция удаления завершена: {message}")
        else:
            QMessageBox.critical(self, "Ошибка", message)
            print(f"[DELETE_FILE] Ошибка удаления: {message}")

        self.load_files()



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

        master_key = self.main_window.master_key if hasattr(self.main_window, 'master_key') else None
        if not master_key:
            QMessageBox.critical(self, "Ошибка", "Мастер-ключ недоступен")
            return

        dialog = FileEditDialog(self.db, file_record, self, master_key=master_key)
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

        # Перезагружаем объект из БД, чтобы password_hash был актуальным
        self.db.refresh(file_record)
        print(
            f"[DEBUG RESTORE] password_hash после refresh: {file_record.password_hash} (type: {type(file_record.password_hash)})")

        # Получаем контейнер
        if not hasattr(self.main_window, 'master_key') or not self.main_window.master_key:
            QMessageBox.critical(self, "Ошибка", "Мастер-ключ недоступен")
            return

        container = BackupContainer(self.main_window.master_key)

        # Версии из контейнера
        versions_data = container.get_all_versions(str(file_id))
        if not versions_data:
            QMessageBox.information(self, "Информация", "Нет доступных версий в контейнере")
            return

        items = []
        for idx, v in enumerate(versions_data):
            dt = datetime.fromisoformat(v["created_at"])
            items.append(f"{dt.strftime('%Y-%m-%d %H:%M:%S')} | {v.get('comment', '')}")

        item, ok = QInputDialog.getItem(self, "Выберите версию", "Версия:", items, editable=False)
        if not (ok and item):
            return

        version_index = items.index(item)
        selected_version = versions_data[version_index]

        # Куда восстановить
        restore_path, _ = QFileDialog.getSaveFileName(
            self,
            "Куда восстановить файл",
            file_record.name
        )
        if not restore_path:
            return

        try:
            # Получаем plaintext контент из контейнера
            content_bytes = bytes.fromhex(selected_version["content"])
            
            # Определяем формат восстановления
            if file_record.password_hash is not None and file_record.password_hash.strip():
                # Файл зашифрован в БД → восстанавливаем зашифрованным
                print("[DEBUG RESTORE] Файл зашифрован → восстанавливаем в зашифрованном виде")
                
                # Запрашиваем пароль ОДИН РАЗ
                password, ok = QInputDialog.getText(
                    self, "Пароль", "Введите пароль для шифрования восстановленного файла:", QLineEdit.Password
                )
                if not (ok and password):
                    return
                
                # Проверяем пароль
                if not verify_password_for_db(password, file_record.password_hash):
                    QMessageBox.critical(self, "Ошибка", "Неверный пароль")
                    return
                
                # Сначала пишем plaintext
                with open(restore_path, "wb") as f:
                    f.write(content_bytes)
                
                # Затем шифруем файл
                encrypt_file(restore_path, password)
                print("[DEBUG RESTORE] Файл успешно зашифрован")
                
            else:
                # Файл plaintext в БД → восстанавливаем как plaintext
                print("[DEBUG RESTORE] Файл plaintext → восстанавливаем без шифрования")
                
                # Просто пишем plaintext контент
                with open(restore_path, "wb") as f:
                    f.write(content_bytes)
                
                print("[DEBUG RESTORE] Файл успешно восстановлен как plaintext")

            # Обновляем хэш в БД (оригинального файла, а не копии)
            file_record.current_hash = compute_hash(file_record.path)
            file_record.updated_at = now_msk()
            self.db.commit()

            # Показываем сообщение об успехе
            QMessageBox.information(self, "Успех", f"Файл успешно восстановлен в:\n{restore_path}")

            # Лог восстановления
            session = SessionLocal()
            session.add(LogEntry(
                action="restore_version",
                file_name=file_record.name,
                result=f"Восстановлена версия от {selected_version['created_at']} в {restore_path}",
                user_name=os.getlogin(),
                timestamp=now_msk()
            ))
            session.commit()
            session.close()

            self.load_files()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось восстановить:\n{e}")


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
