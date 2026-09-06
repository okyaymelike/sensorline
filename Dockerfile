FROM python:3.12-slim

WORKDIR /app

# confluent-kafka and psycopg ship binary wheels, so no system build deps needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common ./common
COPY ingester ./ingester
COPY processor ./processor
COPY simulator ./simulator

# default command; each service overrides it in docker-compose.
CMD ["python", "-m", "processor"]
