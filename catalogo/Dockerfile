FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /data

COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8001

# Entrypoint corrige permisos del volumen y ejecuta como nobody
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:8001 --workers ${WORKERS:-2} --access-logfile - --timeout 30 app:app"]
