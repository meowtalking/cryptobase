import shutil
import sys
import os

from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QFileDialog, QInputDialog, QMessageBox, QComboBox, QLabel, QDialog
)
from PyQt5.QtCore import Qt
from app.db import SessionLocal
from app.models import FileRecord, FileVersion
from app.services.integrity_manager import check_file_integrity, update_file_hash
from app.services.backup_manager import BackupManager
from app.services.security import hash_password

from app.services.reporter import Reporter
from app.db import SessionLocal
from app.services.file_watcher import FileWatcher

db = SessionLocal()

# Экспорт JSON
Reporter.export_json(db, "report.json")

# Экспорт PDF
Reporter.export_pdf(db, "report.pdf")

# Логируем действие
Reporter.log_export(db, "pdf", "report.pdf")


from PyQt5.QtWidgets import QPushButton, QHBoxLayout

class FileEditDialog(QDialog):
    """Диалог для редактирования деталей файла"""

    def __init__(self, db, file_record: FileRecord, parent=None):
        super().__init__(parent)
        self.db = db
        self.file_record = file_record
        self.setWindowTitle(f"Редактирование файла: {file_record.name}")
        self.setGeometry(400, 400, 400, 250)

        layout = QVBoxLayout()

        # Метка с именем файла
        self.label_name = QLabel(f"Файл: {file_record.name}")
        layout.addWidget(self.label_name)

        # Кнопка смены пароля
        self.btn_change_password = QPushButton("Сменить пароль")
        self.btn_change_password.clicked.connect(self.change_password)
        layout.addWidget(self.btn_change_password)

        # Кнопка удаления файла
        self.btn_delete = QPushButton("Удалить файл")
        self.btn_delete.clicked.connect(self.delete_file)
        layout.addWidget(self.btn_delete)

        # Кнопка закрытия
        self.btn_close = QPushButton("Закрыть")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)

        self.setLayout(layout)

    def change_password(self):
        from app.services.security import hash_password

        password, ok = QInputDialog.getText(
            self, "Новый пароль", "Введите новый пароль (оставьте пустым для удаления пароля):"
        )
        if ok:
            if password:
                self.file_record.password_hash = hash_password(password)
            else:
                self.file_record.password_hash = None
            self.db.commit()
            QMessageBox.information(self, "Успех", "Пароль обновлён")

    def delete_file(self):
        confirm = QMessageBox.question(
            self, "Удаление файла",
            f"Вы уверены, что хотите удалить файл {self.file_record.name}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            try:
                # Удаляем файл из диска, если он существует
                if os.path.exists(self.file_record.path):
                    os.remove(self.file_record.path)
                # Удаляем запись из базы
                self.db.delete(self.file_record)
                self.db.commit()
                QMessageBox.information(self, "Успех", "Файл удалён")
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить файл: {e}")


class FileDropDialog(QDialog):
    """Окно для перетаскивания файла (Drag & Drop) с кнопкой 'Далее'"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Добавление файла")
        self.setGeometry(300, 300, 400, 200)
        self.setAcceptDrops(True)
        self.file_path = None

        layout = QVBoxLayout()

        self.label = QLabel("Перетащите файл сюда")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Arial", 14))
        self.label.setStyleSheet(
            "QLabel { border: 3px dashed #00c853; color: #aaa; padding: 40px; }"
        )
        layout.addWidget(self.label)

        # Кнопка Далее
        btn_layout = QHBoxLayout()
        self.next_btn = QPushButton("Далее")
        self.next_btn.setEnabled(False)  # будет активна только после того, как файл перетащен
        self.next_btn.clicked.connect(self.accept)  # закрывает диалог с кодом Accepted
        btn_layout.addStretch()
        btn_layout.addWidget(self.next_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.setLayout(layout)

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
                    self.label.setText(f"✅ Файл готов к добавлению:\n{os.path.basename(path)}")
                    self.next_btn.setEnabled(True)  # включаем кнопку "Далее"
                    break
        self.label.setStyleSheet(
            "QLabel { border: 3px dashed #00c853; color: #aaa; padding: 40px; }"
        )



class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CryptoBase Monitor")
        self.setGeometry(100, 100, 900, 500)
        self.setAcceptDrops(True)
        self.db = SessionLocal()
        import json

        # Загружаем настройки из settings.json
        try:
            if os.path.exists("settings.json"):
                with open("settings.json", "r") as f:
                    settings = json.load(f)
                    self.max_versions = settings.get("max_versions", 5)
            else:
                self.max_versions = 5
        except Exception as e:
            print(f"[Ошибка загрузки настроек]: {e}")
            self.max_versions = 5

        self.init_ui()
        self.load_files()
        self.watcher = None

    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()

        # === Таблица файлов ===
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Имя файла", "Путь", "Статус", "Алгоритм", "Последнее изменение"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        # === Панель управления версиями ===
        control_layout = QHBoxLayout()
        label_btn = QPushButton("Количество версий:")
        label_btn.setEnabled(False)
        control_layout.addWidget(label_btn)

        self.version_combo = QComboBox()
        self.version_combo.addItems([str(i) for i in range(1, 11)])
        self.version_combo.setCurrentText(str(self.max_versions))
        self.version_combo.currentTextChanged.connect(self.change_max_versions)
        control_layout.addWidget(self.version_combo)

        layout.addLayout(control_layout)

        # === Кнопки управления ===
        btn_layout = QHBoxLayout()

        buttons = [
            ("Добавить файл", self.add_file_dialog),
            ("Проверить все", self.check_all_files),
            ("Восстановить версию", self.restore_file_dialog),
            ("Детали изменений", self.show_file_versions),
            ("Редактировать", self.edit_file_dialog),  # <-- новая кнопка
            ("Экспорт отчёта", self.export_report)
        ]
        for text, func in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(func)
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # === Drag & Drop ===
        self.setAcceptDrops(True)
        self.table.setAcceptDrops(True)

        def table_drag_enter(event):
            print("[DragDrop] dragEnterEvent on table")
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                self.setStyleSheet("background-color: #2c2c2c; border: 2px dashed #00c853;")
            else:
                event.ignore()

        def table_drop(event):
            print("[DragDrop] dropEvent on table")
            self.setStyleSheet("")
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                for url in event.mimeData().urls():
                    path = url.toLocalFile()
                    if os.path.isfile(path):
                        print(f"[DragDrop] Получен файл: {path}")
                        self.add_file_from_path(path)
            else:
                event.ignore()

        self.table.dragEnterEvent = table_drag_enter
        self.table.dropEvent = table_drop

    def change_max_versions(self, value):
        """Меняет количество сохраняемых версий и чистит лишние"""
        import json
        from app.models import FileRecord, FileVersion

        self.max_versions = int(value)
        QMessageBox.information(self, "Настройка", f"Теперь будет храниться до {self.max_versions} версий файлов.")

        # Сохраняем в settings.json
        try:
            with open("settings.json", "w") as f:
                json.dump({"max_versions": self.max_versions}, f)
        except Exception as e:
            print(f"[Ошибка сохранения настроек]: {e}")

        # Обновляем FileWatcher, если запущен
        if self.watcher:
            self.watcher.max_versions = self.max_versions
            self.watcher.backup_manager.max_versions = self.max_versions

        # Удаляем лишние старые версии
        session = SessionLocal()
        files = session.query(FileRecord).all()

        for file in files:
            versions = (
                session.query(FileVersion)
                .filter(FileVersion.file_id == file.id)
                .order_by(FileVersion.created_at.desc())
                .all()
            )
            if len(versions) > self.max_versions:
                for old_version in versions[self.max_versions:]:
                    try:
                        session.delete(old_version)
                    except Exception as e:
                        print(f"[Ошибка удаления старой версии {old_version.id}]: {e}")

        session.commit()
        session.close()

    def load_files(self):
        self.table.setRowCount(0)
        files = self.db.query(FileRecord).all()

        for file in files:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(file.id)))
            self.table.setItem(row, 1, QTableWidgetItem(file.name))
            self.table.setItem(row, 2, QTableWidgetItem(file.path))
            self.table.setItem(row, 3, QTableWidgetItem(file.status))
            self.table.setItem(row, 4, QTableWidgetItem(file.algorithm))

            # Добавляем колонку "Последнее изменение"
            last_version = self.db.query(FileVersion).filter(FileVersion.file_id == file.id) \
                .order_by(FileVersion.created_at.desc()).first()
            if last_version:
                last_change = last_version.created_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                last_change = file.updated_at.strftime("%Y-%m-%d %H:%M:%S")
            self.table.setItem(row, 5, QTableWidgetItem(last_change))

    def show_file_versions(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Внимание", "Выберите файл в таблице")
            return

        file_id = int(self.table.item(row, 0).text())
        file_record = self.db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if not file_record:
            QMessageBox.warning(self, "Ошибка", "Файл не найден в базе")
            return

        versions = self.db.query(FileVersion) \
            .filter(FileVersion.file_id == file_id) \
            .order_by(FileVersion.created_at.desc()) \
            .all()

        if not versions:
            QMessageBox.information(self, "Информация", "Нет сохранённых версий")
            return

        # Создаём окно со списком версий
        from PyQt5.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Версии файла: {file_record.name}")
        dialog.setGeometry(200, 200, 600, 300)
        layout = QVBoxLayout()

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["ID версии", "Дата создания", "Хэш", "Комментарий"])
        table.setRowCount(len(versions))

        for i, v in enumerate(versions):
            table.setItem(i, 0, QTableWidgetItem(str(v.id)))
            table.setItem(i, 1, QTableWidgetItem(v.created_at.strftime("%Y-%m-%d %H:%M:%S")))
            table.setItem(i, 2, QTableWidgetItem(v.version_hash))
            table.setItem(i, 3, QTableWidgetItem(v.comment or ""))

        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        dialog.setLayout(layout)
        dialog.exec_()

    from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout
    from PyQt5.QtGui import QFont, QDragEnterEvent, QDropEvent

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
        self.load_files()  # обновляем таблицу после изменений

    def add_file_dialog(self):
        """Открывает окно Drag & Drop для добавления файла."""
        dialog = FileDropDialog(self)
        dialog.exec_()

        if not dialog.file_path:
            return  # пользователь не добавил файл

        path = dialog.file_path
        name = os.path.basename(path)

        # Ввод пароля (опционально)
        password, ok = QInputDialog.getText(
            self, "Пароль", "Введите пароль для защиты (оставьте пустым если не нужен):"
        )
        if ok and password:
            password_hash = hash_password(password)
        else:
            password_hash = None

        # Выбор алгоритма
        alg_dialog = QInputDialog()
        alg_dialog.setComboBoxItems(["sha256", "sha512", "md5", "xxhash"])
        alg_dialog.setWindowTitle("Выберите алгоритм")
        alg_dialog.setLabelText("Алгоритм хэширования:")
        if alg_dialog.exec_() == QInputDialog.Accepted:
            algorithm = alg_dialog.textValue()
        else:
            algorithm = "sha256"

        # Добавляем файл в БД
        from app.services.file_manager import add_file
        try:
            add_file(path, algorithm, password_hash)
            QMessageBox.information(self, "Успех", f"Файл {name} добавлен")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

        self.load_files()

    def add_file_from_path(self, path: str):
        """Добавляет файл, переданный напрямую (например, через Drag & Drop)."""
        name = os.path.basename(path)

        # Ввод пароля (опционально)
        password, ok = QInputDialog.getText(self, "Пароль",
                                            "Введите пароль для защиты (оставьте пустым если не нужен):")
        if ok and password:
            password_hash = hash_password(password)
        else:
            password_hash = None

        # Выбор алгоритма
        alg_dialog = QInputDialog()
        alg_dialog.setComboBoxItems(["sha256", "sha512", "md5", "xxhash"])
        alg_dialog.setWindowTitle("Выберите алгоритм")
        alg_dialog.setLabelText("Алгоритм хэширования:")
        if alg_dialog.exec_() == QInputDialog.Accepted:
            algorithm = alg_dialog.textValue()
        else:
            algorithm = "sha256"

        # Добавляем файл в БД
        from app.services.file_manager import add_file
        try:
            add_file(path, algorithm, password_hash)
            QMessageBox.information(self, "Успех", f"Файл {name} добавлен")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

        self.load_files()

    def dragEnterEvent(self, event):
        """Разрешаем перетаскивание файлов в окно."""
        print("[DragDrop] dragEnterEvent (main window)")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("background-color: #2c2c2c; border: 2px dashed #00c853;")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        """Сбрасываем стиль при уходе курсора."""
        self.setStyleSheet("")

    def dropEvent(self, event):
        """Обрабатываем перетаскивание файлов в окно."""
        print("[DragDrop] dropEvent (main window)")
        self.setStyleSheet("")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.isfile(path):
                    print(f"[DragDrop] Получен файл: {path}")
                    self.add_file_from_path(path)
        else:
            event.ignore()

    def check_all_files(self):
        files = self.db.query(FileRecord).all()
        results = []
        for file in files:
            status = check_file_integrity(self.db, file.id)
            results.append(f"{file.name}: {status}")
        QMessageBox.information(self, "Проверка завершена", "\n".join(results))
        self.load_files()

    def restore_file_dialog(self):
        import glob
        import os
        import shutil
        from datetime import datetime
        from app.services.backup_manager import get_last_versions
        from app.services.security import compute_hash
        from app.models import FileRecord, LogEntry

        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Внимание", "Выберите файл в таблице")
            return

        file_id = int(self.table.item(row, 0).text())

        # Получаем запись о файле из БД (если есть)
        file_record = self.db.query(FileRecord).filter(FileRecord.id == file_id).first()
        if file_record:
            desired_basename = os.path.basename(file_record.path)
            default_restore_path = file_record.path
        else:
            # Если нет записи (крайний случай) - используем шаблон только по id
            desired_basename = None
            default_restore_path = None

        # Берём доступные версии из БД
        versions = get_last_versions(self.db, file_id)
        if not versions:
            QMessageBox.information(self, "Информация", "Нет доступных резервных версий")
            return

        # Формируем список для выбора
        items = [f"{v.created_at} | {v.comment or ''}" for v in versions]
        item, ok = QInputDialog.getItem(self, "Выберите версию", "Версия:", items, editable=False)
        if not (ok and item):
            return

        idx = items.index(item)
        version = versions[idx]

        # Ищем резервную копию на диске по шаблону
        backup_root = "/Users/macbook/backups"  # можно вынести в константу
        # если знаем basename — ищем точнее, иначе ищем по id
        if desired_basename:
            pattern = os.path.join(backup_root, f"{file_id}_*_{desired_basename}")
        else:
            pattern = os.path.join(backup_root, f"{file_id}_*")
        matching_files = sorted(glob.glob(pattern), reverse=True)

        # Попытка точечно найти по timestamp (если совпадает с версией)
        ts_str = version.created_at.strftime("%Y%m%d%H%M%S")
        specific_pattern = os.path.join(backup_root, f"{file_id}_{ts_str}_*")
        specific_matches = sorted(glob.glob(specific_pattern))
        if specific_matches:
            # если есть точные по времени — используем их (предпочтительнее)
            backup_path = specific_matches[0]
        elif matching_files:
            # иначе используем первый результат поиска
            backup_path = matching_files[0]
        else:
            QMessageBox.warning(
                self,
                "Ошибка",
                f"Резервные копии для файла с ID={file_id} не найдены в:\n{backup_root}\n(шаблон: {pattern})"
            )
            return

        # Предложим восстановить в исходный путь или выбрать вручную
        if default_restore_path:
            # спросим, куда восстановить: в исходное место или выбрать вручную
            choice = QMessageBox.question(
                self,
                "Куда восстановить?",
                f"Найдена копия:\n{os.path.basename(backup_path)}\n\n"
                f"Восстановить в исходный путь?\n{default_restore_path}\n\n"
                "Нажмите Да — восстановить в исходный путь, Нет — выбрать место вручную.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if choice == QMessageBox.Yes:
                restore_path = default_restore_path
            else:
                # пользователь выбирает место/имя для восстановления
                restore_path, _ = QFileDialog.getSaveFileName(self, "Куда восстановить файл", desired_basename or "")
                if not restore_path:
                    return
        else:
            # если исходный путь неизвестен — даём выбрать
            restore_path, _ = QFileDialog.getSaveFileName(self, "Куда восстановить файл", os.path.basename(backup_path))
            if not restore_path:
                return

        try:
            # Создаём директорию назначения, если нужно
            restore_dir = os.path.dirname(restore_path)
            if restore_dir and not os.path.exists(restore_dir):
                os.makedirs(restore_dir, exist_ok=True)

            # Копируем резервную копию на место
            shutil.copy2(backup_path, restore_path)

            # Пересчитываем хэш восстановленного файла и обновляем БД (если есть запись)
            if file_record:
                try:
                    new_hash = compute_hash(restore_path, file_record.algorithm)
                except Exception:
                    new_hash = None

                if new_hash:
                    file_record.current_hash = new_hash
                file_record.updated_at = datetime.utcnow()
                # если путь изменился (например, пользователь восстановил в другую папку),
                # можно обновить запись или оставить как есть — тут оставим исходный путь без изменения
                self.db.commit()

                # добавим запись в логи (если есть модель LogEntry)
                try:
                    from app.models import LogEntry
                    log = LogEntry(action="restore", file_name=file_record.name, result=f"restored to {restore_path}",
                                   user_name=None)
                    self.db.add(log)
                    self.db.commit()
                except Exception:
                    # не фатально — просто пропустим лог, если что-то пойдёт не так
                    pass

            QMessageBox.information(self, "Успех", f"Файл восстановлен:\n{restore_path}\nИз копии:\n{backup_path}")
            self.load_files()

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось восстановить файл:\n{e}")
            return

    from app.services.reporter import Reporter

    def export_report(self):
        # Выбор формата и пути
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить отчёт",
            "report",
            "CSV Files (*.csv);;JSON Files (*.json);;PDF Files (*.pdf)"
        )
        if not path:
            return

        # Определяем формат по расширению
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".csv":
                # CSV можно сделать через простую конвертацию
                self.export_csv(path)
                QMessageBox.information(self, "Экспорт", f"CSV отчёт сохранён: {path}")
            elif ext == ".json":
                Reporter.export_json(self.db, path)
                Reporter.log_export(self.db, "json", path)
                QMessageBox.information(self, "Экспорт", f"JSON отчёт сохранён: {path}")
            elif ext == ".pdf":
                Reporter.export_pdf(self.db, path)
                Reporter.log_export(self.db, "pdf", path)
                QMessageBox.information(self, "Экспорт", f"PDF отчёт сохранён: {path}")
            else:
                QMessageBox.warning(self, "Ошибка", "Неподдерживаемый формат")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def export_csv(self, path: str):
        """
        Простая генерация CSV отчёта по логам.
        """
        import csv
        from app.models import LogEntry

        logs = self.db.query(LogEntry).all()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Action", "File Name", "Result", "User"])
            for log in logs:
                writer.writerow([
                    log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    log.action,
                    log.file_name or "-",
                    log.result,
                    log.user_name or "-"
                ])


if __name__ == "__main__":

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # FileWatcher с обновлением GUI
    window.watcher = FileWatcher(main_window=window, interval=10, max_versions=window.max_versions)
    window.watcher.start()

    sys.exit(app.exec_())
