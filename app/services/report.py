import csv
from sqlalchemy.orm import Session
from app.models import FileRecord, FileVersion, LogEntry

def export_report(db: Session, path: str):
    """Экспорт отчёта о файлах и последних версиях в CSV"""
    files = db.query(FileRecord).all()

    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["ID", "Имя файла", "Путь", "Статус", "Алгоритм", "Последние версии"])

        for file in files:
            versions = db.query(FileVersion).filter(FileVersion.file_id == file.id).order_by(FileVersion.created_at.desc()).limit(5).all()
            versions_str = "; ".join([f"{v.created_at} ({v.comment})" for v in versions])
            writer.writerow([file.id, file.name, file.path, getattr(file, "status", "OK"), file.algorithm, versions_str])
