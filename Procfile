web: gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --max-requests 50 --max-requests-jitter 10 --timeout 60
