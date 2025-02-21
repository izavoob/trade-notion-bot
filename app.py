import requests
from flask import Flask, request
import os
import json

app = Flask(__name__)

# Конфігурація через змінні середовища
CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')

# Зберігання даних користувачів
USER_DATA_FILE = 'user_data.json'
user_data = {}
if os.path.exists(USER_DATA_FILE):
    with open(USER_DATA_FILE, 'r') as f:
        user_data = json.load(f)

# Flask маршрути
@app.route('/')
def hello():
    return "Бот працює! Версія 2"

@app.route('/callback', methods=['GET'])
def oauth_callback():
    code = request.args.get('code')
    user_id = request.args.get('state')
    print(f"Отримано code: {code}, user_id: {user_id}")  # Дебаг
    if code and user_id:
        token_response = requests.post(
            'https://api.notion.com/v1/oauth/token',
            auth=(CLIENT_ID, CLIENT_SECRET),
            data={'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI}
        ).json()
        print(f"Notion відповідь: {token_response}")  # Дебаг
        if 'access_token' in token_response:
            user_data[user_id] = {'notion_token': token_response['access_token']}
            with open(USER_DATA_FILE, 'w') as f:
                json.dump(user_data, f)
            print(f"Збережено user_data: {user_data}")  # Дебаг
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)