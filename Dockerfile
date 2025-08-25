
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./
COPY endpoints.json ./
COPY bssci_config.py ./

# Create necessary directories
RUN mkdir -p certs

# Copy certificates if they exist
COPY certs/ ./certs/

# Expose the TLS port
EXPOSE 16017

# Set proper permissions for certificates
RUN chmod -R 644 certs/ || true

# Ensure endpoints.json is writable
RUN touch endpoints.json && chmod 666 endpoints.json

# Run the application with unbuffered output
CMD ["python", "-u", "main.py"]
