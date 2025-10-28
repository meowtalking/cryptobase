import os
import json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from app.models import LogEntry

class Reporter:
    @staticmethod
    def export_json(db, path: str, start_date=None, end_date=None, file_name=None, status=None):
        """
        Экспорт логов в JSON с фильтрацией.
        """
        query = db.query(LogEntry)
        if start_date:
            query = query.filter(LogEntry.timestamp >= start_date)
        if end_date:
            query = query.filter(LogEntry.timestamp <= end_date)
        if file_name:
            query = query.filter(LogEntry.file_name == file_name)
        if status:
            query = query.filter(LogEntry.result == status)

        logs = query.all()
        data = []
        for log in logs:
            data.append({
                "timestamp": log.timestamp.isoformat(),
                "action": log.action,
                "file_name": log.file_name,
                "result": log.result,
                "user_name": log.user_name
            })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @staticmethod
    def export_pdf(db, path: str, start_date=None, end_date=None, file_name=None, status=None):
        """
        Генерация PDF отчета с логами.
        """
        query = db.query(LogEntry)
        if start_date:
            query = query.filter(LogEntry.timestamp >= start_date)
        if end_date:
            query = query.filter(LogEntry.timestamp <= end_date)
        if file_name:
            query = query.filter(LogEntry.file_name == file_name)
        if status:
            query = query.filter(LogEntry.result == status)

        logs = query.all()
        c = canvas.Canvas(path, pagesize=A4)
        width, height = A4
        margin = 50
        y = height - margin

        c.setFont("Helvetica-Bold", 16)
        c.drawString(margin, y, "Отчет CryptoBase")
        y -= 30

        c.setFont("Helvetica", 12)
        for log in logs:
            line = f"{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | {log.action} | {log.file_name or '-'} | {log.result} | {log.user_name or '-'}"
            c.drawString(margin, y, line)
            y -= 20
            if y < margin:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = height - margin

        c.save()

    @staticmethod
    def log_export(db, report_type: str, path: str):
        """
        Логирование действия экспорта отчета.
        """
        from app.models import LogEntry
        log = LogEntry(
            action=f"export_{report_type}",
            file_name=None,
            result=f"Exported to {path}",
            user_name=None,
            timestamp=datetime.utcnow()
        )
        db.add(log)
        db.commit()
