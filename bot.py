import requests
import json
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, filters
)
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

# Визначення станів
START, PAIR, SESSION, CONTEXT, TEST_POI, DELIVERY, POINT_A, TRIGGER, VC, ENTRY_MODEL, ENTRY_TF, POINT_B, SL_POSITION, RR, SUMMARY = range(15)

# Головне меню (тільки ReplyKeyboardMarkup)
MAIN_MENU = ReplyKeyboardMarkup(
    [["Додати новий трейд", "Переглянути останній трейд"], ["5 останніх трейдів", "Повторна авторизація"]],
    resize_keyboard=True,
    one_time_keyboard=True
)

# Функція для отримання ID бази "Classification"
def fetch_classification_db_id(page_id, notion_token):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {"Authorization": f"Bearer {notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    response = requests.get(url, headers=headers)
    return response.json().get("results", [{}])[0].get("id") if response.status_code == 200 and "Classification" in response.text else None

# Функція для створення сторінки в Notion
def create_notion_page(user_id):
    url = 'https://api.notion.com/v1/pages'
    headers = {'Authorization': f'Bearer {user_data[user_id]["notion_token"]}', 'Content-Type': 'application/json', 'Notion-Version': "2022-06-28"}
    trigger_values = user_data[user_id].get('Trigger', [])
    vc_values = user_data[user_id].get('VC', [])
    current_date = datetime.now().strftime("%Y-%m-%d")
    max_num = get_max_num(user_data[user_id]['classification_db_id'], user_data[user_id]["notion_token"])
    new_num = max_num + 1
    
    payload = {
        'parent': {'database_id': user_data[user_id]['classification_db_id']},
        'properties': {
            'Title': {'title': [{'text': {'content': 'Trade'}}]},
            'Num': {'number': new_num},
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
    
    response = requests.post(url, json=payload, headers=headers)
    return response.json()['id'], new_num if response.status_code == 200 else (None, None)

# Функція для отримання максимального Num
def get_max_num(classification_db_id, notion_token):
    url = f"https://api.notion.com/v1/databases/{classification_db_id}/query"
    headers = {"Authorization": f"Bearer {notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    payload = {"sorts": [{"property": "Num", "direction": "descending"}], "page_size": 1}
    response = requests.post(url, json=payload, headers=headers)
    return response.json().get("results", [{}])[0]["properties"].get("Num", {}).get("number", 0) if response.status_code == 200 else 0

# Функція для отримання властивостей сторінки з Notion
def fetch_page_properties(page_id, notion_token):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {"Authorization": f"Bearer {notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    data = response.json()
    properties = data.get('properties', {})
    return {
        'Num': properties.get('Num', {}).get('number', "Немає даних"),
        'Date': properties.get('Date', {}).get('date', {}).get('start', "Немає даних"),
        'Score': properties.get('Score', {}).get('formula', {}).get('number', "Немає даних"),
        'Trade Class': properties.get('Trade Class', {}).get('formula', {}).get('string', "Немає даних"),
        'Offer Risk': properties.get('Offer Risk', {}).get('formula', {}).get('number', "Немає даних")
    }

# Функція для отримання 5 останніх трейдів з Notion
def fetch_last_five_trades(classification_db_id, notion_token):
    url = f"https://api.notion.com/v1/databases/{classification_db_id}/query"
    headers = {"Authorization": f"Bearer {notion_token}", "Content-Type": "application/json", "Notion-Version": "2022-06-28"}
    payload = {"sorts": [{"property": "Num", "direction": "descending"}], "page_size": 5}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        return None
    results = response.json().get("results", [])
    trades = []
    for result in results:
        props = result.get("properties", {})
        trades.append({
            'Num': props.get('Num', {}).get('number', "Немає даних"),
            'Date': props.get('Date', {}).get('date', {}).get('start', "Немає даних"),
            'Score': props.get('Score', {}).get('formula', {}).get('number', "Немає даних"),
            'Trade Class': props.get('Trade Class', {}).get('formula', {}).get('string', "Немає даних"),
            'Offer Risk': props.get('Offer Risk', {}).get('formula', {}).get('number', "Немає даних")
        })
    return trades

# Форматування підсумку
def format_summary(data):
    trigger_str = ", ".join(data.get('Trigger', [])) if data.get('Trigger') else ''
    vc_str = ", ".join(data.get('VC', [])) if data.get('VC') else ''
    return (
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

# Обробка /start
async def start(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Start command received for user_id: {user_id}")
    async with user_data_lock:
        if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
            instructions = (
                "Щоб використовувати бота:\n"
                "1. Скопіюй сторінку за посиланням: https://www.notion.so/A-B-C-position-Final-Bot-1a084b079a8280d29d5ecc9316e02c5d\n"
                "2. Авторизуйся нижче і введи ID батьківської сторінки 'A-B-C position Final Bot' (32 символи з URL)."
            )
            auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
            keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
            await update.message.reply_text(instructions, reply_markup=InlineKeyboardMarkup(keyboard))
            return ConversationHandler.END
        elif 'parent_page_id' not in user_data[auth_key]:
            await update.message.reply_text('Введи ID батьківської сторінки "A-B-C position Final Bot" (32 символи з URL):')
            return ConversationHandler.END
        elif 'classification_db_id' not in user_data[auth_key]:
            classification_db_id = fetch_classification_db_id(user_data[auth_key]['parent_page_id'], user_data[auth_key]['notion_token'])
            if classification_db_id:
                user_data[auth_key]['classification_db_id'] = classification_db_id
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                await update.message.reply_text('Привіт! Вибери дію:', reply_markup=MAIN_MENU)
                return START
            else:
                await update.message.reply_text('Помилка: не вдалося знайти базу "Classification". Перевір правильність ID сторінки.')
                return ConversationHandler.END
        else:
            await update.message.reply_text('Привіт! Вибери дію:', reply_markup=MAIN_MENU)
            return START

# Обробка головного меню
async def main_menu(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    text = update.message.text
    logger.debug(f"Main menu processing for user_id: {user_id}, text: {text}")
    
    if text == "Додати новий трейд":
        logger.debug(f"User {user_id} selected 'Додати новий трейд'")
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD'), InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY'), InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')],
            [InlineKeyboardButton("Обрати Шаблон", callback_data='template'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await update.message.reply_text('Pair?', reply_markup=InlineKeyboardMarkup(keyboard))
        return PAIR
    elif text == "Переглянути останній трейд":
        logger.debug(f"User {user_id} selected 'Переглянути останній трейд'")
        async with user_data_lock:
            if 'last_trades' in user_data[auth_key] and user_data[auth_key]['last_trades']:
                last_trade = user_data[auth_key]['last_trades'][0]['properties']
                message = (
                    f"Трейд №: {last_trade.get('Num', 'Немає даних')}\n"
                    f"Доданий: {last_trade.get('Date', 'Немає даних')}\n"
                    f"Оцінка трейду: {last_trade.get('Score', 'Немає даних')}\n"
                    f"Категорія трейду: {last_trade.get('Trade Class', 'Немає даних')}\n"
                    f"Ризик: {last_trade.get('Offer Risk', 'Немає даних')}%"
                )
                await update.message.reply_text(f"Останній трейд:\n{message}", reply_markup=MAIN_MENU)
            else:
                await update.message.reply_text("Ще немає відправлених трейдів.", reply_markup=MAIN_MENU)
        return START
    elif text == "5 останніх трейдів":
        logger.debug(f"User {user_id} selected '5 останніх трейдів'")
        async with user_data_lock:
            trades = fetch_last_five_trades(user_data[auth_key]['classification_db_id'], user_data[auth_key]['notion_token'])
            if trades:
                message = "Останні 5 трейдів:\n"
                for trade in trades:
                    message += (
                        f"Трейд №: {trade['Num']}\n"
                        f"Доданий: {trade['Date']}\n"
                        f"Оцінка: {trade['Score']}\n"
                        f"Категорія: {trade['Trade Class']}\n"
                        f"Ризик: {trade['Offer Risk']}%\n\n"
                    )
                await update.message.reply_text(message.strip(), reply_markup=MAIN_MENU)
            else:
                await update.message.reply_text("Не вдалося отримати трейди з Notion.", reply_markup=MAIN_MENU)
        return START
    elif text == "Повторна авторизація":
        logger.debug(f"User {user_id} selected 'Повторна авторизація'")
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
        await update.message.reply_text("Натисни для повторної авторизації:", reply_markup=InlineKeyboardMarkup(keyboard))
        return START
    logger.debug(f"Unknown text '{text}' received in main_menu for user_id: {user_id}")
    await update.message.reply_text("Привіт! Вибери дію:", reply_markup=MAIN_MENU)
    return START

# Обробка етапу Pair
async def pair(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Pair state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "template":
        await query.edit_message_text("Шаблони в розробці!")
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD'), InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY'), InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')],
            [InlineKeyboardButton("Обрати Шаблон", callback_data='template'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await context.bot.send_message(chat_id=query.message.chat_id, text="Pair?", reply_markup=InlineKeyboardMarkup(keyboard))
        return PAIR
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Pair'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Asia", callback_data='session_Asia'), InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
        [InlineKeyboardButton("London", callback_data='session_London'), InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
        [InlineKeyboardButton("New York", callback_data='session_New York')],
        [InlineKeyboardButton("Назад", callback_data='back_to_pair'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Session?', reply_markup=InlineKeyboardMarkup(keyboard))
    return SESSION

# Обробка етапу Session
async def session(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Session state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_pair":
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD'), InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY'), InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')],
            [InlineKeyboardButton("Обрати Шаблон", callback_data='template'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Pair?', reply_markup=InlineKeyboardMarkup(keyboard))
        return PAIR
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Session'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("By Context", callback_data='context_By Context'), InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
        [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')],
        [InlineKeyboardButton("Назад", callback_data='back_to_session'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Context?', reply_markup=InlineKeyboardMarkup(keyboard))
    return CONTEXT

# Обробка етапу Context
async def context(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Context state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_session":
        keyboard = [
            [InlineKeyboardButton("Asia", callback_data='session_Asia'), InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
            [InlineKeyboardButton("London", callback_data='session_London'), InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
            [InlineKeyboardButton("New York", callback_data='session_New York')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pair'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Session?', reply_markup=InlineKeyboardMarkup(keyboard))
        return SESSION
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Context'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal'), InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')],
        [InlineKeyboardButton("Назад", callback_data='back_to_context'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Test POI?', reply_markup=InlineKeyboardMarkup(keyboard))
    return TEST_POI

# Обробка етапу Test POI
async def test_poi(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Test POI state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_context":
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context'), InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')],
            [InlineKeyboardButton("Назад", callback_data='back_to_session'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Context?', reply_markup=InlineKeyboardMarkup(keyboard))
        return CONTEXT
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Test POI'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive'), InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')],
        [InlineKeyboardButton("Назад", callback_data='back_to_test_poi'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Delivery to POI?', reply_markup=InlineKeyboardMarkup(keyboard))
    return DELIVERY

# Обробка етапу Delivery to POI
async def delivery(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Delivery state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_test_poi":
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal'), InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')],
            [InlineKeyboardButton("Назад", callback_data='back_to_context'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Test POI?', reply_markup=InlineKeyboardMarkup(keyboard))
        return TEST_POI
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Delivery to POI'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid'), InlineKeyboardButton("RB", callback_data='pointa_RB')],
        [InlineKeyboardButton("FVG", callback_data='pointa_FVG'), InlineKeyboardButton("SNR", callback_data='pointa_SNR')],
        [InlineKeyboardButton("Назад", callback_data='back_to_delivery'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Point A?', reply_markup=InlineKeyboardMarkup(keyboard))
    return POINT_A

# Обробка етапу Point A
async def point_a(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Point A state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_delivery":
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive'), InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')],
            [InlineKeyboardButton("Назад", callback_data='back_to_test_poi'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Delivery to POI?', reply_markup=InlineKeyboardMarkup(keyboard))
        return DELIVERY
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Point A'] = query.data.split('_')[1]
        user_data[auth_key]['Trigger'] = []
    keyboard = [
        [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing'), InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
        [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
        [InlineKeyboardButton("Назад", callback_data='back_to_point_a'), InlineKeyboardButton("Готово", callback_data='done_trigger')]
    ]
    await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
    return TRIGGER

# Обробка етапу Trigger
async def trigger(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Trigger state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_point_a":
        keyboard = [
            [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid'), InlineKeyboardButton("RB", callback_data='pointa_RB')],
            [InlineKeyboardButton("FVG", callback_data='pointa_FVG'), InlineKeyboardButton("SNR", callback_data='pointa_SNR')],
            [InlineKeyboardButton("Назад", callback_data='back_to_delivery'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Point A?', reply_markup=InlineKeyboardMarkup(keyboard))
        return POINT_A
    elif query.data == "done_trigger":
        async with user_data_lock:
            if not user_data[auth_key]['Trigger']:
                await query.edit_message_text("Обери хоча б один Trigger!")
                keyboard = [
                    [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing'), InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
                    [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
                    [InlineKeyboardButton("Назад", callback_data='back_to_point_a'), InlineKeyboardButton("Готово", callback_data='done_trigger')]
                ]
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
                return TRIGGER
            user_data[auth_key]['VC'] = []
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR'), InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
            [InlineKeyboardButton("Назад", callback_data='back_to_trigger'), InlineKeyboardButton("Готово", callback_data='done_vc')]
        ]
        await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
        return VC

    trigger_value = query.data.split('_')[1]
    async with user_data_lock:
        if trigger_value in user_data[auth_key]['Trigger']:
            user_data[auth_key]['Trigger'].remove(trigger_value)
        else:
            user_data[auth_key]['Trigger'].append(trigger_value)
    keyboard = [
        [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing'), InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
        [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
        [InlineKeyboardButton("Назад", callback_data='back_to_point_a'), InlineKeyboardButton("Готово", callback_data='done_trigger')]
    ]
    await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
    return TRIGGER

# Обробка етапу VC
async def vc(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"VC state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_trigger":
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing'), InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
            [InlineKeyboardButton("Назад", callback_data='back_to_point_a'), InlineKeyboardButton("Готово", callback_data='done_trigger')]
        ]
        await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
        return TRIGGER
    elif query.data == "done_vc":
        async with user_data_lock:
            if not user_data[auth_key]['VC']:
                await query.edit_message_text("Обери хоча б один VC!")
                keyboard = [
                    [InlineKeyboardButton("SNR", callback_data='vc_SNR'), InlineKeyboardButton("FVG", callback_data='vc_FVG')],
                    [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
                    [InlineKeyboardButton("Назад", callback_data='back_to_trigger'), InlineKeyboardButton("Готово", callback_data='done_vc')]
                ]
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
                return VC
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM'), InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR'), InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')],
            [InlineKeyboardButton("Назад", callback_data='back_to_vc'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Entry Model?', reply_markup=InlineKeyboardMarkup(keyboard))
        return ENTRY_MODEL

    vc_value = query.data.split('_')[1]
    async with user_data_lock:
        if vc_value in user_data[auth_key]['VC']:
            user_data[auth_key]['VC'].remove(vc_value)
        else:
            user_data[auth_key]['VC'].append(vc_value)
    keyboard = [
        [InlineKeyboardButton("SNR", callback_data='vc_SNR'), InlineKeyboardButton("FVG", callback_data='vc_FVG')],
        [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
        [InlineKeyboardButton("Назад", callback_data='back_to_trigger'), InlineKeyboardButton("Готово", callback_data='done_vc')]
    ]
    await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
    return VC

# Обробка етапу Entry Model
async def entry_model(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Entry Model state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_vc":
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR'), InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')],
            [InlineKeyboardButton("Назад", callback_data='back_to_trigger'), InlineKeyboardButton("Готово", callback_data='done_vc')]
        ]
        await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
        return VC
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Entry Model'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("3m", callback_data='entrytf_3m'), InlineKeyboardButton("5m", callback_data='entrytf_5m')],
        [InlineKeyboardButton("15m", callback_data='entrytf_15m'), InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
        [InlineKeyboardButton("4H", callback_data='entrytf_4H')],
        [InlineKeyboardButton("Назад", callback_data='back_to_entry_model'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Entry TF?', reply_markup=InlineKeyboardMarkup(keyboard))
    return ENTRY_TF

# Обробка етапу Entry TF
async def entry_tf(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Entry TF state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_entry_model":
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM'), InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR'), InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')],
            [InlineKeyboardButton("Назад", callback_data='back_to_vc'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Entry Model?', reply_markup=InlineKeyboardMarkup(keyboard))
        return ENTRY_MODEL
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Entry TF'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing'), InlineKeyboardButton("FVG", callback_data='pointb_FVG')],
        [InlineKeyboardButton("Назад", callback_data='back_to_entry_tf'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('Point B?', reply_markup=InlineKeyboardMarkup(keyboard))
    return POINT_B

# Обробка етапу Point B
async def point_b(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Point B state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_entry_tf":
        keyboard = [
            [InlineKeyboardButton("3m", callback_data='entrytf_3m'), InlineKeyboardButton("5m", callback_data='entrytf_5m')],
            [InlineKeyboardButton("15m", callback_data='entrytf_15m'), InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
            [InlineKeyboardButton("4H", callback_data='entrytf_4H')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entry_model'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Entry TF?', reply_markup=InlineKeyboardMarkup(keyboard))
        return ENTRY_TF
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['Point B'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
        [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
        [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')],
        [InlineKeyboardButton("Назад", callback_data='back_to_point_b'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
    ]
    await query.edit_message_text('SL Position?', reply_markup=InlineKeyboardMarkup(keyboard))
    return SL_POSITION

# Обробка етапу SL Position
async def sl_position(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"SL Position state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "back_to_point_b":
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing'), InlineKeyboardButton("FVG", callback_data='pointb_FVG')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entry_tf'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Point B?', reply_markup=InlineKeyboardMarkup(keyboard))
        return POINT_B
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START

    async with user_data_lock:
        user_data[auth_key]['SL Position'] = query.data.split('_')[1]
    await query.edit_message_text('Введи RR вручну (наприклад, 2.5):', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Скасувати", callback_data='cancel')]]))
    return RR

# Обробка етапу RR
async def rr(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    text = update.message.text if update.message else None
    logger.debug(f"RR state entered for user_id: {user_id}, text or callback: {text or update.callback_query.data}")

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if query.data == "cancel":
            async with user_data_lock:
                user_data[auth_key].clear()
            await query.edit_message_text("Скасовано.")
            await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
            return START
        return RR

    if not text:
        return RR

    try:
        rr = float(text)
        async with user_data_lock:
            user_data[auth_key]['RR'] = rr
        summary = format_summary(user_data[auth_key])
        keyboard = [
            [InlineKeyboardButton("Відправити", callback_data='submit_trade'), InlineKeyboardButton("Змінити", callback_data='edit_trade')],
            [InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await update.message.reply_text(f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUMMARY
    except ValueError:
        await update.message.reply_text("Помилка, введіть число (наприклад, 2.5):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Скасувати", callback_data='cancel')]]))
        return RR

# Обробка підсумку
async def summary(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.debug(f"Summary state entered for user_id: {user_id}, callback_data: {query.data}")
    await query.answer()

    if query.data == "submit_trade":
        logger.debug(f"User {user_id} submitting trade")
        page_id, trade_num = create_notion_page(auth_key)
        if page_id:
            async with user_data_lock:
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
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                user_data[auth_key].clear()

            await query.edit_message_text("Трейд успішно додано до Notion!")
            await asyncio.sleep(5)
            properties = fetch_page_properties(page_id, user_data[auth_key]['notion_token'])
            if properties:
                message = (
                    f"Трейд №: {properties.get('Num', 'Немає даних')}\n"
                    f"Доданий: {properties.get('Date', 'Немає даних')}\n"
                    f"Оцінка трейду: {properties.get('Score', 'Немає даних')}\n"
                    f"Категорія трейду: {properties.get('Trade Class', 'Немає даних')}\n"
                    f"Ризик: {properties.get('Offer Risk', 'Немає даних')}%"
                )
                await context.bot.send_message(chat_id=query.message.chat_id, text=message, reply_markup=MAIN_MENU)
            else:
                await context.bot.send_message(chat_id=query.message.chat_id, text=f"ID трейду: {trade_num}\nНе вдалося отримати оцінку.", reply_markup=MAIN_MENU)
            return START
        else:
            await query.edit_message_text("Помилка при відправці трейду в Notion.")
            await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
            return START
    elif query.data == "edit_trade":
        logger.debug(f"User {user_id} editing trade")
        keyboard = [
            [InlineKeyboardButton("Pair", callback_data='edit_pair'), InlineKeyboardButton("Session", callback_data='edit_session')],
            [InlineKeyboardButton("Повернутися", callback_data='back_to_summary'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text("Який параметр хочеш змінити?", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUMMARY
    elif query.data == "edit_pair":
        logger.debug(f"User {user_id} editing Pair")
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD'), InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY'), InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')],
            [InlineKeyboardButton("Обрати Шаблон", callback_data='template'), InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text('Pair?', reply_markup=InlineKeyboardMarkup(keyboard))
        return PAIR
    elif query.data == "back_to_summary":
        logger.debug(f"User {user_id} returning to summary")
        summary = format_summary(user_data[auth_key])
        keyboard = [
            [InlineKeyboardButton("Відправити", callback_data='submit_trade'), InlineKeyboardButton("Змінити", callback_data='edit_trade')],
            [InlineKeyboardButton("Скасувати", callback_data='cancel')]
        ]
        await query.edit_message_text(f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUMMARY
    elif query.data == "cancel":
        async with user_data_lock:
            user_data[auth_key].clear()
        await query.edit_message_text("Скасовано.")
        await context.bot.send_message(chat_id=query.message.chat_id, text="Привіт! Вибери дію:", reply_markup=MAIN_MENU)
        return START
    return SUMMARY

# Головна функція для запуску бота
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).write_timeout(30).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)],
            PAIR: [CallbackQueryHandler(pair)],
            SESSION: [CallbackQueryHandler(session)],
            CONTEXT: [CallbackQueryHandler(context)],
            TEST_POI: [CallbackQueryHandler(test_poi)],
            DELIVERY: [CallbackQueryHandler(delivery)],
            POINT_A: [CallbackQueryHandler(point_a)],
            TRIGGER: [CallbackQueryHandler(trigger)],
            VC: [CallbackQueryHandler(vc)],
            ENTRY_MODEL: [CallbackQueryHandler(entry_model)],
            ENTRY_TF: [CallbackQueryHandler(entry_tf)],
            POINT_B: [CallbackQueryHandler(point_b)],
            SL_POSITION: [CallbackQueryHandler(sl_position)],
            RR: [MessageHandler(filters.TEXT & ~filters.COMMAND, rr), CallbackQueryHandler(rr)],
            SUMMARY: [CallbackQueryHandler(summary)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()