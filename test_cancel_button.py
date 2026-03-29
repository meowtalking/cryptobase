#!/usr/bin/env python3
"""
Тест кнопки "Отмена" в диалоге сохранения версий
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

def test_cancel_button():
    """Тест кнопки 'Отмена' в диалоге сохранения версий"""
    print("=== Тест кнопки 'Отмена' в диалоге сохранения версий ===")
    
    app = QApplication(sys.argv)
    
    try:
        # Создаем мок для file_record с паролем
        mock_file_record = MagicMock(spec=FileRecord)
        mock_file_record.id = 123
        mock_file_record.name = "test.txt"
        mock_file_record.path = "/tmp/test.txt"
        mock_file_record.password_hash = "hashed_password"  # Файл с паролем
        
        # Создаем FileEditDialog
        with patch('app.services.FileEditDialog.SessionLocal'):
            dialog = FileEditDialog(None, mock_file_record, master_key=b"0123456789abcdef")
            
            print("✓ FileEditDialog создан успешно")
            
            # Тест: Нажатие кнопки "Отмена" в диалоге сохранения версий
            print("Тест: Нажатие кнопки 'Отмена' в диалоге сохранения версий")
            
            mock_msgbox = MagicMock()
            mock_input = MagicMock()
            mock_filedialog = MagicMock()
            mock_container = MagicMock()
            
            with patch('app.services.FileEditDialog.QMessageBox', mock_msgbox):
                with patch('app.services.FileEditDialog.verify_password_for_db', return_value=True):
                    with patch('app.services.FileEditDialog.QInputDialog', mock_input):
                        with patch('app.services.FileEditDialog.QFileDialog', mock_filedialog):
                            with patch('app.services.FileEditDialog.BackupContainer', mock_container):
                                # Настраиваем моки
                                mock_container_instance = MagicMock()
                                mock_container_instance.get_all_versions.return_value = [
                                    {"created_at": "2023-01-01T00:00:00", "comment": "test", "content": "48656c6c6f"}
                                ]
                                mock_container.return_value = mock_container_instance
                                
                                # Сценарий: Пользователь выбирает "Нет" (не удалять оригинал),
                                # затем нажимает "Отмена" в диалоге сохранения версий
                                mock_msgbox.question.side_effect = [QMessageBox.No, QMessageBox.Cancel]
                                mock_input.getText.return_value = ("test_password", True)
                                
                                # Вызываем delete_file
                                dialog.delete_file()
                                
                                # Проверяем, что QMessageBox.question был вызван дважды
                                assert mock_msgbox.question.call_count == 2, "Ожидалось 2 вызова question"
                                
                                # Проверяем, что был показан диалог об отмене
                                assert mock_msgbox.information.called, "Ожидался вызов information об отмене"
                                info_call = mock_msgbox.information.call_args
                                assert info_call[0][1] == "Отмена", "Неверный заголовок диалога"
                                assert info_call[0][2] == "Операция удаления отменена", "Неверное сообщение об отмене"
                                
                                # Проверяем, что QFileDialog не был вызван (пользователь отменил раньше)
                                assert not mock_filedialog.getExistingDirectory.called, "QFileDialog не должен был вызываться"
                                assert not mock_input.getText.called, "QInputDialog не должен был вызываться"
                                
                                print("✓ Правильная обработка кнопки 'Отмена' в диалоге сохранения версий")
            
            # Тест: Проверка наличия кнопки Cancel в диалоге
            print("Тест: Проверка наличия кнопки Cancel в коде")
            
            import inspect
            source = inspect.getsource(dialog.delete_file)
            
            # Проверяем наличие кнопки Cancel в коде
            assert "QMessageBox.Cancel" in source, "Кнопка Cancel отсутствует в коде"
            assert "restore == QMessageBox.Cancel" in source, "Обработка кнопки Cancel отсутствует"
            assert "Операция удаления отменена" in source, "Сообщение об отмене отсутствует"
            
            print("✓ Кнопка 'Отмена' добавлена в диалог сохранения версий")
            print("✓ Обработка кнопки 'Отмена' реализована")
        
        print("\n=== Все тесты пройдены ===")
        return True
        
    except Exception as e:
        print(f"✗ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Запуск теста кнопки 'Отмена'...")
    
    success = test_cancel_button()
    
    print(f"\n=== Результат ===")
    print(f"Тест кнопки 'Отмена': {'✓ УСПЕХ' if success else '✗ НЕУДАЧА'}")
    
    sys.exit(0 if success else 1)
