from __future__ import print_function

import os
import os.path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import io

SCOPES = ['https://www.googleapis.com/auth/drive.file']  # доступ только к файлам приложения
CREDENTIALS_FILE = '/Users/macbook/PycharmProjects/cryptobase/app/google/client_secret_1037331499755-f8pqjeov1hcb60sp53644i4ncaj5vtt8.apps.googleusercontent.com.json'
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.pkl')

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    service = build('drive', 'v3', credentials=creds)
    return service

def list_files():
    """Возвращает список файлов пользователя"""
    service = get_drive_service()
    results = service.files().list(pageSize=100, fields="files(id, name, mimeType, modifiedTime)").execute()
    files = results.get('files', [])
    # Преобразуем для MainWindow
    cloud_files = []
    for f in files:
        cloud_files.append({
            "id": f["id"],
            "name": f["name"],
            "path": f["name"],  # для GUI используем имя
            "status": "OK",
            "algorithm": "-",  # на облаке нет алгоритма
            "updated_at": f.get("modifiedTime")
        })
    return cloud_files

def upload_file(file_path):
    """Загружает файл на Google Drive."""
    service = get_drive_service()
    file_metadata = {'name': os.path.basename(file_path)}
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    return file.get('id')

def download_file(file_id):
    """Возвращает содержимое файла в виде строки (для JSON)"""
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.read().decode("utf-8")
