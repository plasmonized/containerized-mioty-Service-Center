
#!/bin/bash
set -e

# Wait for certificates to be available
if [ ! -f "/app/certs/service_center_cert.pem" ]; then
    echo "Warning: SSL certificates not found. Please mount certificates to /app/certs/"
fi

# Create logs directory if it doesn't exist
mkdir -p /app/logs

# Ensure config files are writable (in case host permissions are wrong)
if [ -w /app ]; then
    chmod 664 /app/endpoints.json /app/bssci_config.py 2>/dev/null || true
fi

# Check if running with web UI or just the service
if [ "${RUN_MODE}" = "service-only" ]; then
    echo "Starting synchronous BSSCI service..."
    exec python -u sync_main.py
else
    echo "Starting synchronous BSSCI service..."
    exec python -u sync_main.py
fi
