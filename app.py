import os
import json
import requests
from flask import Flask, request
from asyncio import Lock as AsyncLock
from hypercorn.config import Config
from hypercorn.asyncio import serve

app = Flask(__name__)

CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

# Завантажуємо user_data із змінної Heroku
user_data = json.loads(os.getenv('HEROKU_USER_DATA', '{}'))
user_data_lock = AsyncLock()  # Використовуємо asyncio.Lock для асинхронного доступу

@app.route('/')
async def hello():
    return "Бот працює! Версія 2"

@app.route('/callback', methods=['GET'])
async def oauth_callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    print(f"Отримано code: {code}, user_id: {user_id}")
    if code and user_id:
        token_response = requests.post(
            'https://api.notion.com/v1/oauth/token',
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        ).json()
        print(f"Notion відповідь: {token_response}")
        if 'access_token' in token_response:
            async with user_data_lock:  # Асинхронне блокування
                user_data[user_id] = {'notion_token': token_response['access_token']}
                # Оновлюємо HEROKU_USER_DATA через Heroku API
                import heroku3
                conn = heroku3.from_key(HEROKU_API_KEY)
                heroku_app = conn.apps()['tradenotionbot-lg2']
                heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
                print(f"Збережено user_data: {user_data}")
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

if __name__ == '__main__':
    import asyncio
    config = Config()
    config.bind = [f"0.0.0.0:{int(os.environ.get('PORT', 5000))}"]
    asyncio.run(serve(app, config))