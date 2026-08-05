#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Running build script..."

# Ensure pip is up to date
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate --no-input

# Collect static files
python manage.py collectstatic --no-input

echo "Build complete."
