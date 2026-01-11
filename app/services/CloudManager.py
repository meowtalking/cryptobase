import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google.oauth2.credentials import Credentials
import io

class CloudManager:
    def __init__(self, credentials_path="app/services/token.json"):
        if not os.path.exists(credentials_path):
            raise FileNotFoundError("Файл с токеном Google Drive не найден")

        creds = Credentials.from_authorized_user_file(credentials_path)
        self.service = build("drive", "v3", credentials=creds)

    # 📁 Получение списка файлов приложения
    def list_files(self):
        results = self.service.files().list(
            q="mimeType != 'application/vnd.google-apps.folder' and trashed = false",
            fields="files(id, name, mimeType, modifiedTime)"
        ).execute()
        return results.get("files", [])

    # ⬆️ Загрузка файла
    def upload_file(self, file_path):
        file_metadata = {"name": os.path.basename(file_path)}
        media = MediaFileUpload(file_path, resumable=True)
        uploaded = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name"
        ).execute()
        return uploaded

    # ⬇️ Скачивание файла
    def download_file(self, file_id, destination_path):
        request = self.service.files().get_media(fileId=file_id)
        with io.FileIO(destination_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        return destination_path

    # ❌ Удаление файла
    def delete_file(self, file_id):
        self.service.files().delete(fileId=file_id).execute()

    # 🔄 Обновление файла
    def update_file(self, file_id, new_file_path):
        media = MediaFileUpload(new_file_path, resumable=True)
        updated = self.service.files().update(
            fileId=file_id,
            media_body=media
        ).execute()
        return updated
