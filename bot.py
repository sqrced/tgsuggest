import os
import logging
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Конфигурация ===
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Токен из переменных окружения Render
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Например: -1001234567890
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://<имя-сайта>.onrender.com/webhook

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Инициализация базы ===
async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                date TEXT
            )
        """)
        await db.commit()

# === Команда /start ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет! Отправь своё предложение сюда, и админы его рассмотрят 👀")

# === Приём предложений ===
@dp.message(F.text)
async def handle_suggestion(message: types.Message):
    text = message.text.strip()
    if not text:
        return

    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT INTO suggestions (user_id, text, date) VALUES (?, ?, ?)",
                         (message.from_user.id, text, datetime.now().isoformat()))
        await db.commit()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{message.from_user.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{message.from_user.id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, f"💬 Новое предложение от @{message.from_user.username or message.from_user.full_name}:\n\n{text}",
                                   reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"Не удалось отправить админу {admin_id}: {e}")

    await message.answer("✅ Предложение отправлено на модерацию!")

# === Кнопки модерации ===
@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    text = callback.message.text.split("\n\n", 1)[-1]

    try:
        await bot.send_message(CHANNEL_ID, text)
        await callback.message.edit_text(f"✅ Одобрено и опубликовано:\n\n{text}")
        await callback.answer("Пост опубликован в канал!")
    except Exception as e:
        await callback.answer("Ошибка публикации!")
        logger.error(e)

@dp.callback_query(F.data.startswith("reject_"))
async def reject_post(callback: types.CallbackQuery):
    text = callback.message.text.split("\n\n", 1)[-1]
    await callback.message.edit_text(f"❌ Отклонено:\n\n{text}")
    await callback.answer("Пост отклонён")

# === Вебхук ===
async def on_startup(app):
    await init_db()
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()

async def handle_webhook(request):
    update = await request.json()
    await dp.feed_webhook_update(bot, update)
    return web.Response()

app = web.Application()
app.router.add_post("/webhook", handle_webhook)

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
