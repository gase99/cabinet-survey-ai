FROM python:3.11-slim
WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home api
COPY . .
RUN mkdir -p /data/exports /data/assets && chown -R api:api /data
USER api
ENV EXPORT_STORAGE_DIR=/data/exports ASSET_STORAGE_DIR=/data/assets
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
