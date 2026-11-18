FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 FRONTEND_DIR=/app/frontend
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt psycopg2-binary

COPY backend backend
COPY frontend frontend

WORKDIR /app/backend
EXPOSE 8000
# ONE worker on purpose: the scheduler runs inside the app process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
