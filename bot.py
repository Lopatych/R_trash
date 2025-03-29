import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import os
import time
import logging

# Настройка логов
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

WHITELIST_FILE = 'whitelist.txt'
ADMIN_ID = os.getenv('ADMIN_ID')

def load_whitelist():
    try:
        if not os.path.exists(WHITELIST_FILE):
            return []
        with open(WHITELIST_FILE, 'r') as f:
            return [line.strip() for line in f.readlines()]
    except Exception as e:
        logger.error(f"Error loading whitelist: {e}")
        return []

def save_whitelist(data):
    try:
        with open(WHITELIST_FILE, 'w') as f:
            f.write('\n'.join(data))
    except Exception as e:
        logger.error(f"Error saving whitelist: {e}")

whitelist = load_whitelist()

def search_gifs(query):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }
    url = f"https://www.google.com/search?q={query}&tbm=isch&tbs=itp:animated"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        return [
            img['src'] for img in soup.find_all('img') 
            if img.get('src', '').startswith('http') and img['src'].endswith('.gif')
        ][:10]
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

@bot.message_handler(commands=['add', 'remove'])
def handle_admin_commands(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    
    try:
        command, user_id = message.text.split()
        if command == '/add':
            if user_id not in whitelist:
                whitelist.append(user_id)
                save_whitelist(whitelist)
                bot.reply_to(message, f"✅ Пользователь {user_id} добавлен")
        elif command == '/remove':
            if user_id in whitelist:
                whitelist.remove(user_id)
                save_whitelist(whitelist)
                bot.reply_to(message, f"❌ Пользователь {user_id} удалён")
    except Exception as e:
        logger.error(f"Admin command error: {e}")
        bot.reply_to(message, "⚠️ Ошибка формата команды")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    
    if user_id not in whitelist:
        bot.reply_to(message, "🔐 Доступ ограничен. Обратитесь к администратору.")
        return
    
    help_text = (
        "🎉 Добро пожаловать в GIF-поисковик!\n\n"
        "Просто отправьте мне поисковый запрос, и я найду для вас 10 GIF-анимаций!\n\n"
        "Примеры запросов:\n"
        "• funny cats\n"
        "• dancing robot\n"
        "• happy birthday\n\n"
        "⚠️ Максимальная длина запроса - 100 символов"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(func=lambda m: True)
def handle_search(message):
    user_id = str(message.from_user.id)
    
    if user_id not in whitelist:
        return
    
    try:
        if time.time() - message.date < 2:
            bot.reply_to(message, "⏳ Пожалуйста, подождите между запросами")
            return
        
        query = message.text.strip()
        if len(query) > 100:
            bot.reply_to(message, "❌ Слишком длинный запрос (макс. 100 символов)")
            return
        
        logger.info(f"New search: {query[:20]}... by {user_id}")
        bot.send_chat_action(message.chat.id, 'upload_photo')
        
        gifs = search_gifs(query)
        if not gifs:
            bot.reply_to(message, "😞 По вашему запросу ничего не найдено")
            return
        
        media = [types.InputMediaPhoto(url) for url in gifs[:10]]
        bot.send_media_group(message.chat.id, media)
        logger.info(f"Sent {len(gifs)} GIFs to {user_id}")
        
    except Exception as e:
        logger.error(f"Handler error: {e}")
        bot.reply_to(message, "⚠️ Произошла ошибка при обработке запроса")

if __name__ == '__main__':
    logger.info("Starting bot...")
    if os.getenv('RENDER'):
        WEBHOOK_URL = f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info("Webhook configured")
    else:
        bot.infinity_polling(logger_level=logging.INFO)
