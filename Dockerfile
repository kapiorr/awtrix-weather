FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Europe/Warsaw

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY awtrix_weather/ ./awtrix_weather/

# config.yaml montujemy przez volume (patrz docker-compose.yml) -
# nie kopiujemy go do obrazu, żeby nie trzymać sekretów w warstwach.

CMD ["python", "main.py", "-c", "/app/config/config.yaml"]
