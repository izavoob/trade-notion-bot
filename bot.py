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

# Завантажуємо user_data один раз при старті бота
user_data = json.loads(os.getenv('HEROKU_USER_DATA', '{}'))

# Мапінг значень для "Relation"
RELATION_IDS = {
    'Context': {
        'Against Context': '1a084b079a828143ad09fea9de3ea593',
        'By Context': '1a084b079a82815bb117c38c1e54e443',
        'Neutral Context': '1a084b079a8281ac87ffd9b9251eb9f6'
    },
    'Test POI': {
        '>50@ or FullFill': '1a084b079a828121874ef45d9b58ead8',
        'Minimal': '1a184b079a82801aa510fde344303b9d'
    },
    'Point A': {
        'SNR': '1a084b079a82812e8f6fe33c1e19e95b',
        'FVG': '1a084b079a828182bea3c8c27deaa134',
        'Fractal Raid': '1a084b079a8281dc9903e1fe26df44c6',
        'RB': '1a084b079a828144aeead84eb2147680'
    },
    'Trigger': {
        'FVG': '1a084b079a828141b08dce31c1826006',
        'No Trigger': '1a084b079a82815398c6dd36c8dd9bdc',
        'Fractal Swing': '1a084b079a8281b29c1ee9673723b42a'
    },
    'VC': {
        'FVG': '1a084b079a82814d80e6f3e073eae4dd',
        'Inversion': '1a084b079a8281b18387ef9e2ab02a31',
        'SNR': '1a084b079a828119aa86d94e8fd0a012'
    },
    'Entry model': {
        'Inversion': '1a084b079a82819393a1f80b69affc20',
        'Displacement': '1a084b079a8281a1b9fadb1ab862a353',
        'SNR': '1a084b079a8281c3b955d789ce6396f6',
        'IDM': '1a084b079a8281fb8212fdd3d04e598c'
    },
    'Entry TF': {
        '5m': '1a084b079a8281ce86a4ffd97970ae66',
        '15m': '1a084b079a82813e80bafa257eef5fc6',
        '4H': '1a084b079a82818ab108cb21587e6c08',
        '3m': '1a084b079a82819bb09ae1b4362edbb0',
        '1H/30m': '1a084b079a8281eabeaef14161a20169'
    },
    'Point B': {
        'FVG': '1a084b079a82811c9cc9c1b8e16dc876',
        'Fractal Swing': '1a084b079a8281d1ba74c8b2d4f23d43'
    },
    'SL Position': {
        '1H/30m Raid': '1a084b079a82816d91f4c20441a5e6fb',
        'LTF/Lunch Manipulation': '1a084b079a828150ab31f4571d22e8f9',
        '4H Raid': '1a084b079a82815ab240f3ffbc680f18'
    }
}

# Початок роботи бота
async def start(update, context):
    global user_data
    user_id = str(update.message.from_user.id)
    auth_key = f"{user_id}user"
    print(f"Перевірка user_data перед /start: {user_data}")
    if auth_key not in user_data or 'notion_token' not in user_data[auth_key]:
        auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&state={user_id}user"
        print(f"Сформований auth_url: {auth_url}")
        keyboard = [[InlineKeyboardButton("Авторизуватись у Notion", url=auth_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Спочатку авторизуйся в Notion:', reply_markup=reply_markup)
    elif 'database_id' not in user_data[auth_key]:
        await update.message.reply_text('Введи ID бази "Classification" (32 символи з URL):')
    else:
        keyboard = [[InlineKeyboardButton("Додати трейд", callback_data='add_trade')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Привіт! Натисни, щоб додати трейд:', reply_markup=reply_markup)

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
            # Зберігаємо в Heroku після введення database_id
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
            # Перевіряємо, чи всі необхідні ключі присутні
            required_keys = ['Pair', 'Session', 'Context', 'Test POI', 'Delivery to POI', 'Point A', 
                            'Trigger', 'VC', 'Entry model', 'Entry TF', 'Point B', 'SL Position', 'RR']
            missing_keys = [key for key in required_keys if key not in user_data[auth_key]]
            if missing_keys:
                await update.message.reply_text(f"Помилка: відсутні дані для {', '.join(missing_keys)}. Почни заново через 'Додати трейд'.")
            else:
                create_notion_page(auth_key)
                await update.message.reply_text(format_summary(user_data[auth_key]))
                # Зберігаємо в Heroku лише після завершення трейду
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                print(f"Збережено user_data в HEROKU_USER_DATA: {user_data}")
                # Очищаємо дані після успішного трейду
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
        'Notion-Version': '2022-06-28'
    }
    payload = {
        'parent': {'database_id': user_data[user_id]['database_id']},
        'properties': {
            'Pair': {'select': {'name': user_data[user_id]['Pair']}},
            'Session': {'select': {'name': user_data[user_id]['Session']}},
            'Context': {'relation': [{'id': RELATION_IDS['Context'][user_data[user_id]['Context']]}]},
            'Test POI': {'relation': [{'id': RELATION_IDS['Test POI'][user_data[user_id]['Test POI']]}]},
            'Delivery to POI': {'select': {'name': user_data[user_id]['Delivery to POI']}},
            'Point A': {'relation': [{'id': RELATION_IDS['Point A'][user_data[user_id]['Point A']]}]},
            'Trigger': {'relation': [{'id': RELATION_IDS['Trigger'][user_data[user_id]['Trigger']]}]},
            'VC': {'relation': [{'id': RELATION_IDS['VC'][user_data[user_id]['VC']]}]},
            'Entry Model': {'relation': [{'id': RELATION_IDS['Entry model'][user_data[user_id]['Entry model']]}]},
            'Entry TF': {'relation': [{'id': RELATION_IDS['Entry TF'][user_data[user_id]['Entry TF']]}]},
            'Point B': {'relation': [{'id': RELATION_IDS['Point B'][user_data[user_id]['Point B']]}]},
            'SL Position': {'relation': [{'id': RELATION_IDS['SL Position'][user_data[user_id]['SL Position']]}]},
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
        print("Запит Test POI відправлено")
    
    elif query.data.startswith('testpoi_'):
        print(f"Отримано callback_data: {query.data}")
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