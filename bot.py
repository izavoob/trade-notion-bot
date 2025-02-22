import requests
import json
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.request import HTTPXRequest
import heroku3
import asyncio

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Конфігурація через змінні середовища
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '7947810667:AAFAFahelospvLx501EQX2TacNzw0YS4zxw')
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

# Завантажуємо user_data із змінної Heroku з обробкою помилок
raw_user_data = os.getenv('HEROKU_USER_DATA', '{}')
try:
    user_data = json.loads(raw_user_data)
except json.JSONDecodeError:
    logger.error(f"Помилка парсингу HEROKU_USER_DATA: '{raw_user_data}'. Використовуємо порожній словник.")
    user_data = {}
user_data_lock = asyncio.Lock()
logger.info(f"Initial user_data loaded: {json.dumps(user_data, indent=2)}")

# Асинхронна функція для збереження user_data в Heroku (тимчасово відключена)
async def save_user_data_to_heroku():
    async with user_data_lock:
        logger.debug("save_user_data_to_heroku called but skipped for testing")
        # Коментуємо збереження для тестування
        """
        try:
            def sync_save():
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']  # Змініть на ваше ім'я додатку
                config = heroku_app.config()
                config['HEROKU_USER_DATA'] = json.dumps(user_data)
                return True
            
            result = await asyncio.to_thread(sync_save)
            logger.info("HEROKU_USER_DATA successfully updated in Heroku")
            return result
        except Exception as e:
            logger.error(f"Error saving to Heroku: {str(e)}")
            raise
        """
        return True

# Функція для отримання ID бази "Classification"
def fetch_classification_db_id(page_id, notion_token):
    logger.debug(f"Starting fetch_classification_db_id with page_id: {page_id}")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch children of page {page_id}: {response.status_code} - {response.text}")
        return None
    data = response.json()
    for block in data.get("results", []):
        if block["type"] == "child_database" and "Classification" in block["child_database"]["title"]:
            logger.info(f"Found Classification database with ID: {block['id']}")
            return block["id"]
    logger.error("Classification database not found on parent page.")
    return None

# Функція для створення сторінки в Notion
def create_notion_page(user_id):
    logger.debug(f"Starting create_notion_page for user {user_id}")
    url = 'https://api.notion.com/v1/pages'
    headers = {
        'Authorization': f'Bearer {user_data[user_id]["notion_token"]}',
        'Content-Type': 'application/json',
        'Notion-Version': "2022-06-28"
    }
    
    trigger_values = user_data[user_id].get('Trigger', [])
    vc_values = user_data[user_id].get('VC', [])
    payload = {
        'parent': {'database_id': user_data[user_id]['classification_db_id']},
        'properties': {
            'Pair': {'select': {'name': user_data[user_id]['Pair']}},
            'Session': {'select': {'name': user_data[user_id]['Session']}},
            'Context': {'select': {'name': user_data[user_id]['Context']}},
            'Test POI': {'select': {'name': user_data[user_id]['Test POI']}},
            'Delivery to POI': {'select': {'name': user_data[user_id]['Delivery to POI']}},
            'Point A': {'select': {'name': user_data[user_id]['Point A']}},
            'Trigger': {'multi_select': [{'name': value} for value in trigger_values] if trigger_values else []},
            'VC': {'multi_select': [{'name': value} for value in vc_values] if vc_values else []},
            'Entry Model': {'select': {'name': user_data[user_id]['Entry Model']}},
            'Entry TF': {'select': {'name': user_data[user_id]['Entry TF']}},
            'Point B': {'select': {'name': user_data[user_id]['Point B']}},
            'SL Position': {'select': {'name': user_data[user_id]['SL Position']}},
            'RR': {'number': user_data[user_id]['RR']}
        }
    }
    
    logger.debug(f"Notion API payload: {json.dumps(payload, indent=2)}")
    response = requests.post(url, json=payload, headers=headers)
    logger.debug(f"Notion API response: status={response.status_code}, content={response.text}")
    
    if response.status_code == 200:
        page_id = response.json()['id']
        logger.info(f"Successfully created page for user {user_id} with ID: {page_id}")
        return page_id
    else:
        logger.error(f"Notion API error for user {user_id}: {response.status_code} - {response.text}")
        return None

# Функція для отримання властивостей сторінки з Notion
def fetch_page_properties(page_id, notion_token):
    logger.debug(f"Fetching properties for page {page_id}")
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch page properties: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    properties = data.get('properties', {})
    
    score = properties.get('Score', {}).get('formula', {}).get('number', None)
    trade_class = properties.get('Trade Class', {}).get('formula', {}).get('string', None)
    offer_risk = properties.get('Offer Risk', {}).get('formula', {}).get('number', None)
    
    logger.info(f"Retrieved properties - Score: {score}, Trade Class: {trade_class}, Offer Risk: {offer_risk}")
    return {
        'Score': score,
        'Trade Class': trade_class,
        'Offer Risk': offer_risk
    }

# Початок роботи бота
async def start(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Start command received from user {user_id}")
    
    async with user_data_lock:
        if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
            instructions = (
                "Щоб використовувати бота:\n"
                "1. Скопіюй сторінку за посиланням: https://www.notion.so/A-B-C-position-Final-Bot-1a084b079a8280d29d5ecc9316e02c5d\n"
                "2. Авторизуйся нижче і введи ID батьківської сторінки 'A-B-C position Final Bot' (32 символи з URL)."
            )
            auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
            keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(instructions, reply_markup=reply_markup)
        elif 'parent_page_id' not in user_data[auth_key]:
            await update.message.reply_text('Введи ID батьківської сторінки "A-B-C position Final Bot" (32 символи з URL):')
        elif 'classification_db_id' not in user_data[auth_key]:
            logger.debug(f"Fetching classification_db_id for user {user_id}")
            classification_db_id = fetch_classification_db_id(user_data[auth_key]['parent_page_id'], user_data[auth_key]['notion_token'])
            if classification_db_id:
                user_data[auth_key]['classification_db_id'] = classification_db_id
                # Тимчасово пропускаємо збереження в Heroku
                await save_user_data_to_heroku()
                logger.debug(f"Classification DB ID saved: {classification_db_id}")
                keyboard = [
                    [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                    [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)
            else:
                await update.message.reply_text('Помилка: не вдалося знайти базу "Classification". Перевір правильність ID сторінки.')
        else:
            keyboard = [
                [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)

# Обробка текстового вводу
async def handle_text(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Text input received from user {user_id}: {update.message.text}")
    
    async with user_data_lock:
        if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
            await update.message.reply_text("Спочатку авторизуйся через /start.")
        elif 'parent_page_id' not in user_data[auth_key]:
            text = update.message.text
            if len(text) == 32:
                user_data[auth_key]['parent_page_id'] = text
                # Тимчасово пропускаємо збереження в Heroku
                await save_user_data_to_heroku()
                logger.debug(f"Parent page ID saved: {text}")
                await update.message.reply_text('ID сторінки збережено! Напиши /start.')
            else:
                await update.message.reply_text('Неправильний ID. Введи 32 символи з URL сторінки "A-B-C position Final Bot".')
        elif 'waiting_for_rr' in user_data[auth_key]:
            rr_input = update.message.text
            try:
                rr = float(rr_input)
                user_data[auth_key]['RR'] = rr
                required_keys = ['Pair', 'Session', 'Context', 'Test POI', 'Delivery to POI', 'Point A', 
                                'Trigger', 'VC', 'Entry Model', 'Entry TF', 'Point B', 'SL Position', 'RR']
                missing_keys = [key for key in required_keys if key not in user_data[auth_key]]
                if missing_keys:
                    await update.message.reply_text(f"Помилка: відсутні дані для {', '.join(missing_keys)}. Почни заново через 'Додати трейд'.")
                else:
                    summary = format_summary(user_data[auth_key])
                    keyboard = [
                        [InlineKeyboardButton("Відправити", callback_data='submit_trade')],
                        [InlineKeyboardButton("Змінити", callback_data='edit_trade')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.", reply_markup=reply_markup)
            except ValueError:
                await update.message.reply_text("Введи коректне число для RR (наприклад, 2.5):")
            except Exception as e:
                await update.message.reply_text(f"Помилка при обробці RR: {str(e)}. Спробуй ще раз.")
        else:
            await update.message.reply_text("Спочатку почни додавання трейду через /start.")

# Форматування підсумку
def format_summary(data):
    trigger_str = ", ".join(data.get('Trigger', [])) if isinstance(data.get('Trigger'), list) else data.get('Trigger', '')
    vc_str = ", ".join(data.get('VC', [])) if isinstance(data.get('VC'), list) else data.get('VC', '')
    summary = (
        f"Зібрана інформація:\n"
        f"Pair: {data.get('Pair', '')}\n"
        f"Session: {data.get('Session', '')}\n"
        f"Context: {data.get('Context', '')}\n"
        f"Test POI: {data.get('Test POI', '')}\n"
        f"Delivery to POI: {data.get('Delivery to POI', '')}\n"
        f"Point A: {data.get('Point A', '')}\n"
        f"Trigger: {trigger_str}\n"
        f"VC: {vc_str}\n"
        f"Entry Model: {data.get('Entry Model', '')}\n"
        f"Entry TF: {data.get('Entry TF', '')}\n"
        f"Point B: {data.get('Point B', '')}\n"
        f"SL Position: {data.get('SL Position', '')}\n"
        f"RR: {data.get('RR', '')}"
    )
    return summary

# Обробка кнопок (скорочено для прикладу, повну версію можна взяти з попереднього коду)
async def button(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Button pressed: {query.data} by user {user_id}")
    await query.answer()
    
    async with user_data_lock:
        if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
            await query.edit_message_text("Спочатку авторизуйся через /start.")
            return
        if 'parent_page_id' not in user_data[auth_key]:
            await query.edit_message_text("Спочатку введи ID сторінки через /start.")
            return
        
        logger.debug(f"Processing callback_data: {query.data}")
        if 'Trigger' not in user_data[auth_key] or not isinstance(user_data[auth_key]['Trigger'], list):
            user_data[auth_key]['Trigger'] = []
        if 'VC' not in user_data[auth_key] or not isinstance(user_data[auth_key]['VC'], list):
            user_data[auth_key]['VC'] = []

    if query.data == 'add_trade':
        logger.info(f"User {user_id} pressed 'Add Trade'")
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Pair?', reply_markup=reply_markup)
    # Додайте решту логіки кнопок з попереднього коду, якщо потрібно

# Головна функція для запуску бота
def main():
    logger.info("Starting bot...")
    try:
        request = HTTPXRequest(connection_pool_size=8, read_timeout=60, write_timeout=60)
        application = Application.builder().token(TELEGRAM_TOKEN).request(request).build()
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CallbackQueryHandler(button))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        logger.info("Bot handlers registered. Starting polling...")
        application.run_polling(allowed_updates=["message", "callback_query"], timeout=60)
    except Exception as e:
        logger.critical(f"Bot crashed: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    main()