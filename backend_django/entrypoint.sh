#!/bin/bash
set -e
echo "Running migrations..."
python manage.py migrate --noinput
echo "Seeding data..."
python manage.py seed_data --noinput
echo "Starting gunicorn..."
exec "$@"
