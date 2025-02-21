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

# Функція для отримання ID бази "Classification" із батьківської сторінки
def fetch_classification_db_id(page_id, notion_token):
    logger.debug(f"Starting fetch_classification_db_id with page_id: {page_id}")
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
        return None
    
    data = response.json()
    logger.info(f"Children of parent page {page_id}: {json.dumps(data, indent=2)}")
    
    classification_db_id = None
    
    for block in data.get("results", []):
        logger.debug(f"Processing block: {json.dumps(block, indent=2)}")
        if block["type"] == "child_database" and "Classification" in block["child_database"]["title"]:
            classification_db_id = block["id"]
            logger.info(f"Found Classification database with ID: {classification_db_id}")
            break
    
    if not classification_db_id:
        logger.error("Classification database not found on parent page.")
        return None
    
    logger.info(f"Returning classification_db_id: {classification_db_id}")
    return classification_db_id

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
    elif 'classification_db_id' not in user_data[auth_key]:
        logger.info(f"Fetching Classification DB ID for user {user_id} with parent_page_id: {user_data[auth_key]['parent_page_id']}")
        classification_db_id = fetch_classification_db_id(user_data[auth_key]['parent_page_id'], user_data[auth_key]['notion_token'])
        if classification_db_id:
            user_data[auth_key]['classification_db_id'] = classification_db_id
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            logger.info(f"Saved classification_db_id: {classification_db_id} to user_data for {auth_key}: {json.dumps(user_data[auth_key], indent=2)}")
            keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)
        else:
            logger.error(f"Failed to fetch Classification DB ID for user {user_id}")
            await update.message.reply_text('Помилка: не вдалося знайти базу "Classification". Перевір правильність ID сторінки.')
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
                            'Trigger', 'VC', 'Entry Model', 'Entry TF', 'Point B', 'SL Position', 'RR']
            missing_keys = [key for key in required_keys if key not in user_data[auth_key]]
            if missing_keys:
                logger.error(f"Missing required keys for user {user_id}: {missing_keys}")
                await update.message.reply_text(f"Помилка: відсутні дані для {', '.join(missing_keys)}. Почни заново через 'Додати трейд'.")
            else:
                summary = format_summary(user_data[auth_key])
                keyboard = [
                    [InlineKeyboardButton("Відправити", callback_data='submit_trade')],
                    [InlineKeyboardButton("Змінити", callback_data='edit_trade')]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(f"{summary}\n\nПеревір дані. Якщо все правильно, натисни 'Відправити'. Якщо щось не так, натисни 'Змінити'.", reply_markup=reply_markup)
                logger.info(f"Displayed summary for user {user_id} to confirm or edit.")
        except ValueError:
            logger.warning(f"Invalid RR input from user {user_id}: {rr_input}")
            await update.message.reply_text("Введи коректне число для RR (наприклад, 2.5):")
        except Exception as e:
            logger.error(f"Error processing RR for user {user_id}: {str(e)}", exc_info=True)
            await update.message.reply_text(f"Помилка при обробці RR: {str(e)}. Спробуй ще раз.")
    else:
        await update.message.reply_text("Спочатку почни додавання трейду через /start.")
        logger.info(f"User {user_id} sent text outside of trade flow: {update.message.text}")

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
    
    # Ініціалізація списків для мультивибору, якщо їх ще немає
    if 'Trigger' not in user_data[auth_key] or not isinstance(user_data[auth_key]['Trigger'], list):
        user_data[auth_key]['Trigger'] = []
    if 'VC' not in user_data[auth_key] or not isinstance(user_data[auth_key]['VC'], list):
        user_data[auth_key]['VC'] = []

    # Логіка повернення назад і мультивибору
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
            [InlineKeyboardButton("New York", callback_data='session_New York')],
            [InlineKeyboardButton("Назад", callback_data='back_to_start')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Session?', reply_markup=reply_markup)
    
    elif query.data.startswith('session_'):
        user_data[auth_key]['Session'] = query.data.split('_')[1]
        logger.info(f"Updated Session for user {user_id}: {user_data[auth_key]['Session']}")
        keyboard = [
            [InlineKeyboardButton("By Context", callback_data='context_By Context')],
            [InlineKeyboardButton("Against Context", callback_data='context_Against Context')],
            [InlineKeyboardButton("Neutral Context", callback_data='context_Neutral Context')],
            [InlineKeyboardButton("Назад", callback_data='back_to_pair')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Context?', reply_markup=reply_markup)
    
    elif query.data.startswith('context_'):
        user_data[auth_key]['Context'] = query.data.split('_')[1]
        logger.info(f"Updated Context for user {user_id}: {user_data[auth_key]['Context']}")
        keyboard = [
            [InlineKeyboardButton("Minimal", callback_data='testpoi_Minimal')],
            [InlineKeyboardButton(">50@ or FullFill", callback_data='testpoi_>50@ or FullFill')],
            [InlineKeyboardButton("Назад", callback_data='back_to_session')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    
    elif query.data.startswith('testpoi_'):
        user_data[auth_key]['Test POI'] = query.data.split('_')[1]
        logger.info(f"Updated Test POI for user {user_id}: {user_data[auth_key]['Test POI']}")
        keyboard = [
            [InlineKeyboardButton("Non-agressive", callback_data='delivery_Non-agressive')],
            [InlineKeyboardButton("Agressive", callback_data='delivery_Agressive')],
            [InlineKeyboardButton("Назад", callback_data='back_to_context')]
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
            [InlineKeyboardButton("SNR", callback_data='pointa_SNR')],
            [InlineKeyboardButton("Назад", callback_data='back_to_testpoi')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point A?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointa_'):
        user_data[auth_key]['Point A'] = query.data.split('_')[1]
        logger.info(f"Updated Point A for user {user_id}: {user_data[auth_key]['Point A']}")
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
        if trigger_value in user_data[auth_key]['Trigger']:
            user_data[auth_key]['Trigger'].remove(trigger_value)
            logger.info(f"Removed Trigger for user {user_id}: {trigger_value}. Current Trigger: {user_data[auth_key]['Trigger']}")
        else:
            user_data[auth_key]['Trigger'].append(trigger_value)
            logger.info(f"Added Trigger for user {user_id}: {trigger_value}. Current Trigger: {user_data[auth_key]['Trigger']}")
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
        if not user_data[auth_key]['Trigger']:
            await query.edit_message_text("Обери хоча б один Trigger!")
            return
        logger.info(f"Trigger selection completed for user {user_id}: {user_data[auth_key]['Trigger']}")
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
        if vc_value in user_data[auth_key]['VC']:
            user_data[auth_key]['VC'].remove(vc_value)
            logger.info(f"Removed VC for user {user_id}: {vc_value}. Current VC: {user_data[auth_key]['VC']}")
        else:
            user_data[auth_key]['VC'].append(vc_value)
            logger.info(f"Added VC for user {user_id}: {vc_value}. Current VC: {user_data[auth_key]['VC']}")
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
        if not user_data[auth_key]['VC']:
            await query.edit_message_text("Обери хоча б один VC!")
            return
        logger.info(f"VC selection completed for user {user_id}: {user_data[auth_key]['VC']}")
        keyboard = [
            [InlineKeyboardButton("IDM", callback_data='entrymodel_IDM')],
            [InlineKeyboardButton("Inversion", callback_data='entrymodel_Inversion')],
            [InlineKeyboardButton("SNR", callback_data='entrymodel_SNR')],
            [InlineKeyboardButton("Displacement", callback_data='entrymodel_Displacement')],
            [InlineKeyboardButton("Назад", callback_data='back_to_trigger')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Entry Model?', reply_markup=reply_markup)
    
    elif query.data.startswith('entrymodel_'):
        user_data[auth_key]['Entry Model'] = query.data.split('_')[1]
        logger.info(f"Updated Entry Model for user {user_id}: {user_data[auth_key]['Entry Model']}")
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
        user_data[auth_key]['Entry TF'] = query.data.split('_')[1]
        logger.info(f"Updated Entry TF for user {user_id}: {user_data[auth_key]['Entry TF']}")
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='pointb_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='pointb_FVG')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entrymodel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Point B?', reply_markup=reply_markup)
    
    elif query.data.startswith('pointb_'):
        user_data[auth_key]['Point B'] = query.data.split('_')[1]
        logger.info(f"Updated Point B for user {user_id}: {user_data[auth_key]['Point B']}")
        keyboard = [
            [InlineKeyboardButton("LTF/Lunch Manipulation", callback_data='slposition_LTF/Lunch Manipulation')],
            [InlineKeyboardButton("1H/30m Raid", callback_data='slposition_1H/30m Raid')],
            [InlineKeyboardButton("4H Raid", callback_data='slposition_4H Raid')],
            [InlineKeyboardButton("Назад", callback_data='back_to_entrytf')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('SL Position?', reply_markup=reply_markup)
    
    elif query.data.startswith('slposition_'):
        user_data[auth_key]['SL Position'] = query.data.split('_')[1]
        user_data[auth_key]['waiting_for_rr'] = True
        logger.info(f"Updated SL Position and set waiting_for_rr for user {user_id}: {json.dumps(user_data[auth_key], indent=2)}")
        await context.bot.send_message(chat_id=query.message.chat_id, text='Введи RR вручну (наприклад, 2.5):', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data='back_to_pointb')]]))

    # Логіка повернення назад
    elif query.data == 'back_to_start':
        keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)
    
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
            [InlineKeyboardButton(">50@ or FullFill", callback_data='testpoi_>50@ or FullFill')],
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

    # Логіка підтвердження або редагування
    elif query.data == 'submit_trade':
        success = create_notion_page(auth_key)
        if success:
            await query.edit_message_text("Трейд успішно додано до Notion!")
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            logger.info(f"Trade submitted successfully for user {user_id}. Updated user_data: {json.dumps(user_data, indent=2)}")
            del user_data[auth_key]['waiting_for_rr']
            del user_data[auth_key]['Pair']
            del user_data[auth_key]['Session']
            del user_data[auth_key]['Context']
            del user_data[auth_key]['Test POI']
            del user_data[auth_key]['Delivery to POI']
            del user_data[auth_key]['Point A']
            del user_data[auth_key]['Trigger']
            del user_data[auth_key]['VC']
            del user_data[auth_key]['Entry Model']
            del user_data[auth_key]['Entry TF']
            del user_data[auth_key]['Point B']
            del user_data[auth_key]['SL Position']
            del user_data[auth_key]['RR']
        else:
            await query.edit_message_text("Помилка при відправці трейду в Notion. Перевір логи.")
    
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
            [InlineKeyboardButton("RR", callback_data='edit_rr')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Який параметр хочеш змінити?", reply_markup=reply_markup)
    
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
            [InlineKeyboardButton(">50@ or FullFill", callback_data='testpoi_>50@ or FullFill')]
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
        user_data[auth_key]['Trigger'] = []  # Очищаємо попередні вибори
        keyboard = [
            [InlineKeyboardButton("Fractal Swing", callback_data='trigger_Fractal Swing')],
            [InlineKeyboardButton("FVG", callback_data='trigger_FVG')],
            [InlineKeyboardButton("No Trigger", callback_data='trigger_No Trigger')],
            [InlineKeyboardButton("Готово", callback_data='trigger_done')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"Trigger? (Обрано: {', '.join(user_data[auth_key]['Trigger']) if user_data[auth_key]['Trigger'] else 'Нічого не обрано'})", reply_markup=reply_markup)
    
    elif query.data == 'edit_vc':
        user_data[auth_key]['VC'] = []  # Очищаємо попередні вибори
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
    logger.info("Bot polling stopped.")

if __name__ == '__main__':
    main()