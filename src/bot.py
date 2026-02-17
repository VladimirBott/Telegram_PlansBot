import asyncio
import logging
from datetime import datetime, timedelta

import asyncpg
from telegram import Update
from telegram.ext import (Application, CommandHandler, ContextTypes,
                          MessageHandler, filters)

from src.config import DATABASE_URL, TOKEN
from src.loggers import logger


async def init_db_pool():
    """Создание пула соединений с БД."""
    logger.info("Инициализация пула соединений с PostgreSQL...")
    return await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)


# Работа с напоминаниями
async def add_reminder(pool, user_id, chat_id, text, remind_time):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO reminders (user_id, chat_id, text, remind_time) VALUES ($1, $2, $3, $4)",
            user_id,
            chat_id,
            text,
            remind_time,
        )
    logger.info(f"Добавлено напоминание для user {user_id}: {text} на {remind_time}")


async def get_due_reminders(pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, chat_id, text FROM reminders WHERE remind_time <= NOW() AND is_done = FALSE"
        )
        return [(r["id"], r["chat_id"], r["text"]) for r in rows]


async def mark_done(pool, reminder_id):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE reminders SET is_done = TRUE WHERE id = $1", reminder_id
        )
    logger.info(f"Напоминание {reminder_id} отмечено выполненным")


async def get_user_reminders(pool, user_id):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, text, remind_time FROM reminders WHERE user_id = $1 AND is_done = FALSE ORDER BY remind_time",
            user_id,
        )
        return rows


# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я твой офисный помощник.\n"
        "Просто напиши мне напоминание в формате:\n"
        "`Завтра 10:30 Позвонить клиенту`\n"
        "или\n"
        "`25.03.2025 14:00 Созвониться с бухгалтерией`\n\n"
        "Доступные команды:\n"
        "/tasks — список активных задач\n"
        "/done <номер> — отметить задачу выполненной"
    )
    logger.info(f"Пользователь {update.effective_user.id} запустил бота")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    parts = text.split(" ", 2)
    if len(parts) < 3:
        await update.message.reply_text(
            "Не понял формат. Попробуй: `25.12 15:30 Купить молоко`"
        )
        logger.warning(f"Пользователь {user_id} ввёл некорректный формат: {text}")
        return

    date_str, time_str, reminder_text = parts[0], parts[1], parts[2]

    try:
        if date_str.lower() == "завтра":
            dt = datetime.now() + timedelta(days=1)
            hour, minute = map(int, time_str.split(":"))
            dt = dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
        else:
            if len(date_str.split(".")) == 2:
                date_str += f".{datetime.now().year}"
            dt = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M")
    except Exception as e:
        await update.message.reply_text(
            "Ошибка в дате/времени. Используй формат ДД.ММ.ГГГГ ЧЧ:ММ или 'завтра ЧЧ:ММ'"
        )
        logger.error(f"Ошибка парсинга даты от user {user_id}: {e}")
        return

    pool = context.bot_data["db_pool"]
    await add_reminder(pool, user_id, chat_id, reminder_text, dt)
    await update.message.reply_text(
        f"✅ Напомню: {reminder_text}\n⏰ {dt.strftime('%d.%m.%Y %H:%M')}"
    )


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pool = context.bot_data["db_pool"]
    reminders = await get_user_reminders(pool, user_id)

    if not reminders:
        await update.message.reply_text("У тебя нет активных напоминаний.")
        logger.info(f"Пользователь {user_id} запросил задачи, но список пуст")
        return

    msg = "📋 Твои задачи:\n"
    for i, r in enumerate(reminders, 1):
        dt = r["remind_time"]
        msg += f"{i}. {r['text']} — {dt.strftime('%d.%m.%Y %H:%M')}\n"
    await update.message.reply_text(msg)
    logger.info(
        f"Пользователь {user_id} запросил задачи, отправлено {len(reminders)} напоминаний"
    )


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = int(context.args[0])
    except IndexError, ValueError:
        await update.message.reply_text("Укажи номер задачи, например: /done 3")
        logger.warning(f"Пользователь {update.effective_user.id} ввёл /done без номера")
        return

    user_id = update.effective_user.id
    pool = context.bot_data["db_pool"]
    reminders = await get_user_reminders(pool, user_id)

    if num < 1 or num > len(reminders):
        await update.message.reply_text("Нет задачи с таким номером.")
        logger.warning(
            f"Пользователь {user_id} указал несуществующий номер задачи: {num}"
        )
        return

    rid = reminders[num - 1]["id"]
    await mark_done(pool, rid)
    await update.message.reply_text(f"Задача {num} отмечена выполненной.")
    logger.info(f"Пользователь {user_id} отметил задачу {rid} как выполненную")


# Фоновая задача для проверки напоминаний
async def reminder_loop(app: Application):
    logger.info("Цикл проверки напоминаний запущен")
    while True:
        try:
            pool = app.bot_data["db_pool"]
            due = await get_due_reminders(pool)
            for rid, chat_id, text in due:
                try:
                    await app.bot.send_message(
                        chat_id=chat_id, text=f"⏰ Напоминание: {text}"
                    )
                    await mark_done(pool, rid)
                    logger.info(f"Отправлено напоминание {rid} в чат {chat_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки напоминания {rid}: {e}")
        except Exception as e:
            logger.error(f"Ошибка в цикле напоминаний: {e}", exc_info=True)
        await asyncio.sleep(30)


async def main():
    logger.info("Запуск бота...")
    pool = await init_db_pool()
    app = Application.builder().token(TOKEN).build()
    app.bot_data["db_pool"] = pool

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", tasks))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.updater.start_polling()
    await app.start()

    asyncio.create_task(reminder_loop(app))

    logger.info("Бот с PostgreSQL запущен. Нажми Ctrl+C для остановки.")

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Получен сигнал остановки")
    finally:
        logger.info("Останавливаю бота...")
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await pool.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())
