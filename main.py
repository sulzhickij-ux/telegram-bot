import logging
import asyncio
import sqlite3
import os
from collections import deque
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google import genai
from aiohttp import web

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") 
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TELEGRAM_TOKEN or not GOOGLE_API_KEY:
    print("❌ ОШИБКА: Ключи не найдены!")
    exit(1)

client = genai.Client(api_key=GOOGLE_API_KEY)
dp = Dispatcher()
chat_history = {}

# База данных
conn = sqlite3.connect('debts.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS debts (who TEXT, to_whom TEXT, amount REAL, reason TEXT)''')
conn.commit()

# --- УМНАЯ ФУНКЦИЯ ВЫБОРА МОДЕЛИ ---
def ask_gemini(prompt):
    # Твой список приоритетов. Сначала пробуем 3.0
    models_to_try = [
        "gemini-3.0-flash-exp",   # Твоя цель (Экспериментальная)
        "gemini-3.0-flash",       # Твоя цель (Стабильная)
        "gemini-2.0-flash-exp",   # Если 3.0 не дадут
        "gemini-1.5-flash"        # Старый надежный вариант
    ]
    
    for model_name in models_to_try:
        try:
            # Пытаемся стучаться в модель
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text
        except Exception as e:
            # Если ошибка — пишем в лог и идем к следующей модели
            print(f"⚠️ Модель {model_name} не сработала. Ошибка: {e}")
            continue 
            
    return "😔 Все версии нейросети (3.0, 2.0, 1.5) сейчас недоступны."

@dp.message(Command("бот"))
async def ask_bot(message: types.Message):
    q = message.text.replace("/бот", "").strip()
    if not q: return await message.reply("❓")
    wait = await message.reply("🚀 Пробую Gemini 3.0...")
    
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
    print("🚀 Старт (Ultimate Version)...")
    bot = Bot(token=TELEGRAM_TOKEN)
    await asyncio.gather(dummy_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
