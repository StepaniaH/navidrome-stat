# === Stage 1: builder ===
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build tools only for the builder stage (discarded later)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated virtualenv for pinned runtime dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency locks into the container and install into the venv
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

# === Stage 2: runner ===
FROM python:3.11-slim AS runner

WORKDIR /app

# Bring in the prebuilt virtualenv from the builder; build-essential stays behind
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user and ensure /app is owned by it
RUN useradd --create-home --uid 1000 appuser

# Copy the application code with the correct ownership
COPY --chown=appuser:appuser . .

USER appuser

# Make port 39421 available to the world outside this container
EXPOSE 39421

# Run main.py when the container launches
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "39421"]
