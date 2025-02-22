import os
import json
import requests
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, Dispatcher
import asyncio
import logging

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Конфігурація
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')  # Наприклад, https://tradenotionbot-lg2.herokuapp.com/callback
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')
WEBHOOK_URL = f"https://tradenotionbot-lg2.herokuapp.com/webhook"

# Ініціалізація бота
application = Application.builder().token(TELEGRAM_TOKEN).build()
dispatcher = Dispatcher(application.bot, None, workers=0)

async def start(update, context):
    user_id = str(update.message.from_user.id)
    logger.info(f"Start command received from user {user_id}")
    keyboard = [
        [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade_test')],
        [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade_test')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)
    logger.info(f"Sent menu to user {user_id}")

async def button(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    logger.info(f"Button callback received from user {user_id}: {query.data}")
    await query.answer()
    
    if query.data == 'add_trade_test':
        logger.info(f"Processing add_trade for user {user_id}")
        await query.edit_message_text('Pair?')
    elif query.data == 'view_last_trade_test':
        logger.info(f"Processing view_last_trade for user {user_id}")
        await query.edit_message_text('Перегляд останнього трейду.')

# Реєстрація обробників
application.add_handler(CommandHandler('start', start))
application.add_handler(CallbackQueryHandler(button))

# Маршрут для вебхука
@app.route('/webhook', methods=['POST'])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await dispatcher.process_update(update)
    return Response(status=200)

# Маршрут для авторизації Notion
@app.route('/callback', methods=['GET'])
async def oauth_callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    print(f"Отримано code: {code}, user_id: {user_id}")
    if code and user_id:
        token_response = requests.post(
            'https://api.notion.com/v1/oauth/token',
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        ).json()
        print(f"Notion відповідь: {token_response}")
        if 'access_token' in token_response:
            user_data = {}
            user_data[user_id] = {'notion_token': token_response['access_token']}
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            print(f"Збережено user_data: {user_data}")
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

@app.route('/')
async def hello():
    return "Бот працює! Версія з вебхуками."

# Налаштування вебхука при запуску
async def set_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")

if __name__ == '__main__':
    from hypercorn.config import Config
    from hypercorn.asyncio import serve
    import asyncio
    
    asyncio.run(set_webhook())
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', 5000))}"]
    asyncio.run(serve(app, config))