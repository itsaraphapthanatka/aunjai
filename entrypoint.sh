#!/bin/bash

# Wait for database to be ready
echo "Waiting for postgres (db:5432)..."

MAX_RETRIES=30
RETRY_COUNT=0

until nc -z db 5432 2>/dev/null || [ $RETRY_COUNT -eq $MAX_RETRIES ]; do
  echo "Waiting for database connection (attempt $((RETRY_COUNT+1))/$MAX_RETRIES)..."
  sleep 2
  RETRY_COUNT=$((RETRY_COUNT+1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "Error: Database connection timed out."
  exit 1
fi

echo "PostgreSQL is up and reachable!"

# Initialize database
echo "Initializing database..."
python init_db.py

# Start the API server
echo "Starting FastAPI server..."
uvicorn api_server:app --host 0.0.0.0 --port 8000
