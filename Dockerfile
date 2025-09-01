
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create app user for better security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create necessary directories
RUN mkdir -p certs logs

# Copy application files with proper ownership
COPY --chown=appuser:appuser . .

# Switch to app user
USER appuser

# Make entrypoint executable
USER root
RUN chmod +x docker-entrypoint.sh
USER appuser

# Expose ports
EXPOSE 16018 5000

# Use custom entrypoint
ENTRYPOINT ["./docker-entrypoint.sh"]

# Default command
CMD ["python", "web_main.py"]
