import json
from datetime import datetime, timezone, timedelta
from app.models import LogEntry, FileRecord, FileVersion
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from pathlib import Path
from datetime import timezone, timedelta
class Reporter:
    @staticmethod
    def export_json(db, path: str, max_versions=5):
        files = db.query(FileRecord).all()
        data = []
        for file in files:
            versions = db.query(FileVersion) \
                .filter(FileVersion.file_id == file.id) \
                .order_by(FileVersion.created_at.desc()) \
                .limit(max_versions) \
                .all()
            data.append({
                "id": file.id,
                "name": file.name,
                "path": file.path,
                "status": getattr(file, "status", "OK"),
                "algorithm": file.algorithm,
                "versions": [
                    {
                        "created_at": v.created_at.isoformat(),
                        "comment": v.comment,
                        "user": v.user_name or "-"
                    } for v in versions
                ]
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    @staticmethod
    def export_pdf(db, path: str):
        from app.models import LogEntry

        logs = db.query(LogEntry).order_by(LogEntry.timestamp).all()

        # --- Шрифт для кириллицы ---
        font_path = '/Users/macbook/PycharmProjects/cryptobase/app/services/fonts/DejaVuSans.ttf'
        if not font_path:
            raise FileNotFoundError(f"Шрифт не найден: {font_path}")
        pdfmetrics.registerFont(TTFont('DejaVuSans', str(font_path)))

        # --- Создаем PDF ---
        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
        elements = []

        # Стиль для таблицы с переносом текста
        styles = getSampleStyleSheet()
        para_style = ParagraphStyle(
            'table_cell',
            parent=styles['Normal'],
            fontName='DejaVuSans',
            fontSize=10,
            leading=12,  # расстояние между строками
        )

        # Заголовок
        header_style = ParagraphStyle(
            'header',
            parent=styles['Heading1'],
            fontName='DejaVuSans',
            fontSize=16,
            leading=18,
            alignment=1  # по центру
        )
        elements.append(Paragraph("Отчёт CryptoBase", header_style))
        elements.append(Spacer(1, 12))

        # Таблица
        data = [["Дата/Время", "Действие", "Файл", "Результат", "Пользователь"]]

        moscow_tz = timezone(timedelta(hours=3))
        for log in logs:
            local_time = log.timestamp.replace(tzinfo=timezone.utc).astimezone(moscow_tz)
            data.append([
                Paragraph(local_time.strftime("%Y-%m-%d %H:%M:%S"), para_style),
                Paragraph(log.action or "-", para_style),
                Paragraph(log.file_name or "-", para_style),
                Paragraph(log.result or "-", para_style),
                Paragraph(log.user_name or "-", para_style),
            ])

        # Ширина колонок под любые длинные тексты
        col_widths = [100, 120, 180, 100, 100]
        table = Table(data, colWidths=col_widths, repeatRows=1)

        table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'DejaVuSans', 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))

        elements.append(table)
        doc.build(elements)

    @staticmethod
    def export_csv(self, path: str, max_versions=5):
        import csv
        files = self.db.query(FileRecord).all()  # используем self.db

        # Заголовки
        headers = ["ID", "Имя файла", "Путь", "Статус", "Алгоритм"]
        for i in range(1, max_versions + 1):
            headers.append(f"Версия {i} (Дата и комментарий)")
            headers.append(f"Версия {i} (Кто изменил)")

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

            for file in files:
                versions = self.db.query(FileVersion) \
                    .filter(FileVersion.file_id == file.id) \
                    .order_by(FileVersion.created_at.desc()) \
                    .limit(max_versions) \
                    .all()
                row = [file.id, file.name, file.path, getattr(file, "status", "OK"), file.algorithm]

                for v in versions:
                    row.append(f"{v.created_at.strftime('%Y-%m-%d %H:%M:%S')} ({v.comment})")
                    row.append(v.user_name or "-")  # кто изменил

                row += ["", ""] * (max_versions - len(versions))
                writer.writerow(row)


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
