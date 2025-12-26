import logging
import asyncio
import sqlite3
import os
from collections import deque
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import google.generativeai as genai  # <-- ВОТ ПРАВИЛЬНЫЙ ИМПОРТ
from aiohttp import web

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") 
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TELEGRAM_TOKEN or not GOOGLE_API_KEY:
    print("❌ ОШИБКА: Ключи не найдены!")
    exit(1)

# --- НАСТРОЙКА GEMINI (КЛАССИКА) ---
genai.configure(api_key=GOOGLE_API_KEY)

# Настройки безопасности
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

dp = Dispatcher()
chat_history = {}

# База данных
conn = sqlite3.connect('debts.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS debts (who TEXT, to_whom TEXT, amount REAL, reason TEXT)''')
conn.commit()

# --- ФУНКЦИЯ GEMINI ---
def ask_gemini(prompt):
    # Пробуем самую надежную модель
    model_name = "gemini-1.5-flash"
    
    try:
        model = genai.GenerativeModel(model_name, safety_settings=safety_settings)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Ошибка Gemini: {e}"

@dp.message(Command("бот"))
async def ask_bot(message: types.Message):
    q = message.text.replace("/бот", "").strip()
    if not q: return await message.reply("❓")
    wait = await message.reply("⚡ Думаю...")
    
    answer = await asyncio.to_thread(ask_gemini, q)
    await wait.edit_text(answer)

@dp.message(Command("долг"))
async def add_debt(message: types.Message):
    try:
        args = message.text.split()
        if len(args) < 4: return await message.reply("Формат: /долг @кому сумма за_что")
        to, amt, rsn = args[1], float(args[2].replace(',', '.')), " ".join(args[3:])
        who = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        cursor.execute("INSERT INTO debts VALUES (?, ?, ?, ?)", (who, to, amt, rsn))
        conn.commit()
        await message.reply(f"✅ {to} должен {who} {amt}р.")
    except: await message.reply("Ошибка данных.")

@dp.message(Command("баланс"))
async def show(message: types.Message):
    cursor.execute("SELECT * FROM debts")
    rows = cursor.fetchall()
    if not rows: return await message.reply("Чисто.")
    text = "\n".join([f"🔴 {r[1]} -> {r[0]}: {r[2]} ({r[3]})" for r in rows])
    await message.reply(f"📒 **Долги:**\n{text}\n\nСброс: /простить_все", parse_mode="Markdown")

@dp.message(Command("простить_все"))
async def clear(message: types.Message):
    cursor.execute("DELETE FROM debts"); conn.commit()
    await message.reply("🎉")

@dp.message(Command("суди"))
async def judge(message: types.Message):
    cid = message.chat.id
    if cid not in chat_history: return await message.reply("Тишина...")
    msg = await message.reply("⚖️ Судья читает дело...")
    
    prompt = f"Ты судья. Рассуди смешно и коротко этот чат:\n{chr(10).join(chat_history[cid])}"
    answer = await asyncio.to_thread(ask_gemini, prompt)
    await msg.edit_text(answer)

@dp.message()
async def hist(message: types.Message):
    if message.text and not message.text.startswith('/'):
        cid = message.chat.id
        if cid not in chat_history: chat_history[cid] = deque(maxlen=40)
        chat_history[cid].append(f"{message.from_user.first_name}: {message.text}")

# Заглушка для Render
async def dummy_server():
    async def handle(request): return web.Response(text="Bot is running")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    print("🚀 Старт (Classic Version)...")
    bot = Bot(token=TELEGRAM_TOKEN)
    await asyncio.gather(dummy_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
