#!/usr/bin/env python3
"""
Clover Swarm ESP-NOW Auto Updater
Автоматический обновлятор для проекта clover-swarm-espnow
"""

import os
import sys
import json
import hashlib
import requests
import zipfile
import tempfile
import shutil
import base64
from pathlib import Path
from getpass import getpass
import argparse
from typing import Optional, Dict, Any

class AutoUpdater:
    def __init__(self, server_url: str, password: str):
        self.server_url = server_url.rstrip('/')
        self.password = password
        self.session = requests.Session()
        # Настраиваем Basic Auth с пустым именем пользователя
        self.session.auth = ('', password)
        
        # Информация о репозитории (из PHP сервера)
        self.repo_owner = 'ropraname'
        self.repo_name = 'clover-swarm-espnow'
        
    def get_current_version(self) -> Optional[str]:
        """Получить текущую версию проекта"""
        version_file = Path("VERSION")
        if version_file.exists():
            return version_file.read_text().strip()
        
        # Попытка получить версию из git
        try:
            import subprocess
            result = subprocess.run(
                ["git", "describe", "--tags", "--always"],
                capture_output=True, text=True, cwd="."
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        
        return None
    
    def get_latest_release_info(self) -> Optional[Dict[str, Any]]:
        """Получить информацию о последнем релизе с сервера"""
        try:
            # Пробуем передать пароль через GET параметр
            params = {'password': self.password}
            response = requests.get(f"{self.server_url}/update_server.php", params=params)
            response.raise_for_status()
            
            data = response.json()
            if data.get('success'):
                return data.get('data')
            else:
                print(f"Ошибка сервера: {data.get('error', 'Неизвестная ошибка')}")
                if 'debug' in data:
                    print(f"Отладочная информация: {data['debug']}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Ошибка подключения к серверу: {e}")
            return None
        except json.JSONDecodeError:
            print("Ошибка парсинга ответа сервера")
            return None
    
    def download_asset(self, asset_url: str, filename: str) -> Optional[Path]:
        """Скачать файл релиза"""
        try:
            print(f"Скачивание {filename}...")
            
            # Если это архив через API, используем PHP прокси
            if 'api.github.com' in asset_url:
                # Извлекаем тег из URL
                tag = asset_url.split('/')[-1]
                download_url = f"{self.server_url}/update_server.php?action=download&tag={tag}&password={self.password}"
                
                response = self.session.get(download_url)
                response.raise_for_status()
                
                data = response.json()
                if data.get('success'):
                    # Декодируем base64 данные
                    import base64
                    archive_data = base64.b64decode(data['archive_data'])
                    archive_name = data['archive_name']
                    
                    # Создаем временную директорию для загрузки
                    temp_dir = Path(tempfile.mkdtemp())
                    file_path = temp_dir / archive_name
                    
                    with open(file_path, 'wb') as f:
                        f.write(archive_data)
                    
                    print(f"Архив скачан через прокси: {file_path}")
                    return file_path
                else:
                    print(f"Ошибка прокси: {data.get('error', 'Unknown error')}")
                    return None
            else:
                # Для обычных assets используем прямую ссылку
                response = requests.get(asset_url, stream=True)
                response.raise_for_status()
                
                # Создаем временную директорию для загрузки
                temp_dir = Path(tempfile.mkdtemp())
                file_path = temp_dir / filename
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                print(f"Файл скачан: {file_path}")
                return file_path
            
        except Exception as e:
            print(f"Ошибка скачивания: {e}")
            return None
    
    def extract_and_update(self, zip_path: Path, backup: bool = True) -> bool:
        """Распаковать архив и обновить проект с слиянием директорий"""
        try:
            # Создаем бэкап если нужно
            if backup:
                import time
                backup_dir = Path(f"backup_{int(time.time())}")
                if Path(".").exists():
                    # Создаем функцию для исключения бэкапов и других ненужных файлов
                    def ignore_backups(dir, files):
                        ignored = []
                        for file in files:
                            file_path = Path(dir) / file
                            # Исключаем существующие бэкапы
                            if file.startswith("backup_"):
                                ignored.append(file)
                            # Исключаем другие ненужные файлы
                            elif file in [".git", "__pycache__"] or file.endswith(".pyc"):
                                ignored.append(file)
                        return ignored
                    
                    shutil.copytree(".", backup_dir, ignore=ignore_backups)
                print(f"Создан бэкап: {backup_dir}")
            
            # Распаковываем архив во временную директорию
            temp_extract_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_extract_dir)
            
            # Находим корневую директорию в распакованном архиве
            root_dir = None
            for item in temp_extract_dir.iterdir():
                if item.is_dir():
                    root_dir = item
                    break
            
            if root_dir:
                # Сливаем директории
                self._merge_directories(root_dir, Path("."))
            else:
                # Если нет корневой директории, копируем файлы напрямую
                for item in temp_extract_dir.iterdir():
                    self._merge_item(item, Path("."))
            
            # Очищаем временную директорию
            shutil.rmtree(temp_extract_dir)
            
            print("Обновление завершено успешно!")
            return True
            
        except Exception as e:
            print(f"Ошибка обновления: {e}")
            return False
    
    def _merge_directories(self, source: Path, destination: Path):
        """Слить директории, сохраняя локальные файлы"""
        for item in source.iterdir():
            self._merge_item(item, destination)
    
    def _merge_item(self, source_item: Path, destination_dir: Path):
        """Слить отдельный файл или директорию"""
        dest_path = destination_dir / source_item.name
        
        if source_item.is_file():
            # Файл
            if dest_path.exists():
                print(f"Обновлен файл: {dest_path}")
            else:
                print(f"Добавлен файл: {dest_path}")
            
            # Копируем файл (заменяем если существует)
            shutil.copy2(source_item, dest_path)
            
        elif source_item.is_dir():
            # Директория
            if dest_path.exists():
                if dest_path.is_dir():
                    # Директория существует - сливаем содержимое
                    print(f"Слияние директории: {dest_path}")
                    self._merge_directories(source_item, dest_path)
                else:
                    # Существует файл с таким именем - заменяем на директорию
                    print(f"Заменен файл на директорию: {dest_path}")
                    dest_path.unlink()
                    shutil.copytree(source_item, dest_path)
            else:
                # Директория не существует - копируем полностью
                print(f"Добавлена директория: {dest_path}")
                shutil.copytree(source_item, dest_path)
    
    def update_version_file(self, version: str):
        """Обновить файл версии"""
        try:
            with open("VERSION", "w") as f:
                f.write(version)
            print(f"Версия обновлена: {version}")
        except Exception as e:
            print(f"Ошибка обновления файла версии: {e}")
    
    def check_for_updates(self) -> bool:
        """Проверить наличие обновлений"""
        current_version = self.get_current_version()
        latest_release = self.get_latest_release_info()
        
        if not latest_release:
            print("Не удалось получить информацию о последнем релизе")
            return False
        
        latest_version = latest_release.get('tag_name', 'unknown')
        
        print(f"Текущая версия: {current_version or 'неизвестна'}")
        print(f"Последняя версия: {latest_version}")
        
        if current_version and current_version == latest_version:
            print("У вас уже установлена последняя версия!")
            return False
        
        return True
    
    def perform_update(self, backup: bool = True) -> bool:
        """Выполнить обновление"""
        latest_release = self.get_latest_release_info()
        
        if not latest_release:
            return False
        
        # Ищем zip файл в активах
        assets = latest_release.get('assets', [])
        print(f"Найдено файлов в релизе: {len(assets)}")
        
        # Показываем все доступные файлы
        for i, asset in enumerate(assets):
            print(f"  {i+1}. {asset.get('name', 'unknown')} ({asset.get('size', 0)} bytes)")
        
        zip_asset = None
        
        for asset in assets:
            if asset.get('name', '').endswith('.zip'):
                zip_asset = asset
                break
        
        if not zip_asset:
            print("Не найден ZIP файл в релизе")
            print("Доступные файлы:")
            for asset in assets:
                print(f"  - {asset.get('name', 'unknown')}")
            
            # Пробуем использовать автоматический архив через PHP сервер
            archive_url = latest_release.get('archive_url')
            archive_name = latest_release.get('archive_name')
            
            if archive_url and archive_name:
                print(f"Используем автоматический архив: {archive_name}")
                
                # Создаем виртуальный asset для архива
                zip_asset = {
                    'name': archive_name,
                    'browser_download_url': archive_url
                }
            else:
                print("Не удалось получить ссылку на архив")
                return False
        
        # Скачиваем файл
        zip_path = self.download_asset(
            zip_asset['browser_download_url'],
            zip_asset['name']
        )
        
        if not zip_path:
            return False
        
        try:
            # Выполняем обновление
            success = self.extract_and_update(zip_path, backup)
            
            if success:
                # Обновляем версию
                self.update_version_file(latest_release.get('tag_name', ''))
            
            return success
            
        finally:
            # Удаляем временный файл
            if zip_path and zip_path.exists():
                zip_path.unlink()
                zip_path.parent.rmdir()

def main():
    parser = argparse.ArgumentParser(description="Clover Swarm ESP-NOW Auto Updater")
    parser.add_argument("--server", default="https://h.548b.ru/espswarmupdater", help="URL сервера обновлений")
    parser.add_argument("--password", help="Пароль для доступа")
    parser.add_argument("--no-backup", action="store_true", help="Не создавать бэкап")
    parser.add_argument("--check-only", action="store_true", help="Только проверить обновления")
    
    args = parser.parse_args()
    
    # Запрашиваем пароль если не указан
    password = args.password
    
    if not password:
        password = getpass("Введите пароль для доступа к обновлениям: ")
    
    # Создаем экземпляр обновлятора
    updater = AutoUpdater(args.server, password)
    
    if args.check_only:
        # Только проверка обновлений
        updater.check_for_updates()
    else:
        # Проверяем и выполняем обновление
        if updater.check_for_updates():
            print("\nНайдено обновление!")
            response = input("Выполнить обновление? (y/N): ")
            
            if response.lower() in ['y', 'yes', 'да']:
                success = updater.perform_update(backup=not args.no_backup)
                if success:
                    print("Обновление выполнено успешно!")
                    sys.exit(0)
                else:
                    print("Ошибка при обновлении!")
                    sys.exit(1)
            else:
                print("Обновление отменено.")
        else:
            print("Обновления не найдены.")

if __name__ == "__main__":
    main()
