FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY main.py .

# Открываем порт
EXPOSE 8080

# Запускаем бота
CMD ["python", "main.py"]