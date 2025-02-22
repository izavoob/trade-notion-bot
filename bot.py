import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

async def start(update, context):
    user_id = str(update.message.from_user.id)
    logger.info(f"Start command received from user {user_id}")
    keyboard = [
        [InlineKeyboardButton("Додати новий трейд", callback_data='add_trade_test')],
        [InlineKeyboardButton("Переглянути останній трейд", callback_data='view_last_trade_test')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Привіт! Вибери дію:', reply_markup=reply_markup)
    logger.info(f"Sent menu to user {user_id}")

async def button(update, context):
    query = update.callback_query
    user_id = str(query.from_user.id)
    logger.info(f"Button callback received from user {user_id}: {query.data}")
    await query.answer()
    
    if query.data == 'add_trade_test':
        logger.info(f"Processing add_trade for user {user_id}")
        await query.edit_message_text('Pair?')
    elif query.data == 'view_last_trade_test':
        logger.info(f"Processing view_last_trade for user {user_id}")
        await query.edit_message_text('Перегляд останнього трейду.')

def main():
    logger.info("Starting bot with TELEGRAM_TOKEN: [REDACTED]")
    application = Application.builder().token(TELEGRAM_TOKEN).read_timeout(60).write_timeout(60).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    logger.info("Bot handlers registered. Starting polling...")
    application.run_polling()

if __name__ == '__main__':
    main()