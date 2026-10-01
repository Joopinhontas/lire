FROM python:3.12-slim

LABEL org.opencontainers.image.title="Lire" \
      org.opencontainers.image.description="Self-hosted Seerr for manga and comics, filed into Kavita" \
      org.opencontainers.image.source="https://github.com/Joopinhontas/lire" \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATE_DIR=/state
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /srv/app/
RUN mkdir -p /state && chown 1000:1000 /state
USER 1000:1000

EXPOSE 8160
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8160/healthz', timeout=4)"

CMD ["uvicorn", "main:app", "--app-dir", "/srv/app", "--host", "0.0.0.0", "--port", "8160", \
     "--no-server-header"]
