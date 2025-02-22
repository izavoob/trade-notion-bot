import os
import json
import requests
from flask import Flask, request, redirect

app = Flask(__name__)

CLIENT_ID = os.getenv('NOTION_CLIENT_ID')
CLIENT_SECRET = os.getenv('NOTION_CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')
HEROKU_API_KEY = os.getenv('HEROKU_API_KEY')

@app.route('/')
def hello():
    return "Hello, Trade Notion Bot!"

@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    app.logger.info(f"Отримано code: {code}, user_id: {state}")

    token_url = 'https://api.notion.com/v1/oauth/token'
    auth = (CLIENT_ID, CLIENT_SECRET)
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI
    }
    response = requests.post(token_url, auth=auth, data=data)
    response_data = response.json()

    if 'access_token' in response_data:
        notion_token = response_data['access_token']
        conn = heroku3.from_key(HEROKU_API_KEY)
        heroku_app = conn.apps()['tradenotionbot-lg2']  # Оновіть назву додатку, якщо потрібно
        config = heroku_app.config()
        user_data = json.loads(config.get('HEROKU_USER_DATA', '{}'))
        user_data[state] = {'notion_token': notion_token}
        config['HEROKU_USER_DATA'] = json.dumps(user_data)
        app.logger.info(f"Збережено user_data: {json.dumps(user_data)}")
        return "Авторизація успішна! Повертайтесь до бота та введіть /start."
    else:
        app.logger.error(f"Помилка авторизації: {response_data}")
        return "Помилка авторизації. Перевірте логи."

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)