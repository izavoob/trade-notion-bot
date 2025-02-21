import os
import json
import requests
import heroku3
from flask import Flask, request

app = Flask(__name__)

CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')  # Додай свій API ключ Heroku

# Завантажуємо user_data із змінної Heroku
user_data = json.loads(os.getenv('HEROKU_USER_DATA', '{}'))

@app.route('/')
def hello():
    return "Бот працює! Версія 2"

@app.route('/callback', methods=['GET'])
def oauth_callback():
    global user_data
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
            user_data[user_id] = {'notion_token': token_response['access_token']}
            # Оновлюємо HEROKU_USER_DATA через Heroku API
            conn = heroku3.from_key(HEROKU_API_KEY)
            heroku_app = conn.apps()['tradenotionbot-lg2']
            heroku_app.config()['HEROKU_USER_DATA'] = json.dumps(user_data)
            print(f"Збережено user_data: {user_data}")
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)