
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./

# Create data directory with proper permissions
RUN mkdir -p /app/data && chmod 755 /app/data

# Create certs directory
RUN mkdir -p certs

# Copy certificates if they exist
COPY certs/ ./certs/

# Expose the TLS port
EXPOSE 16017

# Set proper permissions for certificates
RUN chmod -R 644 certs/ || true

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Change ownership of app directory to appuser
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Run the application with unbuffered output
CMD ["python", "-u", "main.py"]
