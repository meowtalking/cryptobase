# server/main.py
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from minio import Minio
from minio.error import S3Error
from datetime import datetime

# --- Настройка MinIO ---
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
BUCKET_NAME = "cryptobase-backups"

client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

# Создаём бакет, если его нет
if not client.bucket_exists(BUCKET_NAME):
    client.make_bucket(BUCKET_NAME)

app = FastAPI(title="CryptoBase Remote Backup Server")


# ===========================================
# 🟢 Загрузка файла
# ===========================================
@app.post("/upload/{file_id}")
async def upload_backup(file_id: int, upload_file: UploadFile = File(...)):
    try:
        obj_name = f"{file_id}/{datetime.utcnow().isoformat()}.backup"
        client.put_object(
            BUCKET_NAME,
            obj_name,
            data=upload_file.file,  # ✅ передаём поток
            length=-1,  # неизвестная длина — MinIO сам вычислит
            part_size=10 * 1024 * 1024,  # 10MB части
            content_type=upload_file.content_type
        )
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {e}")
    return {"message": "Файл загружен", "object_name": obj_name}

# ===========================================
# 📜 Список версий
# ===========================================
@app.get("/versions/{file_id}")
def list_versions(file_id: int):
    try:
        objects = client.list_objects(BUCKET_NAME, prefix=f"{file_id}/", recursive=True)
        versions = []
        for obj in objects:
            versions.append({
                "object_name": obj.object_name,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None
            })
        return {"versions": versions}
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения списка версий: {e}")



# ===========================================
# ⬇️ Скачивание версии
# ===========================================
@app.get("/download/{file_id}/{object_name}")
def download_backup(file_id: int, object_name: str):
    try:
        response = client.get_object(BUCKET_NAME, object_name)
        return StreamingResponse(response, media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename={object_name.split('/')[-1]}"
        })
    except S3Error as e:
        raise HTTPException(status_code=404, detail=f"Файл не найден: {e}")


# ===========================================
# ❌ Удаление старой версии
# ===========================================
@app.delete("/delete/{file_id}/{object_name}")
def delete_backup(file_id: int, object_name: str):
    try:
        client.remove_object(BUCKET_NAME, object_name)
        return {"message": "Файл удалён"}
    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"Ошибка удаления: {e}")
