#!/usr/bin/env python3
"""
Тест интеграции DeleteFileThread с UI компонентами
"""
import sys
import os
import tempfile
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, '/Users/macbook/PycharmProjects/cryptobase')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, QTimer
from app.services.DeleteFileThread import DeleteFileThread
from app.services.backup_container import BackupContainer
from app.services.file_manager_new import add_file_new
from app.db import SessionLocal
from app.models import FileRecord

def test_delete_thread_integration():
    """Тест интеграции DeleteFileThread"""
    print("=== Тест интеграции DeleteFileThread ===")
    
    app = QApplication(sys.argv)
    
    try:
        # Создаем временный файл для теста
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test content for deletion")
            test_file_path = f.name
        
        print(f"✓ Создан тестовый файл: {test_file_path}")
        
        # Создаем мастер-ключ для теста
        master_key = b"0123456789abcdef0123456789abcdef"
        
        # Добавляем файл в систему
        print("Добавляем файл в систему...")
        file_record = add_file_new(test_file_path, password=None, master_key=master_key)
        print(f"✓ Файл добавлен: {file_record.name} (ID: {file_record.id})")
        
        # Проверяем, что файл в БД
        session = SessionLocal()
        db_file = session.query(FileRecord).filter(FileRecord.id == file_record.id).first()
        session.close()
        
        if db_file:
            print("✓ Файл найден в БД")
        else:
            print("✗ Файл не найден в БД")
            return False
        
        # Создаем контейнер
        container = BackupContainer(master_key)
        
        # Проверяем, что файл в контейнере
        file_id_str = str(file_record.id)
        versions = container.get_all_versions(file_id_str)
        print(f"✓ Версий в контейнере: {len(versions)}")
        
        # Создаем DeleteFileThread
        delete_thread = DeleteFileThread(
            file_id=file_record.id,
            delete_original=False,  # Не удаляем оригинал
            container=container
        )
        
        # Подключаем сигналы
        def on_finished(success, message):
            print(f"Сигнал finished: success={success}, message={message}")
            if success:
                print("✓ Удаление завершено успешно")
            else:
                print(f"✗ Ошибка удаления: {message}")
            app.quit()
        
        def test_cancel():
            """Тест отмены операции"""
            print("Тест отмены операции...")
            delete_thread.cancel()
            print("✓ Отмена отправлена")
        
        delete_thread.finished.connect(on_finished)
        
        # Запускаем поток
        print("Запуск DeleteFileThread...")
        delete_thread.start()
        
        # Тестируем отмену через небольшую задержку
        QTimer.singleShot(100, test_cancel)  # Отмена через 100мс
        
        # Запускаем приложение
        app.exec_()
        
        # Проверяем результаты
        print("\n=== Проверка результатов ===")
        
        # Проверяем БД
        session = SessionLocal()
        db_file_after = session.query(FileRecord).filter(FileRecord.id == file_record.id).first()
        session.close()
        
        if db_file_after is None:
            print("✓ Файл удален из БД")
        else:
            print("✗ Файл все еще в БД (возможно, отмена сработала)")
        
        # Проверяем контейнер
        container_after = BackupContainer(master_key)
        versions_after = container_after.get_all_versions(file_id_str)
        print(f"Версий в контейнере после удаления: {len(versions_after)}")
        
        if len(versions_after) == 0:
            print("✓ Версии удалены из контейнера")
        else:
            print("✗ Версии все еще в контейнере (возможно, отмена сработала)")
        
        # Проверяем оригинальный файл
        if os.path.exists(test_file_path):
            print("✓ Оригинальный файл сохранен")
            os.unlink(test_file_path)  # Удаляем тестовый файл
        else:
            print("✗ Оригинальный файл удален")
        
        print("\n=== Тест завершен ===")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_delete_thread_integration()
    sys.exit(0 if success else 1)
