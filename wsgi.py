"""Production WSGI entrypoint for Gunicorn.

Run with:
    gunicorn wsgi:app --bind 127.0.0.1:5000 --workers 1 --threads 4 --timeout 300 \
        --graceful-timeout 300 --limit-request-line 0 --limit-request-field_size 0
"""

from router import app
