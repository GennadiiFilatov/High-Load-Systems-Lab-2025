FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8000

# Use Flask's built-in server with threading for simplicity
# For production, consider using gevent or eventlet with gunicorn
CMD ["python", "app.py"]
