from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

# Замініть 'YOUR_TELEGRAM_TOKEN' на токен вашого Telegram-бота
TELEGRAM_TOKEN = '8010871228:AAGJeGe49XEsg1er3rDhB9xWI_3X95Ww65Q'

async def handle_photo(update: Update, context: CallbackContext):
    photo = update.message.photo[-1]  # Отримуємо фото з найвищою роздільною здатністю
    file_id = photo.file_id
    print(f"Photo file_id: {file_id}")
    await update.message.reply_text(f"Зображення збережено. File ID: {file_id}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Додаємо обробник фото
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Запускаємо бота
    application.run_polling(allowed_updates=["message"])  # Виправлено!

if __name__ == '__main__':
    main()
