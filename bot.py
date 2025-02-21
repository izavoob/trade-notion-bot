import requests
import json
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import heroku3

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
logger.info(f"Initial user_data loaded from HEROKU_USER_DATA: {json.dumps(user_data, indent=2)}")

# Функція для отримання баз із батьківської сторінки
def fetch_databases_from_parent_page(page_id, notion_token):
    logger.debug(f"Starting fetch_databases_from_parent_page with page_id: {page_id}")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    logger.debug(f"Notion API GET request to: {url} with headers: {headers}")
    response = requests.get(url, headers=headers)
    logger.debug(f"Notion API response: status={response.status_code}, content={response.text}")
    
    if response.status_code != 200:
        logger.error(f"Failed to fetch children of page {page_id}: {response.status_code} - {response.text}")
        return None, None
    
    data = response.json()
    logger.info(f"Children of parent page {page_id}: {json.dumps(data, indent=2)}")
    
    classification_db_id = None
    execution_page_id = None
    
    for block in data.get("results", []):
        logger.debug(f"Processing block: {json.dumps(block, indent=2)}")
        if block["type"] == "child_database" and "Classification" in block["child_database"]["title"]:
            classification_db_id = block["id"]
            logger.info(f"Found Classification database with ID: {classification_db_id}")
        elif block["type"] == "child_page" and "Execution" in block["child_page"]["title"]:
            execution_page_id = block["id"]
            logger.info(f"Found Execution page with ID: {execution_page_id}")
    
    if not classification_db_id:
        logger.error("Classification database not found on parent page.")
        return None, None
    if not execution_page_id:
        logger.error("Execution page not found on parent page.")
        return None, None
    
    relation_ids = fetch_databases_from_execution(execution_page_id, notion_token)
    logger.info(f"Returning classification_db_id: {classification_db_id}, relation_ids: {json.dumps(relation_ids, indent=2)}")
    return classification_db_id, relation_ids

def fetch_databases_from_execution(page_id, notion_token):
    logger.debug(f"Starting fetch_databases_from_execution with page_id: {page_id}")
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    logger.debug(f"Notion API GET request to: {url} with headers: {headers}")
    response = requests.get(url, headers=headers)
    logger.debug(f"Notion API response: status={response.status_code}, content={response.text}")
    
    if response.status_code != 200:
        logger.error(f"Failed to fetch children of Execution page {page_id}: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    logger.info(f"Children of Execution page {page_id}: {json.dumps(data, indent=2)}")
    relation_ids = {
        "Context": {}, "Test POI": {}, "Point A": {}, "Trigger": {}, "VC": {},
        "Entry model": {}, "Entry TF": {}, "Point B": {}, "SL Position": {}
    }
    
    for block in data.get("results", []):
        logger.debug(f"Processing block: {json.dumps(block, indent=2)}")
        if block["type"] == "child_database":
            db_title = block["child_database"]["title"]
            db_id = block["id"]
            logger.info(f"Found database: {db_title} with ID: {db_id}")
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
            elif "Entry Models" in db_title:
                relation_ids["Entry model"] = fetch_relation_ids(db_id, notion_token)
            elif "Entry TF" in db_title:
                relation_ids["Entry TF"] = fetch_relation_ids(db_id, notion_token)
            elif "Point B" in db_title:
                relation_ids["Point B"] = fetch_relation_ids(db_id, notion_token)
            elif "Stop Loss position" in db_title:
                relation_ids["SL Position"] = fetch_relation_ids(db_id, notion_token)
    
    logger.info(f"Collected relation_ids from Execution: {json.dumps(relation_ids, indent=2)}")
    return relation_ids

def fetch_relation_ids(database_id, notion_token):
    logger.debug(f"Starting fetch_relation_ids with database_id: {database_id}")
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {notion_token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    logger.debug(f"Notion API POST request to: {url} with headers: {headers}")
    response = requests.post(url, headers=headers)
    logger.debug(f"Notion API response: status={response.status_code}, content={response.text}")
    
    if response.status_code != 200:
        logger.error(f"Failed to query database {database_id}: {response.status_code} - {response.text}")
        return {}
    
    data = response.json()
    logger.info(f"Records from database {database_id}: {json.dumps(data, indent=2)}")
    relation_ids = {}
    
    for result in data.get("results", []):
        logger.debug(f"Processing record: {json.dumps(result, indent=2)}")
        name_prop = result["properties"].get("Name", {})
        if name_prop.get("title") and name_prop["title"]:
            name = name_prop["title"][0]["text"]["content"]
            page_id = result["id"]
            relation_ids[name] = page_id
            logger.info(f"Added relation: {name} -> {page_id}")
        else:
            logger.warning(f"Record in database {database_id} has no 'Name' property or it's empty: {json.dumps(result, indent=2)}")
    
    return relation_ids

# Початок роботи бота
async def start(update, context):
    global user_data
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Start command received from user {user_id}. Current user_data: {json.dumps(user_data, indent=2)}")
    
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        instructions = (
            "Щоб використовувати бота:\n"
            "1. Скопіюй сторінку за посиланням: https://www.notion.so/A-B-C-position-Final-Bot-1a084b079a8280d29d5ecc9316e02c5d\n"
            "2. Авторизуйся нижче і введи ID батьківської сторінки 'A-B-C position Final Bot' (32 символи з URL)."
        )
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        logger.info(f"Generated Notion auth URL for user {user_id}: {auth_url}")
        keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(instructions, reply_markup=reply_markup)
    elif 'parent_page_id' not in user_data[auth_key]:
        await update.message.reply_text('Введи ID батьківської сторінки "A-B-C position Final Bot" (32 символи з URL):')
        logger.info(f"Prompted user {user_id} to enter parent page ID.")
    elif 'classification_db_id' not in user_data[auth_key] or 'relation_ids' not in user_data[auth_key]:
        logger.info(f"Fetching Classification and relation IDs for user {user_id} with parent_page_id: {user_data[auth_key]['parent_page_id']}")
        classification_db_id, relation_ids = fetch_databases_from_parent_page(user_data[auth_key]['parent_page_id'], user_data[auth_key]['notion_token'])
        if classification_db_id and relation_ids:
            user_data[auth_key]['classification_db_id'] = classification_db_id
            user_data[auth_key]['relation_ids'] = relation_ids
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            logger.info(f"Saved classification_db_id: {classification_db_id} and relation_ids to user_data for {auth_key}: {json.dumps(user_data[auth_key], indent=2)}")
            keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)
        else:
            logger.error(f"Failed to fetch Classification or relation IDs for user {user_id}")
            await update.message.reply_text('Помилка: не вдалося знайти базу "Classification" або сторінку "Execution". Перевір правильність ID сторінки.')
    else:
        keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)
        logger.info(f"User {user_id} ready to add trade. Current user_data: {json.dumps(user_data[auth_key], indent=2)}")

# Обробка текстового вводу
async def handle_text(update, context):
    global user_data
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Text input received from user {user_id}: {update.message.text}")
    
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        await update.message.reply_text("Спочатку авторизуйся через /start.")
        logger.warning(f"User {user_id} not authenticated.")
    elif 'parent_page_id' not in user_data[auth_key]:
        text = update.message.text
        if len(text) == 32:
            user_data[auth_key]['parent_page_id'] = text
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            logger.info(f"Saved parent_page_id: {text} for user {user_id}. Updated user_data: {json.dumps(user_data[auth_key], indent=2)}")
            await update.message.reply_text('ID сторінки збережено! Напиши /start.')
        else:
            logger.warning(f"Invalid parent_page_id length from user {user_id}: {text}")
            await update.message.reply_text('Неправильний ID. Введи 32 символи з URL сторінки "A-B-C position Final Bot".')
    elif 'waiting_for_rr' in user_data[auth_key]:
        rr_input = update.message.text
        logger.info(f"Received RR input from user {user_id}: {rr_input}")
        try:
            rr = float(rr_input)
            user_data[auth_key]['RR'] = rr
            required_keys = ['Pair', 'Session', 'Context', 'Test POI', 'Delivery to POI', 'Point A', 
                            'Trigger', 'VC', 'Entry model', 'Entry TF', 'Point B', 'SL Position', 'RR']
            missing_keys = [key for key in required_keys if key not in user_data[auth_key]]
            if missing_keys:
                logger.error(f"Missing required keys for user {user_id}: {missing_keys}")
                await update.message.reply_text(f"Помилка: відсутні дані для {', '.join(missing_keys)}. Почни заново через 'Додати трейд'.")
            else:
                logger.info(f"Attempting to create Notion page for user {user_id} with data: {json.dumps(user_data[auth_key], indent=2)}")
                success = create_notion_page(auth_key)
                if success:
                    await update.message.reply_text(format_summary(user_data[auth_key]) + "\nТрейд успішно додано!")
                    conn = heroku3.from_key(HEROKU_API_KEY)
                    heroku_app = conn.apps()['tradenotionbot-lg2']
                    heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                    logger.info(f"Trade added successfully for user {user_id}. Updated user_data: {json.dumps(user_data, indent=2)}")
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
                else:
                    await update.message.reply_text("Помилка: не вдалося додати трейд у Notion. Перевір логи.")
        except ValueError:
            logger.warning(f"Invalid RR input from user {user_id}: {rr_input}")
            await update.message.reply_text("Введи коректне число для RR (наприклад, 2.5):")
        except Exception as e:
            logger.error(f"Error adding trade for user {user_id}: {str(e)}", exc_info=True)
            await update.message.reply_text(f"Помилка при додаванні трейду: {str(e)}. Спробуй ще раз.")
    else:
        await update.message.reply_text("Спочатку почни додавання трейду через /start.")
        logger.info(f"User {user_id} sent text outside of trade flow: {update.message.text}")

# Форматування підсумку
def format_summary(data):
    summary = (
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
    logger.info(f"Generated trade summary: {summary}")
    return summary

# Створення сторінки в Notion
def create_notion_page(user_id):
    logger.debug(f"Starting create_notion_page for user {user_id}")
    url = 'https://api.notion.com/v1/pages'
    headers = {
        'Authorization': f'Bearer {user_data[user_id]["notion_token"]}',
        'Content-Type': 'application/json',
        'Notion-Version': "2022-06-28"
    }
    relation_ids = user_data[user_id]['relation_ids']
    logger.info(f"relation_ids for user {user_id}: {json.dumps(relation_ids, indent=2)}")
    
    payload = {
        'parent': {'database_id': user_data[user_id]['classification_db_id']},
        'properties': {
            'Pair': {'select': {'name': user_data[user_id]['Pair']}},
            'Session': {'select': {'name': user_data[user_id]['Session']}},
            'Delivery to POI': {'select': {'name': user_data[user_id]['Delivery to POI']}},
            'RR': {'number': user_data[user_id]['RR']}
        }
    }
    
    # Додаємо поля типу relation лише якщо є відповідний ID
    for prop in ['Context', 'Test POI', 'Point A', 'Trigger', 'VC', 'Entry model', 'Entry TF', 'Point B', 'SL Position']:
        value = user_data[user_id].get(prop)
        if value and prop in relation_ids and relation_ids[prop].get(value):
            payload['properties'][prop] = {'relation': [{'id': relation_ids[prop][value]}]}
            logger.debug(f"Added relation for {prop}: {value} -> {relation_ids[prop][value]}")
        else:
            logger.debug(f"Skipping relation for {prop}: no valid ID found for value {value}")

    logger.debug(f"Notion API payload: {json.dumps(payload, indent=2)}")
    
    missing_relations = [key for key in relation_ids if not relation_ids[key]]
    if missing_relations:
        logger.warning(f"Missing relation records for keys: {missing_relations} in relation_ids: {json.dumps(relation_ids, indent=2)}")
    
    logger.debug(f"Sending POST request to Notion API: {url} with headers: {headers}")
    response = requests.post(url, json=payload, headers=headers)
    logger.debug(f"Notion API response: status={response.status_code}, content={response.text}")
    
    if response.status_code == 200:
        logger.info(f"Successfully created page for user {user_id}: {json.dumps(response.json(), indent=2)}")
        return True
    else:
        logger.error(f"Notion API error for user {user_id}: {response.status_code} - {response.text}")
        return False

# Обробка кнопок
async def button(update, context):
    global user_data
    query = update.callback_query
    user_id = str(query.from_user.id)
    auth_key = f"{user_id}user"
    logger.info(f"Button callback received from user {user_id}: {query.data}")
    
    await query.answer()
    
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        await query.edit_message_text("Спочатку авторизуйся через /start.")
        logger.warning(f"User {user_id} not authenticated for button callback.")
        return
    if 'parent_page_id' not in user_data[auth_key]:
        await query.edit_message_text("Спочатку введи ID сторінки через /start.")
        logger.warning(f"User {user_id} has not provided parent_page_id.")
        return
    
    if user_data[auth_key].get('waiting_for_rr'):
        await context.bot.send_message(chat_id=query.message.chat_id, text='Введи RR вручну (наприклад, 2.5):')
        logger.info(f"User {user_id} in waiting_for_rr state, prompted for RR input.")
        return
    
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
        logger.info(f"User {user_id} started trade flow with Pair selection.")
    
    elif query.data.startswith('pair_'):
        user_data[auth_key]['Pair'] = query.data.split('_')[1]
        logger.info(f"Updated Pair for user {user_id}: {user_data[auth_key]['Pair']}")
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
        logger.info(f"Updated Session for user {user_id}: {user_data[auth_key]['Session']}")
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Context?', reply_markup=reply_markup)
    
    elif query.data.startswith('context_'):
        user_data[auth_key]['Context'] = query.data.split('_')[1]
        logger.info(f"Updated Context for user {user_id}: {user_data[auth_key]['Context']}")
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50@ or FullFill", callback_data='testpoi_>50@ or FullFill')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('testpoi_'):
        user_data[auth_key]['Test POI'] = query.data.split('_')[1]
        logger.info(f"Updated Test POI for user {user_id}: {user_data[auth_key]['Test POI']}")
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Delivery to POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('delivery_'):
        user_data[auth_key]['Delivery to POI'] = query.data.split('_')[1]
        logger.info(f"Updated Delivery to POI for user {user_id}: {user_data[auth_key]['Delivery to POI']}")
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
        logger.info(f"Updated Point A for user {user_id}: {user_data[auth_key]['Point A']}")
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Trigger?', reply_markup=reply_markup)
    
    elif query.data.startswith('trigger_'):
        user_data[auth_key]['Trigger'] = query.data.split('_')[1]
        logger.info(f"Updated Trigger for user {user_id}: {user_data[auth_key]['Trigger']}")
        keyboard = [
            [InlineKeyboardButton("SNR", callback_data='vc_SNR')],
            [InlineKeyboardButton("FVG", callback_data='vc_FVG')],
            [InlineKeyboardButton("Inversion", callback_data='vc_Inversion')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('VC?', reply_markup=reply_markup)
    
    elif query.data.startswith('vc_'):
        user_data[auth_key]['VC'] = query.data.split('_')[1]
        logger.info(f"Updated VC for user {user_id}: {user_data[auth_key]['VC']}")
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
        logger.info(f"Updated Entry model for user {user_id}: {user_data[auth_key]['Entry model']}")
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
        logger.info(f"Updated Entry TF for user {user_id}: {user_data[auth_key]['Entry TF']}")
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point B?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointb_'):
        user_data[auth_key]['Point B'] = query.data.split('_')[1]
        logger.info(f"Updated Point B for user {user_id}: {user_data[auth_key]['Point B']}")
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
        logger.info(f"Updated SL Position and set waiting_for_rr for user {user_id}: {json.dumps(user_data[auth_key], indent=2)}")
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
    logger.info("Bot polling stopped.")

if __name__ == '__main__':
    main()