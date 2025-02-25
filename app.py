import os
import json
import requests
from flask import Flask, request
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Ініціалізація Flask
app = Flask(__name__)

# Конфігурація через змінні середовища
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')

# Перевірка токена
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN is not set. Bot will not start.")
else:
    logger.info(f"TELEGRAM_TOKEN is set: {TELEGRAM_TOKEN[:5]}... (hidden for security)")

# Завантажуємо user_data із файлу
USER_DATA_FILE = 'user_data.json'

def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    try:
        with open(USER_DATA_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save user_data: {e}")

user_data = load_user_data()

# Ініціалізація Telegram Application
application = Application.builder().token(TELEGRAM_TOKEN).build()

# Flask маршрути
@app.route('/')
def hello():
    return "Бот працює! Версія 2"

@app.route('/callback', methods=['GET'])
def oauth_callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    logger.info(f"Received OAuth callback - code: {code}, user_id: {user_id}")
    if code and user_id:
        token_response = requests.post(
            'https://api.notion.com/v1/oauth/token',
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        ).json()
        logger.info(f"Notion response: {token_response}")
        if 'access_token' in token_response:
            user_data[user_id] = {'notion_token': token_response['access_token']}
            save_user_data(user_data)
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

# Маршрут для вебхуків Telegram
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return 'OK', 200

# Функції для Notion API (додайте повні реалізації з вашого попереднього коду)
def fetch_classification_db_id(page_id, notion_token):
    logger.debug(f"Fetching Classification DB ID for page: {page_id}")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {"Authorization": f"Bearer {notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch children: {response.status_code} - {response.text}")
        return None
    data = response.json()
    for block in data.get("results", []):
        if block["type"] == "child_database" and "Classification" in block["child_database"]["title"]:
            return block["id"]
    return None

def get_max_num(classification_db_id, notion_token):
    # Додайте повну реалізацію
    return 0

def create_notion_page(user_id):
    # Додайте повну реалізацію
    return None, None

def fetch_page_properties(page_id, notion_token):
    # Додайте повну реалізацію
    return None

def fetch_last_5_trades(classification_db_id, notion_token):
    # Додайте повну реалізацію
    return None

# Telegram хендлери
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Start command received from user {user_id}")
    
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        instructions = (
            "Щоб використовувати бота:\n"
            "1. Скопіюй сторінку: https://www.notion.so/A-B-C-position-Final-Bot-1a084b079a8280d29d5ecc9316e02c5d\n"
            "2. Авторизуйся і введи ID сторінки."
        )
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(instructions, reply_markup=reply_markup)
    else:
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        keyboard = [
            [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
            [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
            [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')],
            [InlineKeyboardButton("Повторна авторизація", url=auth_url)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)

# Додайте решту хендлерів (handle_text, button тощо) з вашого попереднього коду
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Text input received from user {user_id}: {update.message.text}")
    # Додайте повну логіку з вашого коду

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Button callback received from user {user_id}: {query.data}")
    await query.answer()
    # Додайте повну логіку з вашого коду

def format_summary(data):
    # Додайте повну реалізацію
    return "Placeholder summary"

# Налаштування хендлерів
application.add_handler(CommandHandler('start', start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(CallbackQueryHandler(button))

# Налаштування вебхука при старті програми
if TELEGRAM_TOKEN:
    webhook_url = f"https://trade-notion-bot.onrender.com/{TELEGRAM_TOKEN}"
    logger.info(f"Setting webhook to: {webhook_url}")
    response = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook?url={webhook_url}")
    if response.status_code == 200:
        logger.info("Webhook set successfully.")
    else:
        logger.error(f"Failed to set webhook: {response.status_code} - {response.text}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)