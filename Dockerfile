
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

# Create directories
RUN mkdir -p certs templates

# Copy certificates and templates
COPY certs/ ./certs/
COPY templates/ ./templates/

# Expose ports - TLS server and web GUI
EXPOSE 16017 5000

# Set proper permissions for certificates
RUN chmod -R 644 certs/ || true

# Ensure endpoints.json is writable
RUN touch endpoints.json && chmod 666 endpoints.json || true

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Run the application with unbuffered output
CMD ["python", "-u", "main.py"]
