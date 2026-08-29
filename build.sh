#!/usr/bin/env bash
# exit on error
set -o errexit

echo "Running build script..."

# Ensure pip is up to date
python -m pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Set production settings module for build tasks
export DJANGO_SETTINGS_MODULE=core.settings.production

# Run migrations
python manage.py migrate --no-input

# Collect static files with manifest storage
python manage.py collectstatic --no-input --clear

echo "Build complete."
