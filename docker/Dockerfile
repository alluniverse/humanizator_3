FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including build tools, curl for health checks, and Java for language-tool-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    libpq-dev \
    curl \
    default-jre \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definitions first for layer caching
COPY pyproject.toml ./
COPY backend/ ./backend/

# Install Python dependencies (use local venv packages if available via volume)
RUN pip install --no-cache-dir -e ".[dev]"

# Download spaCy models
RUN python -m spacy download en_core_web_sm || true
RUN python -m spacy download ru_core_news_sm || true

# Expose port
EXPOSE 8000

# Default command (overridden in docker-compose)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
