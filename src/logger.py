import logging
import os
from pathlib import Path

def setup_logger(name=None, log_file='bot.log', level=logging.INFO):
    """
    Настраивает корневой логгер (один раз) и возвращает логгер с указанным именем.
    Логи пишутся в папку data в корне проекта (создаётся автоматически).
    """
    # Определяем корень проекта (на один уровень выше, чем src)
    # Предполагаем, что этот файл лежит в src/logger.py
    current_dir = Path(__file__).parent          # папка src
    project_root = current_dir.parent            # корень проекта
    log_dir = project_root / 'data'               # полный путь к папке data
    log_file_path = log_dir / log_file            # полный путь к файлу лога

    # Создаём папку data, если её нет
    log_dir.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(stream_handler)

    return logging.getLogger(name) if name else root_logger

# Первичная настройка корневого логгера
setup_logger()