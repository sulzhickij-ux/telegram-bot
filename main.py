import logging
import asyncio
import sqlite3
import os
from collections import deque
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import google.generativeai as genai
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# --- КЛЮЧИ ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") 
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TELEGRAM_TOKEN or not GOOGLE_API_KEY:
    print("❌ ОШИБКА: Ключи не найдены!")
    exit(1)

# --- НАСТРОЙКИ AI ---
genai.configure(api_key=GOOGLE_API_KEY)
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

dp = Dispatcher()
chat_history = {}
conn = sqlite3.connect('debts.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS debts (who TEXT, to_whom TEXT, amount REAL, reason TEXT)''')
conn.commit()

# --- СПИСОК ИМЕН, НА КОТОРЫЕ ОТЗЫВАЕТСЯ БОТ ---
BOT_NAMES = ["хуюпсик", "бот", "bot", "эй ты"]

# --- ФУНКЦИЯ ЗАПРОСА К МОЗГАМ ---
def ask_gemini(prompt):
    models_to_try = [
        "gemini-3.0-flash", "gemini-3.0-flash-exp", 
        "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-flash-001"
    ]
    for model_name in models_to_try:
        try:
            model = genai.GenerativeModel(model_name, safety_settings=safety_settings)
            response = model.generate_content(prompt)
            if response.text: return response.text
        except: continue
    return "😔 Мозги перегрелись (ошибка API)."

# --- КОМАНДЫ ---
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
    msg = await message.reply("⚖️ Читаю дело...")
    prompt = f"Ты судья. Рассуди смешно этот чат:\n{chr(10).join(chat_history[cid])}"
    answer = await asyncio.to_thread(ask_gemini, prompt)
    await msg.edit_text(answer)

# --- ГЛАВНЫЙ ОБРАБОТЧИК ТЕКСТА ---
@dp.message()
async def handle_all_messages(message: types.Message):
    if not message.text or message.text.startswith('/'): return

    # 1. Сохраняем в историю (для судьи)
    cid = message.chat.id
    if cid not in chat_history: chat_history[cid] = deque(maxlen=40)
    chat_history[cid].append(f"{message.from_user.first_name}: {message.text}")

    # 2. Проверяем, зовут ли бота по имени
    text_lower = message.text.lower()
    
    # Проверяем, есть ли одно из имен в сообщении ИЛИ это личка с ботом
    is_private = message.chat.type == 'private'
    is_called = any(name in text_lower for name in BOT_NAMES)

    if is_called or is_private:
        # Показываем, что бот "печатает"
        await message.bot.send_chat_action(chat_id=cid, action="typing")
        
        # Генерируем ответ
        answer = await asyncio.to_thread(ask_gemini, message.text)
        
        # Отвечаем реплаем на сообщение
        await message.reply(answer)

# Заглушка для Render
async def dummy_server():
    async def handle(request): return web.Response(text="Alive")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    print("🚀 Старт (Режим общения по имени)...")
    bot = Bot(token=TELEGRAM_TOKEN)
    await asyncio.gather(dummy_server(), dp.start_polling(bot))

if __name__ == "__main__":
    asyncio.run(main())
