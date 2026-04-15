FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create data directory for JSON store
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python3", "main.py"]
