FROM python:3.12-slim

WORKDIR /app

# system deps (optional but nice for some pdf edge cases)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY demo/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY demo/api/app.py ./app.py
COPY eval ./eval

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host=0.0.0.0", "--port=8080"]
