from app.services.file_manager import add_file
from app.services.integrity_manager import check_file, check_all_files

# Добавляем новый файл
file_info = add_file("/Users/macbook/Documents/код_бд.docx", "sha256")

# Проверяем этот файл
result = check_file(file_info["id"])
print(result)

# Проверяем все файлы
all_results = check_all_files()
print(all_results)
