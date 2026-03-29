#!/usr/bin/env python3
"""
Простой тест кнопки "Отмена" в диалоге сохранения версий
"""
import sys
import os
from unittest.mock import MagicMock, patch

# Добавляем путь к проекту
sys.path.insert(0, '/Users/macbook/PycharmProjects/cryptobase')

from PyQt5.QtWidgets import QApplication, QMessageBox, QLineEdit
from PyQt5.QtCore import Qt
from app.services.FileEditDialog import FileEditDialog
from app.models import FileRecord

def test_cancel_button_simple():
    """Простой тест кнопки 'Отмена' в диалоге сохранения версий"""
    print("=== Простой тест кнопки 'Отмена' ===")
    
    app = QApplication(sys.argv)
    
    try:
        # Создаем мок для file_record
        mock_file_record = MagicMock(spec=FileRecord)
        mock_file_record.id = 123
        mock_file_record.name = "test.txt"
        mock_file_record.path = "/tmp/test.txt"
        mock_file_record.password_hash = "hashed_password"
        
        # Создаем FileEditDialog
        with patch('app.services.FileEditDialog.SessionLocal'):
            dialog = FileEditDialog(None, mock_file_record, master_key=b"0123456789abcdef")
            
            print("✓ FileEditDialog создан успешно")
            
            # Проверяем исходный код метода delete_file
            import inspect
            source = inspect.getsource(dialog.delete_file)
            
            # Проверяем наличие кнопки Cancel в коде
            checks = [
                ("QMessageBox.Cancel" in source, "Кнопка Cancel добавлена в диалог"),
                ("restore == QMessageBox.Cancel" in source, "Обработка кнопки Cancel реализована"),
                ("Операция удаления отменена" in source, "Сообщение об отмене присутствует"),
                ("if restore == QMessageBox.Cancel:" in source, "Условие для отмены корректное"),
            ]
            
            all_passed = True
            for check, description in checks:
                if check:
                    print(f"✓ {description}")
                else:
                    print(f"✗ {description}")
                    all_passed = False
            
            # Выводим фрагмент кода с кнопкой Cancel
            print("\n--- Фрагмент кода с кнопкой 'Отмена' ---")
            lines = source.split('\n')
            for i, line in enumerate(lines):
                if 'QMessageBox.Cancel' in line:
                    start = max(0, i-1)
                    end = min(len(lines), i+6)
                    for j in range(start, end):
                        marker = ">>> " if j == i else "    "
                        print(f"{marker}{j+1}: {lines[j]}")
                    break
            
            # Проверяем, что диалог имеет правильные кнопки
            print("\n--- Проверка кнопок диалога ---")
            dialog_line = None
            for line in lines:
                if 'Сохранение версий перед удалением' in line:
                    dialog_line = line
                    break
            
            if dialog_line:
                print(f"Найден диалог: {dialog_line.strip()}")
                # Ищем строку с кнопками
                for i, line in enumerate(lines):
                    if dialog_line == line and i+1 < len(lines):
                        next_line = lines[i+1]
                        if 'QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel' in next_line:
                            print("✓ Кнопки диалога: Yes | No | Cancel")
                            break
                        elif 'QMessageBox.Yes | QMessageBox.No' in next_line:
                            print("✗ Кнопки диалога: только Yes | No (Cancel отсутствует)")
                            all_passed = False
                            break
            else:
                print("✗ Диалог сохранения версий не найден")
                all_passed = False
            
            print(f"\n=== Результат проверки ===")
            if all_passed:
                print("✓ Все проверки пройдены - кнопка 'Отмена' корректно добавлена")
                return True
            else:
                print("✗ Некоторые проверки не пройдены")
                return False
        
    except Exception as e:
        print(f"✗ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Запуск простого теста кнопки 'Отмена'...")
    
    success = test_cancel_button_simple()
    
    print(f"\n=== Итоговый результат ===")
    print(f"Тест кнопки 'Отмена': {'✓ УСПЕХ' if success else '✗ НЕУДАЧА'}")
    
    sys.exit(0 if success else 1)
