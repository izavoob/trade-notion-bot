import os
import json
import requests
import heroku3
from flask import Flask, request
from threading import Lock
import logging

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

# Завантажуємо user_data із змінної Heroku з обробкою помилок
raw_user_data = os.getenv('HEROKU_USER_DATA', '{}')
try:
    user_data = json.loads(raw_user_data)
except json.JSONDecodeError:
    logger.error(f"Помилка парсингу HEROKU_USER_DATA: '{raw_user_data}'. Використовуємо порожній словник.")
    user_data = {}
user_data_lock = Lock()  # Блокування для синхронізації

@app.route('/')
def hello():
    return "Бот працює! Версія 2"

@app.route('/callback', methods=['GET'])
def oauth_callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    logger.info(f"Отримано code: {code}, user_id: {user_id}")
    if code and user_id:
        token_response = requests.post(
            'https://api.notion.com/v1/oauth/token',
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        ).json()
        logger.debug(f"Notion відповідь: {token_response}")
        if 'access_token' in token_response:
            with user_data_lock:  # Синхронізований доступ до user_data
                user_data[user_id] = {'notion_token': token_response['access_token']}
                # Оновлюємо HEROKU_USER_DATA через Heroku API
                try:
                    conn = heroku3.from_key(HEROKU_API_KEY)
                    heroku_app = conn.apps()['tradenotionbot-lg2']
                    heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                    logger.info(f"Збережено user_data: {user_data}")
                except Exception as e:
                    logger.error(f"Помилка оновлення HEROKU_USER_DATA: {str(e)}")
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)