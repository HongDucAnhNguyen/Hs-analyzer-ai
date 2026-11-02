FROM python:3.10.8-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY ./ /app/rag_service

CMD ["bash", "/app/rag_service/run.sh", "prod"]