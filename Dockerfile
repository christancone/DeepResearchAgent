FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for the project and Playwright
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    curl \
    git \
    make \
    # Playwright dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml poetry.lock requirements.txt Makefile README.md ./

# Install dependencies following the exact README/Makefile process:
# 1. Install poetry
# 2. Install markitdown[all]
# 3. Install browser-use[memory]==0.1.48
# 4. Install playwright and chromium browser
# 5. Poetry install (--no-root to skip installing current project, we just need deps)
# 6. Install xlrd==2.0.1
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir poetry && \
    pip install --no-cache-dir 'markitdown[all]' && \
    pip install --no-cache-dir "browser-use[memory]==0.1.48" && \
    pip install --no-cache-dir playwright && \
    playwright install chromium --with-deps && \
    poetry config virtualenvs.create false && \
    poetry lock && \
    poetry install --no-interaction --no-ansi --no-root && \
    pip install --no-cache-dir xlrd==2.0.1

# Copy the entire project
COPY . .

# Create outputs directory
RUN mkdir -p /app/outputs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "main.py"]
