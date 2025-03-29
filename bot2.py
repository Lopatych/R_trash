import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import os
import time
import logging
from flask import Flask, request

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Configuration
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
WHITELIST_FILE = 'whitelist.txt'
ADMIN_ID = os.getenv('ADMIN_ID')

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Whitelist management
def load_whitelist():
    try:
        if not os.path.exists(WHITELIST_FILE):
            return []
        with open(WHITELIST_FILE, 'r') as f:
            return [line.strip() for line in f.readlines()]
    except Exception as e:
        logger.error(f"Whitelist error: {e}")
        return []

def save_whitelist(data):
    try:
        with open(WHITELIST_FILE, 'w') as f:
            f.write('\n'.join(data))
    except Exception as e:
        logger.error(f"Save whitelist error: {e}")

whitelist = load_whitelist()+[ADMIN_ID]

# Image search function
def search_images(query):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(
            f"https://www.google.com/search?q={query}&tbm=isch",
            headers=headers,
            timeout=15
        )
        soup = BeautifulSoup(response.text, 'html.parser')
        return [img['src'] for img in soup.find_all('img') 
               if img.get('src', '').startswith('http')][:10]
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []

# Bot handlers
@bot.message_handler(commands=['add', 'remove'])
def handle_admin(message):
    if str(message.from_user.id) != ADMIN_ID:
        return
    try:
        cmd, user_id = message.text.split()
        if cmd == '/add' and user_id not in whitelist:
            whitelist.append(user_id)
            save_whitelist(whitelist)
            bot.reply_to(message, f"✅ Added {user_id}")
        elif cmd == '/remove' and user_id in whitelist:
            whitelist.remove(user_id)
            save_whitelist(whitelist)
            bot.reply_to(message, f"❌ Removed {user_id}")
    except Exception as e:
        logger.error(f"Admin command error: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if str(message.from_user.id) not in whitelist:
        bot.reply_to(message, "🔒 Contact administrator for access")
        return
    bot.reply_to(message, "🔍 Send me a search query to get images!")

@bot.message_handler(func=lambda m: True)
def handle_query(message):
    user_id = str(message.from_user.id)
    if user_id not in whitelist:
        return
    
    try:
        query = message.text.strip()
        if len(query) > 100:
            bot.reply_to(message, "❌ Query too long (max 100 chars)")
            return
        
        logger.info(f"New search: {query[:20]}... by {user_id}")
        bot.send_chat_action(message.chat.id, 'upload_photo')
        
        if images := search_images(query)[:10]:
            bot.send_media_group(message.chat.id, [types.InputMediaPhoto(url) for url in images])
        else:
            bot.reply_to(message, "❌ No images found")
    except Exception as e:
        logger.error(f"Handler error: {e}")

# Webhook routes
@app.route('/webhook', methods=['POST'])
def webhook_handler():
    if request.headers.get('content-type') == 'application/json':
        update = types.Update.de_json(request.get_json())
        bot.process_new_updates([update])
        return 'ok', 200
    return 'Bad request', 400

@app.route('/')
def health_check():
    return 'Bot is running', 200

# Initialization
if __name__ == '__main__':
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"https://{os.getenv('RENDER_SERVICE_NAME')}.onrender.com/webhook")
    app.run(host='0.0.0.0', port=os.getenv('PORT', 5000))
