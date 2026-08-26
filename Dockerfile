FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

FROM python:3.11-slim AS runner

ARG APP_VERSION=0.8.2-dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 1000 appuser \
    && mkdir /data \
    && chown appuser:appuser /data

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 39421

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "39421"]
