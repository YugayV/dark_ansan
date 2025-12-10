# Создайте файл set_webhook.py
import requests
import os

BOT_TOKEN = os.getenv('BOT_TOKEN')
RAILWAY_URL = "https://ваш-проект.up.railway.app"  # Замените на ваш URL

response = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
    json={'url': f'{RAILWAY_URL}/{BOT_TOKEN}'}
)

print(response.json())