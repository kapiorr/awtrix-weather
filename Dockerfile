FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Europe/Warsaw

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY upload_icons.py .
COPY awtrix_weather/ ./awtrix_weather/

# Zabezpieczenie: gdyby na hoście leżały jakieś stare __pycache__/*.pyc
# (np. z ręcznego uruchomienia poza Dockerem), .dockerignore powinien je
# odsiać z kontekstu builda, ale usuwamy je tu jeszcze raz na wszelki
# wypadek - nieaktualny .pyc potrafi "zasłonić" świeży kod źródłowy.
RUN find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; \
    find . -name "*.pyc" -delete

# config.yaml montujemy przez volume (patrz docker-compose.yml) -
# nie kopiujemy go do obrazu, żeby nie trzymać sekretów w warstwach.

CMD ["python", "main.py", "-c", "/app/config/config.yaml"]
