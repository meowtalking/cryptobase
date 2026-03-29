#!/usr/bin/env python3
"""
Тест интеграции UI компонентов с DeleteFileThread
"""
import sys
import os
from unittest.mock import MagicMock, patch

# Добавляем путь к проекту
sys.path.insert(0, '/Users/macbook/PycharmProjects/cryptobase')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject

def test_ui_components():
    """Тест UI компонентов"""
    print("=== Тест UI компонентов ===")
    
    app = QApplication(sys.argv)
    
    try:
        # Тест 1: LocalStoragePage
        print("Тест LocalStoragePage...")
        from app.ui.local_storage_page import LocalStoragePage
        
        # Создаем мок для main_window
        mock_main_window = MagicMock()
        mock_main_window.master_key = b"0123456789abcdef0123456789abcdef"
        
        # Создаем LocalStoragePage
        with patch('app.ui.local_storage_page.SessionLocal'):
            storage_page = LocalStoragePage(mock_main_window)
            
            # Проверяем наличие новых методов
            assert hasattr(storage_page, '_start_file_deleting_process'), "Метод _start_file_deleting_process отсутствует"
            assert hasattr(storage_page, '_on_file_deleted'), "Метод _on_file_deleted отсутствует"
            
            print("✓ LocalStoragePage создан успешно")
            print("✓ Все необходимые методы присутствуют")
        
        # Тест 2: FileEditDialog
        print("\nТест FileEditDialog...")
        from app.services.FileEditDialog import FileEditDialog
        from app.models import FileRecord
        
        # Создаем мок для file_record
        mock_file_record = MagicMock(spec=FileRecord)
        mock_file_record.id = 123
        mock_file_record.name = "test.txt"
        mock_file_record.password_hash = None
        
        # Создаем FileEditDialog
        with patch('app.services.FileEditDialog.SessionLocal'):
            dialog = FileEditDialog(None, mock_file_record, master_key=b"0123456789abcdef")
            
            # Проверяем наличие новых методов
            assert hasattr(dialog, '_start_version_deleting_process'), "Метод _start_version_deleting_process отсутствует"
            assert hasattr(dialog, '_on_version_deleted'), "Метод _on_version_deleted отсутствует"
            assert hasattr(dialog, '_start_file_deleting_process'), "Метод _start_file_deleting_process отсутствует"
            assert hasattr(dialog, 'delete_version'), "Метод delete_version отсутствует"
            assert hasattr(dialog, 'delete_file'), "Метод delete_file отсутствует"
            
            print("✓ FileEditDialog создан успешно")
            print("✓ Все необходимые методы присутствуют")
        
        print("\n=== Тест завершен ===")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_imports():
    """Тест импортов"""
    print("\n=== Тест импортов ===")
    
    try:
        # Тестируем все основные импорты
        from app.services.DeleteFileThread import DeleteFileThread
        from app.ui.local_storage_page import LocalStoragePage
        from app.services.FileEditDialog import FileEditDialog
        
        print("✓ DeleteFileThread импортирован")
        print("✓ LocalStoragePage импортирован")
        print("✓ FileEditDialog импортирован")
        
        # Проверяем PyQt5 импорты
        from PyQt5.QtWidgets import QProgressDialog
        from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
        
        print("✓ PyQt5 компоненты импортированы")
        
        return True
        
    except Exception as e:
        print(f"✗ Ошибка импорта: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Запуск тестов UI интеграции...")
    
    # Тест 1: Импорты
    test1_success = test_imports()
    
    # Тест 2: UI компоненты
    test2_success = test_ui_components()
    
    overall_success = test1_success and test2_success
    
    print(f"\n=== Результаты ===")
    print(f"Тест импортов: {'✓' if test1_success else '✗'}")
    print(f"Тест UI компонентов: {'✓' if test2_success else '✗'}")
    print(f"Общий результат: {'✓ УСПЕХ' if overall_success else '✗ НЕУДАЧА'}")
    
    sys.exit(0 if overall_success else 1)
