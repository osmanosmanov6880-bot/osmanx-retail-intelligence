FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OSMANX_DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
COPY scripts ./scripts
RUN groupadd --system osmanx && useradd --system --gid osmanx --home /app osmanx \
    && mkdir -p /data && chown -R osmanx:osmanx /data /app
USER osmanx
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready',timeout=3)" || exit 1
CMD ["uvicorn","backend.app:app","--host","0.0.0.0","--port","8000","--workers","1"]
