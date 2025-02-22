from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)
import requests
import json

# Токени та конфігурація
TELEGRAM_TOKEN = '8010871228:AAGJeGe49XEsg1er3rDhB9xWI_3X95Ww65Q'
NOTION_TOKEN = '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'
NOTION_DATABASE_ID = '1a084b079a82817cbd71ef12e7e714aa'

# Стани розмови
(
    START,
    CHOOSE_PAIR,
    CHOOSE_SESSION,
    CHOOSE_CONTEXT,
    CHOOSE_TEST_POI,
    CHOOSE_DELIVERY,
    CHOOSE_POINT_A,
    CHOOSE_TRIGGER,
    CHOOSE_VC,
    CHOOSE_ENTRY_MODEL,
    CHOOSE_ENTRY_TF,
    CHOOSE_POINT_B,
    CHOOSE_SL_POSITION,
    ENTER_RR,
    SUMMARY,
) = range(15)

# Зберігання даних користувача
user_data = {}

# Початкове меню
async def start(update: Update, context: CallbackContext) -> int:
    keyboard = [
        [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade')],
        [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade')],
        [InlineKeyboardButton("Інша кнопка 1", callback_data='other_button_1')],
        [InlineKeyboardButton("Інша кнопка 2", callback_data='other_button_2')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Виберіть опцію:', reply_markup=reply_markup)
    return START

# Обробка кнопки "Додати новий трейд"
async def add_trade(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id] = {}  # Ініціалізація даних користувача

    keyboard = [
        [InlineKeyboardButton("Обрати Шаблон", callback_data='choose_template')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Pair?', reply_markup=reply_markup)
    return CHOOSE_PAIR

# Обробка вибору пари
async def choose_pair(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Pair'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Session?', reply_markup=reply_markup)
    return CHOOSE_SESSION

# Обробка вибору сесії
async def choose_session(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Session'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Context?', reply_markup=reply_markup)
    return CHOOSE_CONTEXT

# Обробка вибору контексту
async def choose_context(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Context'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Test POI?', reply_markup=reply_markup)
    return CHOOSE_TEST_POI

# Обробка вибору Test POI
async def choose_test_poi(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Test POI'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Delivery to POI?', reply_markup=reply_markup)
    return CHOOSE_DELIVERY

# Обробка вибору Delivery to POI
async def choose_delivery(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Delivery to POI'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Point A?', reply_markup=reply_markup)
    return CHOOSE_POINT_A

# Обробка вибору Point A
async def choose_point_a(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Point A'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
        [InlineKeyboardButton("Готово", callback_data='done')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Trigger?', reply_markup=reply_markup)
    return CHOOSE_TRIGGER

# Обробка вибору Trigger
async def choose_trigger(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if 'Trigger' not in user_data[user_id]:
        user_data[user_id]['Trigger'] = []
    trigger = query.data.split('_')[1]
    if trigger in user_data[user_id]['Trigger']:
        user_data[user_id]['Trigger'].remove(trigger)
    else:
        user_data[user_id]['Trigger'].append(trigger)

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
        [InlineKeyboardButton("Готово", callback_data='done')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"Trigger: {', '.join(user_data[user_id]['Trigger'])}", reply_markup=reply_markup)
    return CHOOSE_TRIGGER

# Обробка вибору VC
async def choose_vc(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if 'VC' not in user_data[user_id]:
        user_data[user_id]['VC'] = []
    vc = query.data.split('_')[1]
    if vc in user_data[user_id]['VC']:
        user_data[user_id]['VC'].remove(vc)
    else:
        user_data[user_id]['VC'].append(vc)

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
        [InlineKeyboardButton("Готово", callback_data='done')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"VC: {', '.join(user_data[user_id]['VC'])}", reply_markup=reply_markup)
    return CHOOSE_VC

# Обробка вибору Entry Model
async def choose_entry_model(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Entry model'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Entry TF?', reply_markup=reply_markup)
    return CHOOSE_ENTRY_TF

# Обробка вибору Entry TF
async def choose_entry_tf(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Entry TF'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Point B?', reply_markup=reply_markup)
    return CHOOSE_POINT_B

# Обробка вибору Point B
async def choose_point_b(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['Point B'] = query.data.split('_')[1]

    keyboard = [
        [InlineKeyboardButton("Назад", callback_data='back')],
        [InlineKeyboardButton("Скасувати", callback_data='cancel')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('SL Position?', reply_markup=reply_markup)
    return CHOOSE_SL_POSITION

# Обробка вибору SL Position
async def choose_sl_position(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data[user_id]['SL Position'] = query.data.split('_')[1]

    await query.edit_message_text('Введіть RR (наприклад, 2.5):')
    return ENTER_RR

# Обробка введення RR
async def enter_rr(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    rr_input = update.message.text
    try:
        rr = float(rr_input)
        user_data[user_id]['RR'] = rr
        await update.message.reply_text(format_summary(user_data[user_id]))
        return SUMMARY
    except ValueError:
        await update.message.reply_text("Введіть коректне число для RR (наприклад, 2.5):")
        return ENTER_RR

# Підсумок та відправка в Notion
async def summary(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    create_notion_page(user_data[user_id])
    await update.message.reply_text('Трейд успішно додано до Notion!')
    return ConversationHandler.END

# Створення сторінки в Notion
def create_notion_page(data):
    url = 'https://api.notion.com/v1/pages'
    headers = {
        'Authorization': f'Bearer {NOTION_TOKEN}',
        'Content-Type': 'application/json',
        'Notion-Version': '2022-06-28'
    }
    payload = {
        'parent': {'database_id': NOTION_DATABASE_ID},
        'properties': {
            'Pair': {'select': {'name': data['Pair']}},
            'Session': {'select': {'name': data['Session']}},
            'Context': {'relation': [{'id': RELATION_IDS['Context'][data['Context']]}]},
            'Test POI': {'relation': [{'id': RELATION_IDS['Test POI'][data['Test POI']]}]},
            'Delivery to POI': {'select': {'name': data['Delivery to POI']}},
            'Point A': {'relation': [{'id': RELATION_IDS['Point A'][data['Point A']]}]},
            'Trigger': {'relation': [{'id': RELATION_IDS['Trigger'][trigger]} for trigger in data['Trigger']]},
            'VC': {'relation': [{'id': RELATION_IDS['VC'][vc]} for vc in data['VC']]},
            'Entry Model': {'relation': [{'id': RELATION_IDS['Entry model'][data['Entry model']]}]},
            'Entry TF': {'relation': [{'id': RELATION_IDS['Entry TF'][data['Entry TF']]}]},
            'Point B': {'relation': [{'id': RELATION_IDS['Point B'][data['Point B']]}]},
            'SL Position': {'relation': [{'id': RELATION_IDS['SL Position'][data['SL Position']]}]},
            'RR': {'number': data['RR']}
        }
    }
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        print(f"Помилка Notion API: {response.text}")

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
        f"Trigger: {', '.join(data['Trigger'])}\n"
        f"VC: {', '.join(data['VC'])}\n"
        f"Entry model: {data['Entry model']}\n"
        f"Entry TF: {data['Entry TF']}\n"
        f"Point B: {data['Point B']}\n"
        f"SL Position: {data['SL Position']}\n"
        f"RR: {data['RR']}"
    )

# Головна функція
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            START: [CallbackQueryHandler(add_trade, pattern='^add_trade$')],
            CHOOSE_PAIR: [
                CallbackQueryHandler(choose_pair, pattern='^pair_'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_SESSION: [
                CallbackQueryHandler(choose_session, pattern='^session_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_CONTEXT: [
                CallbackQueryHandler(choose_context, pattern='^context_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_TEST_POI: [
                CallbackQueryHandler(choose_test_poi, pattern='^testpoi_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_DELIVERY: [
                CallbackQueryHandler(choose_delivery, pattern='^delivery_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_POINT_A: [
                CallbackQueryHandler(choose_point_a, pattern='^pointa_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_TRIGGER: [
                CallbackQueryHandler(choose_trigger, pattern='^trigger_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
                CallbackQueryHandler(choose_vc, pattern='^done$'),
            ],
            CHOOSE_VC: [
                CallbackQueryHandler(choose_vc, pattern='^vc_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
                CallbackQueryHandler(choose_entry_model, pattern='^done$'),
            ],
            CHOOSE_ENTRY_MODEL: [
                CallbackQueryHandler(choose_entry_model, pattern='^entrymodel_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_ENTRY_TF: [
                CallbackQueryHandler(choose_entry_tf, pattern='^entrytf_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_POINT_B: [
                CallbackQueryHandler(choose_point_b, pattern='^pointb_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            CHOOSE_SL_POSITION: [
                CallbackQueryHandler(choose_sl_position, pattern='^slposition_'),
                CallbackQueryHandler(back, pattern='^back$'),
                CallbackQueryHandler(cancel, pattern='^cancel$'),
            ],
            ENTER_RR: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_rr)],
            SUMMARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, summary)],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()