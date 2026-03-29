#!/usr/bin/env python3
"""
Простой тест DeleteFileThread без зависимости от существующего контейнера
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, '/Users/macbook/PycharmProjects/cryptobase')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, QTimer
from app.services.DeleteFileThread import DeleteFileThread
from app.services.backup_container import BackupContainer

def test_delete_thread_basic():
    """Базовый тест DeleteFileThread"""
    print("=== Базовый тест DeleteFileThread ===")
    
    app = QApplication(sys.argv)
    
    try:
        # Создаем временную директорию для тестов
        temp_dir = tempfile.mkdtemp()
        print(f"✓ Создана временная директория: {temp_dir}")
        
        # Создаем временный файл для контейнера
        container_path = os.path.join(temp_dir, "test_backups.enc")
        
        # Создаем мастер-ключ для теста
        master_key = b"0123456789abcdef0123456789abcdef"
        
        # Создаем новый контейнер
        os.environ['CRYPTOBASE_CONTAINER_PATH'] = container_path
        
        # Создаем контейнер с тестовыми данными
        container = BackupContainer(master_key)
        
        # Добавляем тестовые данные в контейнер
        test_file_id = "123"
        test_version_data = {
            "created_at": "2023-01-01T00:00:00",
            "comment": "Test version",
            "content": "48656c6c6f20576f726c64"  # "Hello World" в hex
        }
        
        container.add_version(test_file_id, test_version_data)
        print("✓ Добавлены тестовые данные в контейнер")
        
        # Проверяем, что данные есть
        versions = container.get_all_versions(test_file_id)
        print(f"✓ Версий в контейнере: {len(versions)}")
        
        # Создаем DeleteFileThread
        delete_thread = DeleteFileThread(
            file_id=123,  # Используем числовой ID
            delete_original=False,
            container=container
        )
        
        # Подключаем сигналы
        def on_finished(success, message):
            print(f"Сигнал finished: success={success}, message={message}")
            if success:
                print("✓ Удаление завершено успешно")
            else:
                print(f"✗ Ошибка удаления: {message}")
            
            # Проверяем результаты после завершения
            container_after = BackupContainer(master_key)
            versions_after = container_after.get_all_versions(test_file_id)
            print(f"Версий в контейнере после удаления: {len(versions_after)}")
            
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
        QTimer.singleShot(50, test_cancel)  # Отмена через 50мс
        
        # Запускаем приложение
        app.exec_()
        
        # Очистка
        shutil.rmtree(temp_dir)
        print("✓ Временная директория удалена")
        
        print("\n=== Тест завершен ===")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_delete_thread_signals():
    """Тест сигналов DeleteFileThread"""
    print("\n=== Тест сигналов DeleteFileThread ===")
    
    try:
        # Проверяем наличие сигнала finished
        from PyQt5.QtCore import pyqtSignal
        
        if hasattr(DeleteFileThread, 'finished'):
            print("✓ Сигнал finished присутствует")
        else:
            print("✗ Сигнал finished отсутствует")
            return False
        
        # Проверяем наличие метода cancel
        if hasattr(DeleteFileThread, 'cancel'):
            print("✓ Метод cancel присутствует")
        else:
            print("✗ Метод cancel отсутствует")
            return False
        
        print("✓ Все необходимые атрибуты присутствуют")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте сигналов: {e}")
        return False

if __name__ == "__main__":
    print("Запуск тестов DeleteFileThread...")
    
    # Тест 1: Проверка сигналов
    test1_success = test_delete_thread_signals()
    
    # Тест 2: Базовый тест функциональности
    test2_success = test_delete_thread_basic()
    
    overall_success = test1_success and test2_success
    
    print(f"\n=== Результаты ===")
    print(f"Тест сигналов: {'✓' if test1_success else '✗'}")
    print(f"Базовый тест: {'✓' if test2_success else '✗'}")
    print(f"Общий результат: {'✓ УСПЕХ' if overall_success else '✗ НЕУДАЧА'}")
    
    sys.exit(0 if overall_success else 1)
