# Valo Stats — production image.
# Includes the native libraries WeasyPrint needs (Pango/Cairo/GDK-PixBuf) so
# real PDF generation works on Render (the app otherwise falls back to HTML).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# WeasyPrint runtime dependencies + fonts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libcairo2 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Single worker keeps the in-memory job registry consistent across the
# /start and /stream (SSE) requests; threads handle concurrent users.
# --timeout 0 so long-lived SSE streams are not killed.
CMD ["sh", "-c", "gunicorn --workers 1 --threads 8 --timeout 0 --bind 0.0.0.0:${PORT:-5000} app:app"]
