import requests
import json
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import heroku3
import asyncio
from datetime import datetime

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Конфігурація через змінні середовища
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

user_data = json.loads(os.getenv('HEROKU_USER_DATA', '{}'))
user_data_lock = asyncio.Lock()
logger.info(f"Initial user_data loaded from HEROKU_USER_DATA: {json.dumps(user_data, indent=2)}")

# Функція для отримання ID бази "Classification" із батьківської сторінки
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

# Функція для отримання максимального значення "Num" із бази
def get_max_num(classification_db_id, notion_token):
    logger.debug(f"Fetching max Num from database {classification_db_id}")
    url = f"https://api.notion.com/v1/databases/{classification_db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    payload = {
        "sorts": [{"property": "Num", "direction": "descending"}],
        "page_size": 1  # Беремо лише останній запис із найбільшим Num
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch max Num: {response.status_code} - {response.text}")
        return 0  # Якщо помилка, починаємо з 1
    data = response.json()
    results = data.get("results", [])
    if results:
        max_num = results[0]["properties"].get("Num", {}).get("number", 0)
        logger.info(f"Max Num found: {max_num}")
        return max_num
    logger.info("No trades found, starting Num from 1")
    return 0  # Якщо база порожня, починаємо з 1

# Функція для створення сторінки в Notion із датою, назвою "Trade" і порядковим номером "Num"
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
    current_date = datetime.now().strftime("%Y-%m-%d")  # Формат ISO 8601: 2025-02-22
    max_num = get_max_num(user_data[user_id]['classification_db_id'], user_data[user_id]["notion_token"])
    new_num = max_num + 1  # Новий порядковий номер
    
    payload = {
        'parent': {'database_id': user_data[user_id]['classification_db_id']},
        'properties': {
            'Title': {'title': [{'text': {'content': 'Trade'}}]},  # Припускаємо, що колонка називається "Title"
            'Num': {'number': new_num},  # Додаємо порядковий номер
            'Date': {'date': {'start': current_date}},
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
        logger.info(f"Successfully created page for user {user_id} with page_id: {page_id}, Num: {new_num}")
        return page_id, new_num
    else:
        logger.error(f"Notion API error for user {user_id}: {response.status_code} - {response.text}")
        return None, None

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
    logger.debug(f"Properties for page {page_id}: {json.dumps(properties, indent=2)}")
    
    num = properties.get('Num', {}).get('number', "Немає даних")
    date_property = properties.get('Date', {})
    date = date_property.get('date', "Немає даних") if isinstance(date_property, dict) else "Немає даних"
    if isinstance(date, dict):  # Якщо 'date' повертає словник (наприклад, {"start": "2025-02-22"})
        date = date.get('start', "Немає даних")
    score = properties.get('Score', {}).get('formula', {}).get('number', "Немає даних")
    trade_class = properties.get('Trade Class', {}).get('formula', {}).get('string', "Немає даних")
    offer_risk = properties.get('Offer Risk', {}).get('formula', {}).get('number', "Немає даних")
    
    logger.info(f"Retrieved properties - Num: {num}, Date: {date}, Score: {score}, Trade Class: {trade_class}, Offer Risk: {offer_risk}")
    return {
        'Num': num,
        'Date': date,
        'Score': score,
        'Trade Class': trade_class,
        'Offer Risk': offer_risk
    }

# Функція для отримання останніх 5 трейдів із бази Notion
def fetch_last_5_trades(classification_db_id, notion_token):
    logger.debug(f"Fetching last 5 trades from database {classification_db_id}")
    url = f"https://api.notion.com/v1/databases/{classification_db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    payload = {
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        "page_size": 5
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        logger.error(f"Failed to fetch trades: {response.status_code} - {response.text}")
        return None
    data = response.json()
    trades = []
    for page in data.get("results", []):
        page_id = page["id"]
        properties = fetch_page_properties(page_id, notion_token)
        if properties:
            trades.append({
                "Num": properties["Num"],
                "Date": properties["Date"],
                "Score": properties["Score"],
                "Trade Class": properties["Trade Class"],
                "Offer Risk": properties["Offer Risk"]
            })
    logger.info(f"Retrieved {len(trades)} trades")
    return trades

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
            classification_db_id = fetch_classification_db_id(user_data[auth_key]['parent_page_id'], user_data[auth_key]['notion_token'])
            if classification_db_id:
                user_data[auth_key]['classification_db_id'] = classification_db_id
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                keyboard = [
                    [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                    [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
                    [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)
            else:
                await update.message.reply_text('Помилка: не вдалося знайти базу "Classification". Перевір правильність ID сторінки.')
        else:
            keyboard = [
                [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
                [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
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
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
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

# Обробка кнопок
async def button(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Button callback received from user {user_id}: {query.data}")
    
    await query.answer()
    
    async with user_data_lock:
        if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
            await query.edit_message_text("Спочатку авторизуйся через /start.")
            return
        if 'parent_page_id' not in user_data[auth_key]:
            await query.edit_message_text("Спочатку введи ID сторінки через /start.")
            return
        
        if 'Trigger' not in user_data[auth_key] or not isinstance(user_data[auth_key]['Trigger'], list):
            user_data[auth_key]['Trigger'] = []
        if 'VC' not in user_data[auth_key] or not isinstance(user_data[auth_key]['VC'], list):
            user_data[auth_key]['VC'] = []

    if query.data == 'add_trade':
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Pair?', reply_markup=reply_markup)
    
    elif query.data.startswith('pair_'):
        async with user_data_lock:
            user_data[auth_key]['Pair'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("Asia", callback_data='session_Asia')],
            [InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
            [InlineKeyboardButton("London", callback_data='session_London')],
            [InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
            [InlineKeyboardButton("New York", callback_data='session_New York')],
            [InlineKeyboardButton("Назад", callback_data='back_to_start')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Session?', reply_markup=reply_markup)
    
    elif query.data.startswith('session_'):
        async with user_data_lock:
            user_data[auth_key]['Session'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pair')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Context?', reply_markup=reply_markup)
    
    elif query.data.startswith('context_'):
        async with user_data_lock:
            user_data[auth_key]['Context'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')],
            [InlineKeyboardButton("Назад", callback_data='back_to_session')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('testpoi_'):
        async with user_data_lock:
            user_data[auth_key]['Test POI'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')],
            [InlineKeyboardButton("Назад", callback_data='back_to_context')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Delivery to POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('delivery_'):
        async with user_data_lock:
            user_data[auth_key]['Delivery to POI'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid')],
            [InlineKeyboardButton("RB", callback_data='pointa_RB')],
            [InlineKeyboardButton("FVG", callback_data='pointa_FVG')],
            [InlineKeyboardButton("SNR", callback_data='pointa_SNR')],
            [InlineKeyboardButton("Назад", callback_data='back_to_testpoi')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point A?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointa_'):
        async with user_data_lock:
            user_data[auth_key]['Point A'] = query.data.split('_')[1]
            user_data[auth_key]['Trigger'] = []
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
            [InlineKeyboardButton("Готово", callback_data='trigger_done')],
            [InlineKeyboardButton("Назад", callback_data='back_to_delivery')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data.startswith('trigger_') and query.data != 'trigger_done':
        trigger_value = query.data.split('_')[1]
        async with user_data_lock:
            if trigger_value in user_data[auth_key]['Trigger']:
                user_data[auth_key]['Trigger'].remove(trigger_value)
            else:
                user_data[auth_key]['Trigger'].append(trigger_value)
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
            [InlineKeyboardButton("Готово", callback_data='trigger_done')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pointa')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'trigger_done':
        async with user_data_lock:
            if not user_data[auth_key]['Trigger']:
                await query.edit_message_text("Обери хоча б один Trigger!")
                return
            user_data[auth_key]['VC'] = []
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
            [InlineKeyboardButton("Готово", callback_data='vc_done')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pointa')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data.startswith('vc_') and query.data != 'vc_done':
        vc_value = query.data.split('_')[1]
        async with user_data_lock:
            if vc_value in user_data[auth_key]['VC']:
                user_data[auth_key]['VC'].remove(vc_value)
            else:
                user_data[auth_key]['VC'].append(vc_value)
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
            [InlineKeyboardButton("Готово", callback_data='vc_done')],
            [InlineKeyboardButton("Назад", callback_data='back_to_trigger')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'vc_done':
        async with user_data_lock:
            if not user_data[auth_key]['VC']:
                await query.edit_message_text("Обери хоча б один VC!")
                return
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')],
            [InlineKeyboardButton("Назад", callback_data='back_to_vc')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry Model?', reply_markup=reply_markup)
    
    elif query.data.startswith('entrymodel_'):
        async with user_data_lock:
            user_data[auth_key]['Entry Model'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("3m", callback_data='entrytf_3m')],
            [InlineKeyboardButton("5m", callback_data='entrytf_5m')],
            [InlineKeyboardButton("15m", callback_data='entrytf_15m')],
            [InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
            [InlineKeyboardButton("4H", callback_data='entrytf_4H')],
            [InlineKeyboardButton("Назад", callback_data='back_to_vc')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry TF?', reply_markup=reply_markup)
    
    elif query.data.startswith('entrytf_'):
        async with user_data_lock:
            user_data[auth_key]['Entry TF'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entrymodel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point B?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointb_'):
        async with user_data_lock:
            user_data[auth_key]['Point B'] = query.data.split('_')[1]
        keyboard = [
            [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
            [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
            [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entrytf')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('SL Position?', reply_markup=reply_markup)
    
    elif query.data.startswith('slposition_'):
        async with user_data_lock:
            user_data[auth_key]['SL Position'] = query.data.split('_')[1]
            user_data[auth_key]['waiting_for_rr'] = True
        await context.bot.send_message(chat_id=query.message.chat_id, text='Введи RR вручну (наприклад, 2.5):', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data='back_to_pointb')]]))

    # Логіка повернення назад
    elif query.data == 'back_to_start':
        keyboard = [
            [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
            [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
            [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Привіт! Вибери дію:', reply_markup=reply_markup)
    
    elif query.data == 'back_to_pair':
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Pair?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_session':
        keyboard = [
            [InlineKeyboardButton("Asia", callback_data='session_Asia')],
            [InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
            [InlineKeyboardButton("London", callback_data='session_London')],
            [InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
            [InlineKeyboardButton("New York", callback_data='session_New York')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pair')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Session?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_context':
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')],
            [InlineKeyboardButton("Назад", callback_data='back_to_session')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Context?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_testpoi':
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')],
            [InlineKeyboardButton("Назад", callback_data='back_to_context')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_delivery':
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')],
            [InlineKeyboardButton("Назад", callback_data='back_to_testpoi')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Delivery to POI?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_pointa':
        keyboard = [
            [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid')],
            [InlineKeyboardButton("RB", callback_data='pointa_RB')],
            [InlineKeyboardButton("FVG", callback_data='pointa_FVG')],
            [InlineKeyboardButton("SNR", callback_data='pointa_SNR')],
            [InlineKeyboardButton("Назад", callback_data='back_to_delivery')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point A?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_trigger':
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
            [InlineKeyboardButton("Готово", callback_data='trigger_done')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pointa')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'back_to_vc':
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
            [InlineKeyboardButton("Готово", callback_data='vc_done')],
            [InlineKeyboardButton("Назад", callback_data='back_to_trigger')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'back_to_entrymodel':
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')],
            [InlineKeyboardButton("Назад", callback_data='back_to_vc')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry Model?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_entrytf':
        keyboard = [
            [InlineKeyboardButton("3m", callback_data='entrytf_3m')],
            [InlineKeyboardButton("5m", callback_data='entrytf_5m')],
            [InlineKeyboardButton("15m", callback_data='entrytf_15m')],
            [InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
            [InlineKeyboardButton("4H", callback_data='entrytf_4H')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entrymodel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry TF?', reply_markup=reply_markup)
    
    elif query.data == 'back_to_pointb':
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entrytf')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point B?', reply_markup=reply_markup)

    # Логіка підтвердження трейду
    elif query.data == 'submit_trade':
        async with user_data_lock:
            page_id, trade_num = create_notion_page(auth_key)
            if page_id:
                user_data[auth_key]['last_trade'] = {
                    'id': trade_num,
                    'Pair': user_data[auth_key].get('Pair'),
                    'Session': user_data[auth_key].get('Session'),
                    'Context': user_data[auth_key].get('Context'),
                    'Test POI': user_data[auth_key].get('Test POI'),
                    'Delivery to POI': user_data[auth_key].get('Delivery to POI'),
                    'Point A': user_data[auth_key].get('Point A'),
                    'Trigger': user_data[auth_key].get('Trigger', []).copy(),
                    'VC': user_data[auth_key].get('VC', []).copy(),
                    'Entry Model': user_data[auth_key].get('Entry Model'),
                    'Entry TF': user_data[auth_key].get('Entry TF'),
                    'Point B': user_data[auth_key].get('Point B'),
                    'SL Position': user_data[auth_key].get('SL Position'),
                    'RR': user_data[auth_key].get('RR')
                }
                if 'last_trades' not in user_data[auth_key]:
                    user_data[auth_key]['last_trades'] = []
                user_data[auth_key]['last_trades'].insert(0, {
                    'id': trade_num,
                    'properties': fetch_page_properties(page_id, user_data[auth_key]['notion_token'])
                })
                if len(user_data[auth_key]['last_trades']) > 5:
                    user_data[auth_key]['last_trades'] = user_data[auth_key]['last_trades'][:5]

                await query.edit_message_text("Трейд успішно додано до Notion!")
                
                await asyncio.sleep(5)
                
                properties = fetch_page_properties(page_id, user_data[auth_key]['notion_token'])
                if properties:
                    num = properties['Num'] if properties['Num'] is not None else "Немає даних"
                    date = properties['Date'] if properties['Date'] is not None else "Немає даних"
                    score = properties['Score'] if properties['Score'] is not None else "Немає даних"
                    trade_class = properties['Trade Class'] if properties['Trade Class'] is not None else "Немає даних"
                    offer_risk = properties['Offer Risk'] if properties['Offer Risk'] is not None else "Немає даних"
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"Трейд №: {num}\n"
                             f"Доданий: {date}\n"
                             f"Оцінка трейду: {score}\n"
                             f"Категорія трейду: {trade_class}\n"
                             f"Ризик: {offer_risk}%"
                    )
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"ID трейду: {trade_num}\n"
                             f"Не вдалося отримати оцінку трейду. Перевір логи."
                    )
                
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                for key in ['waiting_for_rr', 'Pair', 'Session', 'Context', 'Test POI', 'Delivery to POI', 'Point A', 
                            'Trigger', 'VC', 'Entry Model', 'Entry TF', 'Point B', 'SL Position', 'RR']:
                    if key in user_data[auth_key]:
                        del user_data[auth_key][key]
                user_data[auth_key]['Trigger'] = []
                user_data[auth_key]['VC'] = []
            else:
                await query.edit_message_text("Помилка при відправці трейду в Notion. Перевір логи.")
        
        if page_id:
            keyboard = [
                [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
                [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=query.message.chat_id, text="Вибери дію:", reply_markup=reply_markup)
    
    elif query.data == 'view_last_trade':
        async with user_data_lock:
            if 'last_trades' in user_data[auth_key] and user_data[auth_key]['last_trades']:
                last_trade = user_data[auth_key]['last_trades'][0]['properties']  # Беремо останній доданий трейд
                num = last_trade['Num'] if last_trade['Num'] is not None else "Немає даних"
                date = last_trade['Date'] if last_trade['Date'] is not None else "Немає даних"
                score = last_trade['Score'] if last_trade['Score'] is not None else "Немає даних"
                trade_class = last_trade['Trade Class'] if last_trade['Trade Class'] is not None else "Немає даних"
                offer_risk = last_trade['Offer Risk'] if last_trade['Offer Risk'] is not None else "Немає даних"
                message = (
                    f"Трейд №: {num}\n"
                    f"Доданий: {date}\n"
                    f"Оцінка трейду: {score}\n"
                    f"Категорія трейду: {trade_class}\n"
                    f"Ризик: {offer_risk}%"
                )
                keyboard = [
                    [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                    [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
                    [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(f"Останній трейд:\n{message}\n\nВибери дію:", reply_markup=reply_markup)
            else:
                keyboard = [
                    [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                    [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text("Ще немає відправлених трейдів. Вибери дію:", reply_markup=reply_markup)
    
    elif query.data == 'view_last_5_trades':
        async with user_data_lock:
            if 'classification_db_id' not in user_data[auth_key]:
                await query.edit_message_text("Помилка: база даних Classification не налаштована.")
                return
            trades = fetch_last_5_trades(user_data[auth_key]['classification_db_id'], user_data[auth_key]['notion_token'])
            if trades:
                message = "Останні 5 трейдів:\n\n"
                for trade in trades:
                    num = trade['Num'] if trade['Num'] is not None else "Немає даних"
                    date = trade['Date'] if trade['Date'] is not None else "Немає даних"
                    score = trade['Score'] if trade['Score'] is not None else "Немає даних"
                    trade_class = trade['Trade Class'] if trade['Trade Class'] is not None else "Немає даних"
                    offer_risk = trade['Offer Risk'] if trade['Offer Risk'] is not None else "Немає даних"
                    message += (
                        f"Трейд №: {num}\n"
                        f"Доданий: {date}\n"
                        f"Оцінка трейду: {score}\n"
                        f"Категорія трейду: {trade_class}\n"
                        f"Ризик: {offer_risk}%\n\n"
                    )
            else:
                message = "Не вдалося отримати останні трейди або їх ще немає."
            
            keyboard = [
                [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
                [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
                [InlineKeyboardButton("5 останніх трейдів", callback_data='view_last_5_trades')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)
    
    elif query.data == 'edit_trade':
        keyboard = [
            [InlineKeyboardButton("Pair", callback_data='edit_pair')],
            [InlineKeyboardButton("Session", callback_data='edit_session')],
            [InlineKeyboardButton("Context", callback_data='edit_context')],
            [InlineKeyboardButton("Test POI", callback_data='edit_testpoi')],
            [InlineKeyboardButton("Delivery to POI", callback_data='edit_delivery')],
            [InlineKeyboardButton("Point A", callback_data='edit_pointa')],
            [InlineKeyboardButton("Trigger", callback_data='edit_trigger')],
            [InlineKeyboardButton("VC", callback_data='edit_vc')],
            [InlineKeyboardButton("Entry Model", callback_data='edit_entrymodel')],
            [InlineKeyboardButton("Entry TF", callback_data='edit_entrytf')],
            [InlineKeyboardButton("Point B", callback_data='edit_pointb')],
            [InlineKeyboardButton("SL Position", callback_data='edit_slposition')],
            [InlineKeyboardButton("RR", callback_data='edit_rr')],
            [InlineKeyboardButton("Повернутися", callback_data='back_to_summary')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Який параметр хочеш змінити?", reply_markup=reply_markup)
    
    elif query.data == 'back_to_summary':
        async with user_data_lock:
            summary = format_summary(user_data[auth_key])
            keyboard = [
                [InlineKeyboardButton("Відправити", callback_data='submit_trade')],
                [InlineKeyboardButton("Змінити", callback_data='edit_trade')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.", reply_markup=reply_markup)

    # Логіка редагування
    elif query.data == 'edit_pair':
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Pair?', reply_markup=reply_markup)
    
    elif query.data == 'edit_session':
        keyboard = [
            [InlineKeyboardButton("Asia", callback_data='session_Asia')],
            [InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
            [InlineKeyboardButton("London", callback_data='session_London')],
            [InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
            [InlineKeyboardButton("New York", callback_data='session_New York')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Session?', reply_markup=reply_markup)
    
    elif query.data == 'edit_context':
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Context?', reply_markup=reply_markup)
    
    elif query.data == 'edit_testpoi':
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    
    elif query.data == 'edit_delivery':
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Delivery to POI?', reply_markup=reply_markup)
    
    elif query.data == 'edit_pointa':
        keyboard = [
            [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid')],
            [InlineKeyboardButton("RB", callback_data='pointa_RB')],
            [InlineKeyboardButton("FVG", callback_data='pointa_FVG')],
            [InlineKeyboardButton("SNR", callback_data='pointa_SNR')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point A?', reply_markup=reply_markup)
    
    elif query.data == 'edit_trigger':
        async with user_data_lock:
            user_data[auth_key]['Trigger'] = []
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
            [InlineKeyboardButton("Готово", callback_data='trigger_done')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'edit_vc':
        async with user_data_lock:
            user_data[auth_key]['VC'] = []
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
            [InlineKeyboardButton("Готово", callback_data='vc_done')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'edit_entrymodel':
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry Model?', reply_markup=reply_markup)
    
    elif query.data == 'edit_entrytf':
        keyboard = [
            [InlineKeyboardButton("3m", callback_data='entrytf_3m')],
            [InlineKeyboardButton("5m", callback_data='entrytf_5m')],
            [InlineKeyboardButton("15m", callback_data='entrytf_15m')],
            [InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
            [InlineKeyboardButton("4H", callback_data='entrytf_4H')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry TF?', reply_markup=reply_markup)
    
    elif query.data == 'edit_pointb':
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point B?', reply_markup=reply_markup)
    
    elif query.data == 'edit_slposition':
        keyboard = [
            [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
            [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
            [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('SL Position?', reply_markup=reply_markup)
    
    elif query.data == 'edit_rr':
        async with user_data_lock:
            user_data[auth_key]['waiting_for_rr'] = True
        await context.bot.send_message(chat_id=query.message.chat_id, text='Введи RR вручну (наприклад, 2.5):')

# Головна функція для запуску бота
def main():
    logger.info("Starting bot with TELEGRAM_TOKEN: [REDACTED]")
    application = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).write_timeout(30).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Bot handlers registered. Starting polling...")
    application.run_polling()

if __name__ == '__main__':
    main()