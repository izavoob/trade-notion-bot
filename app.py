import os
import json
import requests
from flask import Flask, request
from threading import Lock

app = Flask(__name__)

CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')

# Завантажуємо user_data із файлу
USER_DATA_FILE = 'user_data.json'
user_data_lock = Lock()

def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f)

user_data = load_user_data()

@app.route('/')
def hello():
    return "Бот працює! Версія 2"

@app.route('/callback', methods=['GET'])
def oauth_callback():
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
            with user_data_lock:
                user_data[user_id] = {'notion_token': token_response['access_token']}
                save_user_data(user_data)
                print(f"Збережено user_data: {user_data}")
            return "Авторизація успішна! Повернись у Telegram і напиши /start."
    return "Помилка авторизації."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)