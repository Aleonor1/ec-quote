# ec-quote pe un VPS mic: un singur proces, un singur worker (limitele de ritm si lacatele sunt in memorie).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY ec_quote ./ec_quote
COPY config ./config
COPY templates ./templates
COPY knowledge ./knowledge

# Instalare editabila: fisierele statice si config/ raman langa cod.
# Verificarea fusului orar opreste constructia daca imaginea nu are datele de fus orar.
RUN pip install -e . \
    && python -c "import zoneinfo; zoneinfo.ZoneInfo('Europe/Bucharest')" \
    && useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin ecquote \
    && mkdir -p /data \
    && chown ecquote:ecquote /data

ARG GIT_COMMIT=""
ENV GIT_COMMIT=${GIT_COMMIT} \
    EC_QUOTE_DATA_DIR=/data

USER ecquote
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status == 200 else 1)"]

CMD ["python", "-m", "uvicorn", "ec_quote.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
