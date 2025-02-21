import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import os
import json
import heroku3

# Конфігурація через змінні середовища
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

user_data = json.loads(os.getenv('HEROKU_USER_DATA', '{}'))

# Функція для отримання батьківської сторінки бази "Classification" і пошуку "Execution"
def fetch_execution_databases(database_id, notion_token):
    # Крок 1: Отримуємо інформацію про базу "Classification"
    url = f"https://api.notion.com/v1/databases/{database_id}"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Помилка отримання бази Classification: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    print(f"Інформація про базу Classification: {data}")
    parent = data.get("parent", {})
    if parent.get("type") != "page_id":
        print("База Classification не знаходиться на сторінці.")
        return None
    
    parent_page_id = parent["page_id"]
    print(f"Знайдено батьківську сторінку з ID: {parent_page_id}")

    # Крок 2: Шукаємо сторінку "Execution" серед дочірніх елементів батьківської сторінки
    url = f"https://api.notion.com/v1/blocks/{parent_page_id}/children"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Помилка отримання дочірніх елементів сторінки: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    print(f"Дочірні елементи батьківської сторінки: {data}")
    for block in data["results"]:
        if block["type"] == "child_page" and "Execution" in block["child_page"]["title"]:
            execution_page_id = block["id"]
            print(f"Знайдено сторінку Execution з ID: {execution_page_id}")
            return fetch_databases_from_execution(execution_page_id, notion_token)
    
    print("Сторінку 'Execution' не знайдено на батьківській сторінці.")
    return None

# Функція для отримання баз із сторінки "Execution"
def fetch_databases_from_execution(page_id, notion_token):
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Дочірні блоки сторінки Execution: {data}")
        relation_ids = {
            "Context": {}, "Test POI": {}, "Point A": {}, "Trigger": {}, "VC": {},
            "Entry model": {}, "Entry TF": {}, "Point B": {}, "SL Position": {}
        }
        for block in data["results"]:
            if block["type"] == "child_database":
                db_title = block["child_database"]["title"]
                db_id = block["id"]
                print(f"Знайдено базу: {db_title} з ID {db_id}")
                if "Context" in db_title:
                    relation_ids["Context"] = fetch_relation_ids(db_id, notion_token)
                elif "Test POI" in db_title:
                    relation_ids["Test POI"] = fetch_relation_ids(db_id, notion_token)
                elif "Point A" in db_title:
                    relation_ids["Point A"] = fetch_relation_ids(db_id, notion_token)
                elif "Trigger" in db_title:
                    relation_ids["Trigger"] = fetch_relation_ids(db_id, notion_token)
                elif "VC" in db_title:
                    relation_ids["VC"] = fetch_relation_ids(db_id, notion_token)
                elif "Entry Models" in db_title:  # Змінено на "Entry Models" відповідно до вашої структури
                    relation_ids["Entry model"] = fetch_relation_ids(db_id, notion_token)
                elif "Entry TF" in db_title:
                    relation_ids["Entry TF"] = fetch_relation_ids(db_id, notion_token)
                elif "Point B" in db_title:
                    relation_ids["Point B"] = fetch_relation_ids(db_id, notion_token)
                elif "Stop Loss position" in db_title:  # Змінено на "Stop Loss position"
                    relation_ids["SL Position"] = fetch_relation_ids(db_id, notion_token)
        return relation_ids
    else:
        print(f"Помилка отримання баз із Execution: {response.status_code} - {response.text}")
        return None

# Функція для отримання ID записів із бази
def fetch_relation_ids(database_id, notion_token):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print(f"Записи бази {database_id}: {data}")
        relation_ids = {}
        for result in data["results"]:
            name_prop = result["properties"].get("Name", {})
            if name_prop.get("title"):
                name = name_prop["title"][0]["text"]["content"]
                page_id = result["id"]
                relation_ids[name] = page_id
                print(f"Додано запис: {name} -> {page_id}")
        return relation_ids
    else:
        print(f"Помилка отримання записів із бази {database_id}: {response.status_code} - {response.text}")
        return None

# Початок роботи бота
async def start(update, context):
    global user_data
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    print(f"Перевірка user_data перед /start: {user_data}")
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        instructions = (
            "Щоб використовувати бота:\n"
            "1. Скопіюй сторінку за посиланням: https://www.notion.so/A-B-C-position-Final-Bot-1a084b079a8280d29d5ecc9316e02c5d\n"
            "2. Авторизуйся нижче і введи ID бази 'Classification'."
        )
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        print(f"Сформований auth_url: {auth_url}")
        keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(instructions, reply_markup=reply_markup)
    elif 'database_id' not in user_data[auth_key]:
        await update.message.reply_text('Введи ID бази "Classification" (32 символи з URL):')
    elif 'relation_ids' not in user_data[auth_key]:
        relation_ids = fetch_execution_databases(user_data[auth_key]['database_id'], user_data[auth_key]['notion_token'])
        if relation_ids:
            user_data[auth_key]['relation_ids'] = relation_ids
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)
        else:
            await update.message.reply_text('Помилка: не вдалося знайти сторінку "Execution" поруч із базою "Classification". Перевір правильність ID або структуру сторінки.')
    else:
        keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)

# Решта коду (handle_text, create_notion_page, button, main) залишається без змін
# ... (вставте решту вашого коду сюди)

# Обробка текстового вводу
async def handle_text(update, context):
    global user_data
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        await update.message.reply_text("Спочатку авторизуйся через /start.")
    elif 'database_id' not in user_data[auth_key]:
        text = update.message.text
        if len(text) == 32:
            user_data[auth_key]['database_id'] = text
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            await update.message.reply_text('ID бази збережено! Напиши /start.')
        else:
            await update.message.reply_text('Неправильний ID. Введи 32 символи з URL бази "Classification".')
    elif 'waiting_for_rr' in user_data[auth_key]:
        rr_input = update.message.text
        try:
            rr = float(rr_input)
            user_data[auth_key]['RR'] = rr
            required_keys = ['Pair', 'Session', 'Context', 'Test POI', 'Delivery to POI', 'Point A', 
                            'Trigger', 'VC', 'Entry model', 'Entry TF', 'Point B', 'SL Position', 'RR']
            missing_keys = [key for key in required_keys if key not in user_data[auth_key]]
            if missing_keys:
                await update.message.reply_text(f"Помилка: відсутні дані для {', '.join(missing_keys)}. Почни заново через 'Додати трейд'.")
            else:
                create_notion_page(auth_key)
                await update.message.reply_text(format_summary(user_data[auth_key]))
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                print(f"Збережено user_data в HEROKU_USER_DATA: {user_data}")
                del user_data[auth_key]['waiting_for_rr']
                del user_data[auth_key]['Pair']
                del user_data[auth_key]['Session']
                del user_data[auth_key]['Context']
                del user_data[auth_key]['Test POI']
                del user_data[auth_key]['Delivery to POI']
                del user_data[auth_key]['Point A']
                del user_data[auth_key]['Trigger']
                del user_data[auth_key]['VC']
                del user_data[auth_key]['Entry model']
                del user_data[auth_key]['Entry TF']
                del user_data[auth_key]['Point B']
                del user_data[auth_key]['SL Position']
                del user_data[auth_key]['RR']
        except ValueError:
            await update.message.reply_text("Введи коректне число для RR (наприклад, 2.5):")
    else:
        await update.message.reply_text("Спочатку почни додавання трейду через /start.")

# Форматування підсумку
def format_summary(data):
    return (
        f"Трейд додано!\n"
        f"Pair: {data['Pair']}\n"
        f"Session: {data['Session']}\n"
        f"Context: {data['Context']}\n"
        f"Test POI: {data['Test POI']}\n"
        f"Delivery to POI: {data['Delivery to POI']}\n"
        f"Point A: {data['Point A']}\n"
        f"Trigger: {data['Trigger']}\n"
        f"VC: {data['VC']}\n"
        f"Entry model: {data['Entry model']}\n"
        f"Entry TF: {data['Entry TF']}\n"
        f"Point B: {data['Point B']}\n"
        f"SL Position: {data['SL Position']}\n"
        f"RR: {data['RR']}"
    )

# Створення сторінки в Notion
def create_notion_page(user_id):
    url = 'https://api.notion.com/v1/pages'
    headers = {
        'Authorization': f'Bearer {user_data[user_id]["notion_token"]}',
        'Content-Type': 'application/json',
        'Notion-Version': "2022-06-28"
    }
    relation_ids = user_data[user_id]['relation_ids']
    payload = {
        'parent': {'database_id': user_data[user_id]['database_id']},
        'properties': {
            'Pair': {'select': {'name': user_data[user_id]['Pair']}},
            'Session': {'select': {'name': user_data[user_id]['Session']}},
            'Context': {'relation': [{'id': relation_ids['Context'][user_data[user_id]['Context']]}]},
            'Test POI': {'relation': [{'id': relation_ids['Test POI'][user_data[user_id]['Test POI']]}]},
            'Delivery to POI': {'select': {'name': user_data[user_id]['Delivery to POI']}},
            'Point A': {'relation': [{'id': relation_ids['Point A'][user_data[user_id]['Point A']]}]},
            'Trigger': {'relation': [{'id': relation_ids['Trigger'][user_data[user_id]['Trigger']]}]},
            'VC': {'relation': [{'id': relation_ids['VC'][user_data[user_id]['VC']]}]},
            'Entry Model': {'relation': [{'id': relation_ids['Entry model'][user_data[user_id]['Entry model']]}]},
            'Entry TF': {'relation': [{'id': relation_ids['Entry TF'][user_data[user_id]['Entry TF']]}]},
            'Point B': {'relation': [{'id': relation_ids['Point B'][user_data[user_id]['Point B']]}]},
            'SL Position': {'relation': [{'id': relation_ids['SL Position'][user_data[user_id]['SL Position']]}]},
            'RR': {'number': user_data[user_id]['RR']}
        }
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"Помилка Notion API для користувача {user_id}: {response.text}")

# Обробка кнопок
async def button(update, context):
    global user_data
    user_id = str(update.message.from_user.id) if update.message else str(update.callback_query.from_user.id)
    auth_key = f"{user_id}user"
    
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        await update.callback_query.edit_message_text("Спочатку авторизуйся через /start.")
        return
    if 'database_id' not in user_data[auth_key]:
        await update.callback_query.edit_message_text("Спочатку введи ID бази через /start.")
        return
    
    query = update.callback_query
    await query.answer()

    # Перевіряємо, чи бот чекає на введення RR
    if user_data[auth_key].get('waiting_for_rr'):
        await query.edit_message_text('Введи RR вручну (наприклад, 2.5):')
        return  # Ігноруємо будь-які callback-запити, чекаємо текст у handle_text
    
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
        user_data[auth_key]['Pair'] = query.data.split('_')[1]
        print(f"Оновлено Pair: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("Asia", callback_data='session_Asia')],
            [InlineKeyboardButton("Frankfurt", callback_data='session_Frankfurt')],
            [InlineKeyboardButton("London", callback_data='session_London')],
            [InlineKeyboardButton("Out of OTT", callback_data='session_Out of OTT')],
            [InlineKeyboardButton("New York", callback_data='session_New York')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Session?', reply_markup=reply_markup)
    
    elif query.data.startswith('session_'):
        user_data[auth_key]['Session'] = query.data.split('_')[1]
        print(f"Оновлено Session: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Context?', reply_markup=reply_markup)
    
    elif query.data.startswith('context_'):
        user_data[auth_key]['Context'] = query.data.split('_')[1]
        print(f"Оновлено Context: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50@ or FullFill", callback_data='testpoi_>50@ or FullFill')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('testpoi_'):
        user_data[auth_key]['Test POI'] = query.data.split('_')[1]
        print(f"Оновлено Test POI: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Delivery to POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('delivery_'):
        user_data[auth_key]['Delivery to POI'] = query.data.split('_')[1]
        print(f"Оновлено Delivery to POI: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("Fractal Raid", callback_data='pointa_Fractal Raid')],
            [InlineKeyboardButton("RB", callback_data='pointa_RB')],
            [InlineKeyboardButton("FVG", callback_data='pointa_FVG')],
            [InlineKeyboardButton("SNR", callback_data='pointa_SNR')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point A?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointa_'):
        user_data[auth_key]['Point A'] = query.data.split('_')[1]
        print(f"Оновлено Point A: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Trigger?', reply_markup=reply_markup)
    
    elif query.data.startswith('trigger_'):
        user_data[auth_key]['Trigger'] = query.data.split('_')[1]
        print(f"Оновлено Trigger: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('VC?', reply_markup=reply_markup)
    
    elif query.data.startswith('vc_'):
        user_data[auth_key]['VC'] = query.data.split('_')[1]
        print(f"Оновлено VC: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry model?', reply_markup=reply_markup)
    
    elif query.data.startswith('entrymodel_'):
        user_data[auth_key]['Entry model'] = query.data.split('_')[1]
        print(f"Оновлено Entry model: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("3m", callback_data='entrytf_3m')],
            [InlineKeyboardButton("5m", callback_data='entrytf_5m')],
            [InlineKeyboardButton("15m", callback_data='entrytf_15m')],
            [InlineKeyboardButton("1H/30m", callback_data='entrytf_1H/30m')],
            [InlineKeyboardButton("4H", callback_data='entrytf_4H')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry TF?', reply_markup=reply_markup)
    
    elif query.data.startswith('entrytf_'):
        user_data[auth_key]['Entry TF'] = query.data.split('_')[1]
        print(f"Оновлено Entry TF: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point B?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointb_'):
        user_data[auth_key]['Point B'] = query.data.split('_')[1]
        print(f"Оновлено Point B: {user_data[auth_key]}")
        keyboard = [
            [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
            [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
            [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('SL Position?', reply_markup=reply_markup)
    
    elif query.data.startswith('slposition_'):
        user_data[auth_key]['SL Position'] = query.data.split('_')[1]
        user_data[auth_key]['waiting_for_rr'] = True
        print(f"Оновлено SL Position і waiting_for_rr: {user_data[auth_key]}")
        await query.edit_message_text('Введи RR вручну (наприклад, 2.5):')

# Головна функція для запуску бота
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).read_timeout(30).write_timeout(30).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.run_polling()

if __name__ == '__main__':
    main()