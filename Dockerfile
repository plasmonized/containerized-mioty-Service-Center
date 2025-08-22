
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

# Create certs directory
RUN mkdir -p certs

# Copy certificates if they exist
COPY certs/ ./certs/

# Expose the TLS port
EXPOSE 16017

# Run the application
CMD ["python", "main.py"]
