import logging

def setup_logger(name=__name__, log_file='bot.log', level=logging.INFO):
    """
    Настраивает и возвращает логгер с заданным именем.
    Логи выводятся в консоль и в файл.
    """
    # Создаём форматтер
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Обработчик для файла
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    # Обработчик для консоли
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # Настраиваем корневой логгер (чтобы все логи попадали в оба обработчика)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    # Возвращаем логгер с именем модуля
    return logging.getLogger(name)

# Сразу создаём и настраиваем логгер для использования в других модулях
logger = setup_logger(__name__)