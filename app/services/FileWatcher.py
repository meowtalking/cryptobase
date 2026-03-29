import os
import time
import threading
from datetime import datetime
from app.db import SessionLocal
from app.models import FileRecord, FileVersion, LogEntry
from app.services.file_manager import compute_hash, now_msk
from PyQt5.QtCore import QObject, pyqtSignal
from app.services.backup_container import BackupContainer


class FileWatcher(QObject):
    update_signal = pyqtSignal()

    def __init__(self, main_window=None, local_page=None, interval: int = 10):
        super().__init__()
        self.main_window = main_window
        self.local_page = local_page
        self.interval = interval
        self.running = False
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)

        if self.local_page:
            self.update_signal.connect(self.local_page.load_files)
        else:
            print("[WARNING] FileWatcher создан без local_page — обновление таблицы не будет работать")

        # НЕ создаём постоянный контейнер здесь — будем брать свежий в каждом цикле
        # Это решает проблему кэша/рассинхрона

    def start(self):
        if not self.running:
            self.running = True
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=3)

    def _get_current_max_versions(self):
        if self.main_window:
            return self.main_window.get_max_versions()
        return 5

    def _watch_loop(self):
        while self.running:
            session = SessionLocal()
            try:
                max_versions = self._get_current_max_versions()

                # Каждый цикл — свежий контейнер (решает проблему старых данных)
                if not self.main_window or not self.main_window.master_key:
                    print("[WATCHER] Master key недоступен — пропуск цикла")
                    time.sleep(self.interval)
                    continue

                container = BackupContainer(self.main_window.master_key)

                for file_record in session.query(FileRecord).all():
                    try:
                        abs_path = os.path.abspath(file_record.path)

                        if not os.path.exists(abs_path):
                            # Файл отсутствует - статус missing
                            if file_record.status != "Missing":
                                file_record.status = "Missing"
                                session.add(LogEntry(
                                    action="file_missing",
                                    file_name=file_record.name,
                                    result="File not found",
                                    user_name=os.getlogin(),
                                    timestamp=now_msk()
                                ))
                                session.commit()
                            continue

                        # ────────────── ДИАГНОСТИКА ХЭША ──────────────
                        try:
                            # Небольшая задержка для предотвращения гонок состояний
                            time.sleep(0.1)
                            new_hash = compute_hash(abs_path)
                            print(
                                f"[HASH] {file_record.name:<35} db={file_record.current_hash[:12] if file_record.current_hash else 'None'}... "
                                f"new={new_hash[:12]}...  equal={new_hash == file_record.current_hash}")
                        except Exception as e:
                            print(f"[HASH-ERR] {file_record.name}: {e}")
                            continue

                        # Файл на месте - проверяем хэши
                        if new_hash == file_record.current_hash:
                            # Хэши совпадают - статус OK только если был missing
                            if file_record.status == "Missing":
                                file_record.status = "OK"
                                session.commit()
                                print(f"[STATUS] {file_record.name} → OK (файл найден после missing)")
                            # Если статус был modified, не меняем его
                            elif file_record.status == "Modified":
                                print(f"[STATUS] {file_record.name} остается Modified (хэши совпали, но статус сохранен)")
                            continue

                        # Хэши различаются - файл изменен
                        print(f"[CHANGE DETECTED] {file_record.name}")

                        # Проверяем, не был ли файл изменен слишком недавно (для предотвращения гонок)
                        try:
                            file_mtime = os.path.getmtime(abs_path)
                            current_time = time.time()
                            time_diff = current_time - file_mtime
                            
                            # Если файл изменен менее 2 секунд назад, пропускаем (предотвращаем гонки)
                            if time_diff < 2.0:
                                print(f"[SKIP] Файл изменен слишком недавно ({time_diff:.1f}s назад), пропускаем")
                                continue
                        except Exception as time_err:
                            print(f"[TIME-ERR] Ошибка проверки времени: {time_err}")

                        # Устанавливаем статус modified (если еще не установлен)
                        if file_record.status != "Modified":
                            file_record.status = "Modified"
                            print(f"[STATUS] {file_record.name} → Modified")
                        
                        file_record.updated_at = now_msk()

                        # Проверка дубликата по хэшу
                        has_same_hash_db = session.query(FileVersion).filter(
                            FileVersion.file_id == file_record.id,
                            FileVersion.version_hash == new_hash
                        ).first() is not None

                        has_same_hash_container = any(
                            v["hash"] == new_hash for v in container.get_all_versions(str(file_record.id))
                        )

                        if has_same_hash_db or has_same_hash_container:
                            file_record.current_hash = new_hash
                            session.commit()
                            print(f"[SKIP] Версия с хэшем {new_hash[:12]}... уже существует")
                            continue

                        # ──── СОЗДАНИЕ НОВОЙ ВЕРСИИ ────
                        try:
                            with open(abs_path, "rb") as f:
                                content = f.read()

                            file_id_str = str(file_record.id)
                            versions_before = container.get_all_versions(file_id_str)
                            print(f"[VERSION DEBUG] До добавления: {len(versions_before)} версий")

                            # Шифруем содержимое версии если файл зашифрован
                            if file_record.password_hash:
                                # Файл зашифрован - версию тоже нужно зашифровать
                                # Но content уже зашифрован (так как читаем с диска зашифрованный файл)
                                version_content = content.hex()
                            else:
                                # Файл не зашифрован - версия plaintext
                                version_content = content.hex()

                            version_data = {
                                "version_id": len(versions_before) + 1,
                                "created_at": now_msk().isoformat(),
                                "hash": new_hash,
                                "comment": "Auto FileWatcher",
                                "content": version_content
                            }

                            container.add_version(file_id_str, version_data)
                            print(f"[BACKUP OK] Добавлена версия → теперь {len(versions_before) + 1}")

                            file_record.current_hash = new_hash

                            new_v = FileVersion(
                                file_id=file_record.id,
                                version_hash=new_hash,
                                created_at=now_msk(),
                                comment=version_data["comment"],
                                location="container:backups.enc"
                            )
                            session.add(new_v)

                            # ──── ОБРЕЗКА ВЕРСИЙ ТОЛЬКО ЧЕРЕЗ delete_version ────
                            versions_after = container.get_all_versions(file_id_str)
                            current_count = len(versions_after)

                            if current_count > max_versions:
                                # Сортируем от новых к старым
                                versions_after.sort(
                                    key=lambda v: datetime.fromisoformat(v["created_at"]),
                                    reverse=True
                                )

                                # Удаляем лишние (с конца — самые старые)
                                excess = current_count - max_versions
                                print(f"[TRIM] Нужно удалить {excess} старых версий")

                                # Удаляем одну за другой (индексы с конца)
                                for i in range(excess):
                                    # Самая старая имеет индекс current_count - 1 - i
                                    index_to_delete = current_count - 1 - i
                                    container.delete_version(file_id_str, index_to_delete)
                                    print(f"[TRIM] Удалена версия по индексу {index_to_delete}")

                            # Логирование
                            from app.services.integrity_manager import _log_action
                            _log_action(
                                db=session,
                                action="auto_backup",
                                file_name=file_record.name,
                                result=f"created version {len(versions_before) + 1}",
                            )

                            session.commit()
                            self.update_signal.emit()

                        except Exception as e:
                            import traceback
                            print(f"[BACKUP CRASH] {file_record.name}: {e}")
                            print(traceback.format_exc())
                            session.rollback()

                    except Exception as file_err:
                        print(f"[FILE ERROR] {file_record.name if hasattr(file_record, 'name') else 'unknown'}: {file_err}")
                        import traceback
                        traceback.print_exc()
                        # Продолжаем со следующим файлом
                        continue

            except Exception as e:
                print(f"[WATCHER FATAL] {e}")
                import traceback
                traceback.print_exc()
                # Не останавливаем watcher, продолжаем работу
            finally:
                session.close()

            time.sleep(self.interval)