FROM python:3.11-slim
WORKDIR /service
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home worker
COPY worker.py .
RUN mkdir -p /data/worker && chown -R worker:worker /data/worker
USER worker
EXPOSE 8081
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health')"
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8081", "--no-access-log"]
