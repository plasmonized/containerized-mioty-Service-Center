
#!/bin/bash
set -e

# Wait for certificates to be available
if [ ! -f "/app/certs/service_center_cert.pem" ]; then
    echo "Warning: SSL certificates not found. Please mount certificates to /app/certs/"
fi

# Create logs directory if it doesn't exist
mkdir -p /app/logs

# Check if running with web UI or just the service
if [ "${RUN_MODE}" = "service-only" ]; then
    echo "Starting BSSCI service only..."
    exec python -u main.py
else
    echo "Starting BSSCI service with Web UI..."
    exec python -u web_main.py
fi
