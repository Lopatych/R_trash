import os
import logging
from functools import lru_cache
from flask import Flask, request
import telebot
from telebot.types import InputMediaAnimation, InlineKeyboardMarkup, InlineKeyboardButton
import requests
from cachetools import TTLCache

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = os.getenv('BOT_TOKEN')
GIPHY_API_KEY = os.getenv('GIPHY_API_KEY')
ADMIN_ID = os.getenv('ADMIN_ID')
WHITELIST_FILE = 'whitelist.txt'
CACHE_SIZE = 100
CACHE_TTL = 300

# Инициализация
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
gif_cache = TTLCache(maxsize=CACHE_SIZE, ttl=CACHE_TTL)
user_states = {}

# Файл вайтлиста
if not os.path.exists(WHITELIST_FILE):
    with open(WHITELIST_FILE, 'w') as f:
        if ADMIN_ID:
            f.write(f"{ADMIN_ID}\n")

# Утилиты
def update_whitelist(user_id):
    with open(WHITELIST_FILE, 'a+') as f:
        f.seek(0)
        if str(user_id) not in f.read().splitlines():
            f.write(f"{user_id}\n")

def check_whitelist(user_id):
    with open(WHITELIST_FILE, 'r') as f:
        return str(user_id) in f.read().splitlines()

# Команды админа
@bot.message_handler(commands=['add'])
def handle_add(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Требуются права администратора!")
        return
    
    try:
        user_id = message.text.split()[1]
        update_whitelist(user_id)
        bot.reply_to(message, f"✅ Пользователь {user_id} добавлен в вайтлист")
    except IndexError:
        bot.reply_to(message, "Использование: /add <user_id>")

@bot.message_handler(commands=['remove'])
def handle_remove(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Требуются права администратора!")
        return
    
    try:
        user_id = message.text.split()[1]
        with open(WHITELIST_FILE, "r") as f:
            lines = f.readlines()
        with open(WHITELIST_FILE, "w") as f:
            for line in lines:
                if line.strip() != user_id:
                    f.write(line)
        bot.reply_to(message, f"✅ Пользователь {user_id} удален из вайтлиста")
    except IndexError:
        bot.reply_to(message, "Использование: /remove <user_id>")

@bot.message_handler(commands=['whitelist'])
def handle_whitelist(message):
    if str(message.from_user.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Требуются права администратора!")
        return
    
    with open(WHITELIST_FILE, 'r') as f:
        users = f.read().splitlines()
    
    bot.reply_to(message, f"👥 Пользователи в вайтлисте:\n" + "\n".join(users))

# Поиск с кэшированием
@lru_cache(maxsize=CACHE_SIZE)
def search_gifs(query, limit=10, offset=0):
    url = "https://api.giphy.com/v1/gifs/search"
    params = {
        'api_key': GIPHY_API_KEY,
        'q': query,
        'limit': limit,
        'offset': offset,
        'lang': 'ru'
    }
    response = requests.get(url, params=params)
    return response.json()['data'] if response.status_code == 200 else []

# Пагинация
def create_pagination_markup(query, offset):
    markup = InlineKeyboardMarkup()
    if offset > 0:
        markup.add(InlineKeyboardButton("⬅ Назад", callback_data=f"prev_{query}_{offset}"))
    markup.add(InlineKeyboardButton("➡ Вперед", callback_data=f"next_{query}_{offset}"))
    return markup

# Обработка запросов
@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    
    if not check_whitelist(str(user_id)):
        bot.reply_to(message, "⛔ Доступ запрещен!")
        return
    
    search_query = message.text.strip()
    if not search_query:
        return
    
    user_states[user_id] = {'query': search_query, 'offset': 0}
    send_gifs(message.chat.id, search_query)

def send_gifs(chat_id, query, offset=0):
    try:
        data = search_gifs(query, limit=10, offset=offset)
        if not data:
            bot.send_message(chat_id, "Ничего не найдено 😞")
            return
        
        media_group = []
        for i, gif in enumerate(data[:10]):
            media = InputMediaAnimation(
                media=gif['images']['original']['url'],
                caption=f"Страница {offset//10 + 1}" if i == 0 else ''
            )
            media_group.append(media)
        
        bot.send_media_group(chat_id, media_group)
        bot.send_message(
            chat_id,
            f"Результаты по запросу: {query}",
            reply_markup=create_pagination_markup(query, offset)
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.send_message(chat_id, "⚠ Произошла ошибка")

# Обработка инлайн-кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    if not check_whitelist(str(user_id)):
        return
    
    data = call.data.split('_')
    action, query, offset = data[0], '_'.join(data[1:-1]), int(data[-1])
    
    new_offset = offset - 10 if action == 'prev' else offset + 10
    if new_offset < 0:
        new_offset = 0
    
    user_states[user_id] = {'query': query, 'offset': new_offset}
    bot.delete_message(call.message.chat.id, call.message.message_id)
    send_gifs(call.message.chat.id, query, new_offset)

# Веб-сервер для Render
@app.route('/')
def index():
    return "Bot is running!"

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

if __name__ == '__main__':
    logger.info("Starting bot...")
    bot.remove_webhook()
    bot.set_webhook(url=f"https://your-render-service.onrender.com/webhook")
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
