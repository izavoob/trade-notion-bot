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

# Визначення станів (виправлено range(14) на range(15))
START, PAIR, SESSION, CONTEXT, TEST_POI, DELIVERY, POINT_A, TRIGGER, VC, ENTRY_MODEL, ENTRY_TF, POINT_B, SL_POSITION, RR, SUMMARY = range(15)

# Головне меню
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["Додати новий трейд", "Переглянути останній трейд"],
        ["5 останніх трейдів", "Повторна авторизація"]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Меню для етапу Pair
PAIR_MENU = ReplyKeyboardMarkup(
    [["Обрати Шаблон", "Скасувати"]],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Меню з "Назад" і "Скасувати"
BACK_CANCEL_MENU = ReplyKeyboardMarkup(
    [["Назад", "Скасувати"]],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Меню з "Назад", "Скасувати" і "Готово"
BACK_CANCEL_DONE_MENU = ReplyKeyboardMarkup(
    [["Назад", "Скасувати"], ["Готово"]],
    resize_keyboard=True,
    one_time_keyboard=False
)

# Функція для отримання ID бази "Classification"
def fetch_classification_db_id(page_id, notion_token):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    data = response.json()
    for block in data.get("results", []):
        if block["type"] == "child_database" and "Classification" in block["child_database"]["title"]:
            return block["id"]
    return None

# Функція для створення сторінки в Notion
def create_notion_page(user_id):
    url = 'https://api.notion.com/v1/pages'
    headers = {
        'Authorization': f'Bearer {user_data[user_id]["notion_token"]}',
        'Content-Type': 'application/json',
        'Notion-Version': "2022-06-28"
    }
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
    if response.status_code == 200:
        page_id = response.json()['id']
        return page_id, new_num
    return None, None

# Функція для отримання максимального Num
def get_max_num(classification_db_id, notion_token):
    url = f"https://api.notion.com/v1/databases/{classification_db_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    payload = {"sorts": [{"property": "Num", "direction": "descending"}], "page_size": 1}
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        return 0
    data = response.json()
    results = data.get("results", [])
    return results[0]["properties"].get("Num", {}).get("number", 0) if results else 0

# Функція для отримання властивостей сторінки з Notion
def fetch_page_properties(page_id, notion_token):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    data = response.json()
    properties = data.get('properties', {})
    num = properties.get('Num', {}).get('number', "Немає даних")
    date = properties.get('Date', {}).get('date', {}).get('start', "Немає даних")
    score = properties.get('Score', {}).get('formula', {}).get('number', "Немає даних")
    trade_class = properties.get('Trade Class', {}).get('formula', {}).get('string', "Немає даних")
    offer_risk = properties.get('Offer Risk', {}).get('formula', {}).get('number', "Немає даних")
    return {'Num': num, 'Date': date, 'Score': score, 'Trade Class': trade_class, 'Offer Risk': offer_risk}

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
    
    if text == "Додати новий трейд":
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        await update.message.reply_text('Pair?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=PAIR_MENU)
        return PAIR
    elif text == "Переглянути останній трейд":
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
        # Потрібна функція для отримання 5 трейдів із Notion, тут спрощено
        await update.message.reply_text("Функція в розробці!", reply_markup=MAIN_MENU)
        return START
    elif text == "Повторна авторизація":
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
        await update.message.reply_text("Натисни для повторної авторизації:", reply_markup=InlineKeyboardMarkup(keyboard))
        return START
    return START

# Обробка етапу Pair
async def pair(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Pair'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Asia", callback_data='session_Asia')],
        [InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
        [InlineKeyboardButton("London", callback_data='session_London')],
        [InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
        [InlineKeyboardButton("New York", callback_data='session_New York')]
    ]
    await query.edit_message_text('Session?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return SESSION

async def pair_text(update, context):
    text = update.message.text
    if text == "Обрати Шаблон":
        await update.message.reply_text("Шаблони в розробці!", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return PAIR

# Обробка етапу Session
async def session(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Session'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("By Context", callback_data='context_By Context')],
        [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
        [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')]
    ]
    await query.edit_message_text('Context?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return CONTEXT

async def session_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        await update.message.reply_text('Pair?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=PAIR_MENU)
        return PAIR
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return SESSION

# Обробка етапу Context
async def context(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Context'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
        [InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')]
    ]
    await query.edit_message_text('Test POI?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return TEST_POI

async def context_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("Asia", callback_data='session_Asia')],
            [InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
            [InlineKeyboardButton("London", callback_data='session_London')],
            [InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
            [InlineKeyboardButton("New York", callback_data='session_New York')]
        ]
        await update.message.reply_text('Session?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return SESSION
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return CONTEXT

# Обробка етапу Test POI
async def test_poi(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Test POI'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
        [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')]
    ]
    await query.edit_message_text('Delivery to POI?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return DELIVERY

async def test_poi_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')]
        ]
        await update.message.reply_text('Context?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return CONTEXT
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return TEST_POI

# Обробка етапу Delivery to POI
async def delivery(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Delivery to POI'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid')],
        [InlineKeyboardButton("RB", callback_data='pointa_RB')],
        [InlineKeyboardButton("FVG", callback_data='pointa_FVG')],
        [InlineKeyboardButton("SNR", callback_data='pointa_SNR')]
    ]
    await query.edit_message_text('Point A?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return POINT_A

async def delivery_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50% or FullFill", callback_data='testpoi_>50% or FullFill')]
        ]
        await update.message.reply_text('Test POI?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return TEST_POI
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return DELIVERY

# Обробка етапу Point A
async def point_a(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Point A'] = query.data.split('_')[1]
        user_data[auth_key]['Trigger'] = []
    keyboard = [
        [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
        [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
        [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')]
    ]
    await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_DONE_MENU)
    return TRIGGER

async def point_a_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')]
        ]
        await update.message.reply_text('Delivery to POI?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return DELIVERY
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return POINT_A

# Обробка етапу Trigger
async def trigger(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    trigger_value = query.data.split('_')[1]
    async with user_data_lock:
        if trigger_value in user_data[auth_key]['Trigger']:
            user_data[auth_key]['Trigger'].remove(trigger_value)
        else:
            user_data[auth_key]['Trigger'].append(trigger_value)
    keyboard = [
        [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
        [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
        [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')]
    ]
    await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
    return TRIGGER

async def trigger_text(update, context):
    text = update.message.text
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid')],
            [InlineKeyboardButton("RB", callback_data='pointa_RB')],
            [InlineKeyboardButton("FVG", callback_data='pointa_FVG')],
            [InlineKeyboardButton("SNR", callback_data='pointa_SNR')]
        ]
        await update.message.reply_text('Point A?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return POINT_A
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[auth_key].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    elif text == "Готово":
        async with user_data_lock:
            if not user_data[auth_key]['Trigger']:
                await update.message.reply_text("Обери хоча б один Trigger!")
                return TRIGGER
            user_data[auth_key]['VC'] = []
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')]
        ]
        await update.message.reply_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_DONE_MENU)
        return VC
    return TRIGGER

# Обробка етапу VC
async def vc(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    vc_value = query.data.split('_')[1]
    async with user_data_lock:
        if vc_value in user_data[auth_key]['VC']:
            user_data[auth_key]['VC'].remove(vc_value)
        else:
            user_data[auth_key]['VC'].append(vc_value)
    keyboard = [
        [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
        [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
        [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')]
    ]
    await query.edit_message_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
    return VC

async def vc_text(update, context):
    text = update.message.text
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    if text == "Назад":
        async with user_data_lock:
            user_data[auth_key]['VC'] = []
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')]
        ]
        await update.message.reply_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_DONE_MENU)
        return TRIGGER
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[auth_key].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    elif text == "Готово":
        async with user_data_lock:
            if not user_data[auth_key]['VC']:
                await update.message.reply_text("Обери хоча б один VC!")
                return VC
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')]
        ]
        await update.message.reply_text('Entry Model?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return ENTRY_MODEL
    return VC

# Обробка етапу Entry Model
async def entry_model(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Entry Model'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("3m", callback_data='entrytf_3m')],
        [InlineKeyboardButton("5m", callback_data='entrytf_5m')],
        [InlineKeyboardButton("15m", callback_data='entrytf_15m')],
        [InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
        [InlineKeyboardButton("4H", callback_data='entrytf_4H')]
    ]
    await query.edit_message_text('Entry TF?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return ENTRY_TF

async def entry_model_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')]
        ]
        async with user_data_lock:
            user_id = str(update.message.from_user.id)
            auth_key = f"{user_id}user"
            await update.message.reply_text(f"VC? (Обрано: {', '.join(user_data[auth_key]['VC']) if user_data[auth_key]['VC'] else 'Нічого не обрано'})", reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_DONE_MENU)
        return VC
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return ENTRY_MODEL

# Обробка етапу Entry TF
async def entry_tf(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Entry TF'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
        [InlineKeyboardButton("FVG", callback_data='pointb_FVG')]
    ]
    await query.edit_message_text('Point B?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return POINT_B

async def entry_tf_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')]
        ]
        await update.message.reply_text('Entry Model?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return ENTRY_MODEL
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return ENTRY_TF

# Обробка етапу Point B
async def point_b(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['Point B'] = query.data.split('_')[1]
    keyboard = [
        [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
        [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
        [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')]
    ]
    await query.edit_message_text('SL Position?', reply_markup=InlineKeyboardMarkup(keyboard))
    await query.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
    return SL_POSITION

async def point_b_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("3m", callback_data='entrytf_3m')],
            [InlineKeyboardButton("5m", callback_data='entrytf_5m')],
            [InlineKeyboardButton("15m", callback_data='entrytf_15m')],
            [InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
            [InlineKeyboardButton("4H", callback_data='entrytf_4H')]
        ]
        await update.message.reply_text('Entry TF?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return ENTRY_TF
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return POINT_B

# Обробка етапу SL Position
async def sl_position(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()
    async with user_data_lock:
        user_data[auth_key]['SL Position'] = query.data.split('_')[1]
    await query.edit_message_text('Введи RR вручну (наприклад, 2.5):', reply_markup=ReplyKeyboardRemove())
    return RR

async def sl_position_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')]
        ]
        await update.message.reply_text('Point B?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return POINT_B
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return SL_POSITION

# Обробка етапу RR
async def rr(update, context):
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    text = update.message.text
    try:
        rr = float(text)
        async with user_data_lock:
            user_data[auth_key]['RR'] = rr
        summary = format_summary(user_data[auth_key])
        keyboard = [
            [InlineKeyboardButton("Відправити", callback_data='submit_trade')],
            [InlineKeyboardButton("Змінити", callback_data='edit_trade')]
        ]
        await update.message.reply_text(
            f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SUMMARY
    except ValueError:
        await update.message.reply_text("Помилка, введіть число (наприклад, 2.5):")
        return RR
    except Exception as e:
        await update.message.reply_text(f"Помилка: {str(e)}. Спробуй ще раз.")
        return RR

async def rr_text(update, context):
    text = update.message.text
    if text == "Назад":
        keyboard = [
            [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
            [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
            [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')]
        ]
        await update.message.reply_text('SL Position?', reply_markup=InlineKeyboardMarkup(keyboard))
        await update.message.reply_text('Вибір:', reply_markup=BACK_CANCEL_MENU)
        return SL_POSITION
    elif text == "Скасувати":
        async with user_data_lock:
            user_data[str(update.message.from_user.id)].clear()
        await update.message.reply_text("Скасовано.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    return RR

# Обробка підсумку
async def summary(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    await query.answer()

    if query.data == 'submit_trade':
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
            return ConversationHandler.END
        else:
            await query.edit_message_text("Помилка при відправці трейду в Notion.", reply_markup=MAIN_MENU)
            return ConversationHandler.END
    elif query.data == 'edit_trade':
        keyboard = [
            [InlineKeyboardButton("Pair", callback_data='edit_pair')],
            [InlineKeyboardButton("Session", callback_data='edit_session')],
            # Додайте інші параметри для редагування за потреби
            [InlineKeyboardButton("Повернутися", callback_data='back_to_summary')]
        ]
        await query.edit_message_text("Який параметр хочеш змінити?", reply_markup=InlineKeyboardMarkup(keyboard))
        return SUMMARY
    elif query.data == 'edit_pair':
        keyboard = [
            [InlineKeyboardButton("EURUSD", callback_data='pair_EURUSD')],
            [InlineKeyboardButton("GBPUSD", callback_data='pair_GBPUSD')],
            [InlineKeyboardButton("USDJPY", callback_data='pair_USDJPY')],
            [InlineKeyboardButton("XAUUSD", callback_data='pair_XAUUSD')],
            [InlineKeyboardButton("GER40", callback_data='pair_GER40')]
        ]
        await query.edit_message_text('Pair?', reply_markup=InlineKeyboardMarkup(keyboard))
        await query.message.reply_text('Вибір:', reply_markup=PAIR_MENU)
        return PAIR
    elif query.data == 'back_to_summary':
        summary = format_summary(user_data[auth_key])
        keyboard = [
            [InlineKeyboardButton("Відправити", callback_data='submit_trade')],
            [InlineKeyboardButton("Змінити", callback_data='edit_trade')]
        ]
        await query.edit_message_text(
            f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SUMMARY
    return SUMMARY

# Головна функція для запуску бота
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).write_timeout(30).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)],
            PAIR: [CallbackQueryHandler(pair, pattern='^pair_'), MessageHandler(filters.TEXT & ~filters.COMMAND, pair_text)],
            SESSION: [CallbackQueryHandler(session, pattern='^session_'), MessageHandler(filters.TEXT & ~filters.COMMAND, session_text)],
            CONTEXT: [CallbackQueryHandler(context, pattern='^context_'), MessageHandler(filters.TEXT & ~filters.COMMAND, context_text)],
            TEST_POI: [CallbackQueryHandler(test_poi, pattern='^testpoi_'), MessageHandler(filters.TEXT & ~filters.COMMAND, test_poi_text)],
            DELIVERY: [CallbackQueryHandler(delivery, pattern='^delivery_'), MessageHandler(filters.TEXT & ~filters.COMMAND, delivery_text)],
            POINT_A: [CallbackQueryHandler(point_a, pattern='^pointa_'), MessageHandler(filters.TEXT & ~filters.COMMAND, point_a_text)],
            TRIGGER: [CallbackQueryHandler(trigger, pattern='^trigger_'), MessageHandler(filters.TEXT & ~filters.COMMAND, trigger_text)],
            VC: [CallbackQueryHandler(vc, pattern='^vc_'), MessageHandler(filters.TEXT & ~filters.COMMAND, vc_text)],
            ENTRY_MODEL: [CallbackQueryHandler(entry_model, pattern='^entrymodel_'), MessageHandler(filters.TEXT & ~filters.COMMAND, entry_model_text)],
            ENTRY_TF: [CallbackQueryHandler(entry_tf, pattern='^entrytf_'), MessageHandler(filters.TEXT & ~filters.COMMAND, entry_tf_text)],
            POINT_B: [CallbackQueryHandler(point_b, pattern='^pointb_'), MessageHandler(filters.TEXT & ~filters.COMMAND, point_b_text)],
            SL_POSITION: [CallbackQueryHandler(sl_position, pattern='^slposition_'), MessageHandler(filters.TEXT & ~filters.COMMAND, sl_position_text)],
            RR: [MessageHandler(filters.TEXT & ~filters.COMMAND, rr)],
            SUMMARY: [CallbackQueryHandler(summary)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()