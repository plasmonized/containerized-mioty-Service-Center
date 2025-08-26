
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./
COPY templates/ ./templates/
COPY endpoints.json ./
COPY bssci_config.py ./

# Create certs directory
RUN mkdir -p certs

# Copy certificates if they exist
COPY certs/ ./certs/

# Expose the TLS port and web UI port
EXPOSE 16017 5000

# Set proper permissions for certificates
RUN chmod -R 644 certs/ || true

# Create a non-root user for security
RUN useradd -m -u 1000 bssci

# Set ownership of all files to bssci user
RUN chown -R bssci:bssci /app

# Ensure configuration files are writable
RUN chmod 664 endpoints.json bssci_config.py

# Switch to non-root user
USER bssci

# Run the application with web UI and unbuffered output
CMD ["python", "-u", "web_main.py"]
