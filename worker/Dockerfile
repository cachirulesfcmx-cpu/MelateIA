FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY worker/requirements.txt worker/requirements.txt
RUN pip install --no-cache-dir -r worker/requirements.txt
COPY worker/ worker/
COPY backend/data/ data/
ENV MELATE_DATA_DIR=/app/data
ENTRYPOINT ["python", "-m", "worker.main"]
