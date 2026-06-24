# Hosts the self-serve Loc Sentinel Console (demo mode — no secrets needed).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Demo mode: the console works with the committed translation cache, no API key.
ENV DEMO_MODE=true \
    PYTHONUNBUFFERED=1

EXPOSE 8000
# Hosts (Render/Railway/Fly) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.web.console:app --host 0.0.0.0 --port ${PORT:-8000}"]
