import requests
import json
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import heroku3
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

user_data = json.loads(os.getenv('HEROKU_USER_DATA', '{}'))
user_data_lock = asyncio.Lock()
logger.info(f"Initial user_data loaded: {json.dumps(user_data, indent=2)}")

async def reload_user_data():
    global user_data
    try:
        conn = heroku3.from_key(HEROKU_API_KEY)
        heroku_app = conn.apps()['tradenotionbot-lg2']
        config_vars = heroku_app.config()
        user_data_json = config_vars['HEROKU_USER_DATA'] if 'HEROKU_USER_DATA' in config_vars else '{}'
        user_data = json.loads(user_data_json)
        logger.info(f"Reloaded user_data from Heroku: {json.dumps(user_data, indent=2)}")
    except Exception as e:
        logger.error(f"Error reloading user_data: {str(e)}")
        user_data = {}

async def start(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Start command received from user {user_id}")
    
    await reload_user_data()
    
    async with user_data_lock:
        if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
            instructions = (
                "Щоб використовувати бота:\n"
                "1. Скопіюй сторінку за посиланням: https://www.notion.so/A-B-C-position-Final-Bot-1a084b079a8280d29d5ecc9316e02c5d\n"
                "2. Авторизуйся нижче і надай доступ до скопійованої сторінки.\n"
                "3. Введи ID батьківської сторінки 'A-B-C position Final Bot' (32 символи з URL)."
            )
            auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
            keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(instructions, reply_markup=reply_markup)
        elif 'parent_page_id' not in user_data[auth_key]:
            await update.message.reply_text('Введи ID батьківської сторінки "A-B-C position Final Bot" (32 символи з URL):')
        else:
            keyboard = [
                [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)
            logger.info(f"Sent menu to user {user_id}")

async def button(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Button callback received from user {user_id}: {query.data}")
    
    await query.answer()
    logger.debug(f"Before reload_user_data for user {user_id}")
    await reload_user_data()
    logger.debug(f"After reload_user_data for user {user_id}: {json.dumps(user_data.get(auth_key, {}), indent=2)}")
    
    async with user_data_lock:
        logger.debug(f"Checking user_data for {auth_key}")
        if auth_key not in user_data:
            logger.warning(f"No user_data for {auth_key}")
            await query.edit_message_text("Спочатку авторизуйся через /start.")
            return
        if 'notion_token' not in user_data[auth_key]:
            logger.warning(f"No notion_token for {auth_key}")
            await query.edit_message_text("Спочатку авторизуйся через /start.")
            return
        if 'parent_page_id' not in user_data[auth_key]:
            logger.warning(f"No parent_page_id for {auth_key}")
            await query.edit_message_text("Спочатку введи ID сторінки через /start.")
            return
        logger.info(f"User {user_id} passed all checks")

    if query.data == 'add_trade':
        try:
            logger.info(f"Processing add_trade for user {user_id}")
            keyboard = [
                [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
                [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
                [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
                [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
                [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text('Pair?', reply_markup=reply_markup)
            logger.info(f"Successfully sent Pair? message for user {user_id}")
        except Exception as e:
            logger.error(f"Error in add_trade for user {user_id}: {str(e)}")
            await query.edit_message_text("Сталася помилка. Спробуй ще раз через /start.")
    elif query.data == 'view_last_trade':
        logger.info(f"Processing view_last_trade for user {user_id}")
        await query.edit_message_text("Функція перегляду ще не реалізована.")

def main():
    logger.info("Starting bot with TELEGRAM_TOKEN: [REDACTED]")
    application = Application.builder().token(TELEGRAM_TOKEN).read_timeout(60).write_timeout(60).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    logger.info("Bot handlers registered. Starting polling...")
    application.run_polling()

if __name__ == '__main__':
    main()