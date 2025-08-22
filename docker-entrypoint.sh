
#!/bin/bash
set -e

# Ensure certificates directory exists
mkdir -p /app/certs

# Check if certificates exist
if [ ! -f "/app/certs/service_center_cert.pem" ] || [ ! -f "/app/certs/service_center_key.pem" ] || [ ! -f "/app/certs/ca_cert.pem" ]; then
    echo "Warning: SSL certificates not found in /app/certs/"
    echo "Please ensure the following files exist:"
    echo "  - service_center_cert.pem"
    echo "  - service_center_key.pem"
    echo "  - ca_cert.pem"
    echo "Starting application anyway..."
fi

# Ensure endpoints.json exists
if [ ! -f "/app/endpoints.json" ]; then
    echo "Creating empty endpoints.json"
    echo "[]" > /app/endpoints.json
fi

# Make endpoints.json writable
chmod 666 /app/endpoints.json

echo "Starting BSSCI Service Center..."
echo "TLS Server will be available on port 16017"
echo "Web GUI will be available on port 5000"

# Execute the main command
exec "$@"
