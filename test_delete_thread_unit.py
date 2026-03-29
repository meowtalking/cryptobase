#!/usr/bin/env python3
"""
Unit тест для DeleteFileThread с мок-объектами
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

# Добавляем путь к проекту
sys.path.insert(0, '/Users/macbook/PycharmProjects/cryptobase')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QThread, QTimer
from app.services.DeleteFileThread import DeleteFileThread

def test_delete_thread_unit():
    """Unit тест DeleteFileThread с мок-объектами"""
    print("=== Unit тест DeleteFileThread ===")
    
    app = QApplication(sys.argv)
    
    try:
        # Создаем мок-контейнер
        mock_container = MagicMock()
        mock_container.data = {"files": {"123": [{"created_at": "2023-01-01T00:00:00", "comment": "test"}]}}
        mock_container.get_all_versions.return_value = [{"created_at": "2023-01-01T00:00:00", "comment": "test"}]
        mock_container._save.return_value = None
        
        # Создаем мок-сессию БД
        mock_session = MagicMock()
        mock_file_record = MagicMock()
        mock_file_record.name = "test_file.txt"
        mock_file_record.path = "/tmp/test_file.txt"
        
        # Мокируем SessionLocal
        with patch('app.services.DeleteFileThread.SessionLocal', return_value=mock_session):
            mock_session.query.return_value.filter.return_value.first.return_value = mock_file_record
            mock_session.query.return_value.filter.return_value.delete.return_value = 1
            mock_session.delete.return_value = None
            mock_session.commit.return_value = None
            mock_session.add.return_value = None
            mock_session.close.return_value = None
            
            # Создаем DeleteFileThread
            delete_thread = DeleteFileThread(
                file_id=123,
                delete_original=False,
                container=mock_container
            )
            
            # Подключаем сигналы
            results = {"success": False, "message": "", "finished": False}
            
            def on_finished(success, message):
                print(f"Сигнал finished: success={success}, message={message}")
                results["success"] = success
                results["message"] = message
                results["finished"] = True
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
        
        # Проверяем результаты
        print("\n=== Проверка результатов ===")
        if results["finished"]:
            print("✓ Операция завершена")
            if results["success"]:
                print("✓ Удаление успешно")
            else:
                print(f"✓ Отмена сработала: {results['message']}")
        else:
            print("✗ Операция не завершена")
            return False
        
        print("\n=== Тест завершен ===")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_delete_thread_methods():
    """Тест методов DeleteFileThread"""
    print("\n=== Тест методов DeleteFileThread ===")
    
    try:
        # Создаем мок-контейнер
        mock_container = MagicMock()
        
        # Создаем DeleteFileThread
        delete_thread = DeleteFileThread(
            file_id=123,
            delete_original=False,
            container=mock_container
        )
        
        # Проверяем атрибуты
        assert delete_thread.file_id == 123
        assert delete_thread.delete_original == False
        assert delete_thread.container == mock_container
        assert delete_thread._cancel_requested == False
        
        print("✓ Атрибуты инициализированы правильно")
        
        # Проверяем метод cancel
        delete_thread.cancel()
        assert delete_thread._cancel_requested == True
        print("✓ Метод cancel работает")
        
        # Проверяем наличие сигнала
        if hasattr(delete_thread, 'finished'):
            print("✓ Сигнал finished присутствует")
        else:
            print("✗ Сигнал finished отсутствует")
            return False
        
        print("✓ Все проверки пройдены")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте методов: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Запуск unit тестов DeleteFileThread...")
    
    # Тест 1: Проверка методов
    test1_success = test_delete_thread_methods()
    
    # Тест 2: Проверка функциональности с моками
    test2_success = test_delete_thread_unit()
    
    overall_success = test1_success and test2_success
    
    print(f"\n=== Результаты ===")
    print(f"Тест методов: {'✓' if test1_success else '✗'}")
    print(f"Unit тест: {'✓' if test2_success else '✗'}")
    print(f"Общий результат: {'✓ УСПЕХ' if overall_success else '✗ НЕУДАЧА'}")
    
    sys.exit(0 if overall_success else 1)
