# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency locks into the container
COPY requirements.lock .

# Install pinned runtime dependencies
RUN pip install --no-cache-dir -r requirements.lock

# Copy the current directory contents into the container at /app
COPY . .

# Make port 39421 available to the world outside this container
EXPOSE 39421

# Run main.py when the container launches
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "39421"]
