
#!/bin/bash
set -e

# Ensure proper permissions on log directory
mkdir -p /app/logs
chmod 755 /app/logs

# Ensure certificates directory exists
mkdir -p /app/certs

# Handle Synology Docker setup
if [ "$SYNOLOGY_DOCKER" = "1" ]; then
    echo "Synology Docker mode detected - copying config files to writable locations"
    
    # Copy config files from host mounts to writable container locations
    if [ -f "/tmp/host_bssci_config.py" ]; then
        cp /tmp/host_bssci_config.py /app/bssci_config.py
        echo "Copied bssci_config.py to writable location"
    fi
    
    if [ -f "/tmp/host_endpoints.json" ]; then
        cp /tmp/host_endpoints.json /app/endpoints.json
        echo "Copied endpoints.json to writable location"
    fi
    
    if [ -f "/tmp/host_.env" ]; then
        cp /tmp/host_.env /app/.env
        echo "Copied .env to writable location"
    fi
    
    # Ensure .env exists and is writable
    touch /app/.env 2>/dev/null || true
    
    # Set proper permissions on copied files
    chmod 644 /app/bssci_config.py /app/endpoints.json 2>/dev/null || true
    chmod 666 /app/.env 2>/dev/null || true
    chown $(id -u):$(id -g) /app/bssci_config.py /app/endpoints.json /app/.env 2>/dev/null || true
    
    echo "Synology setup complete - config files are now writable"
else
    # Standard Docker setup - fix permissions for configuration files at runtime
    touch /app/.env 2>/dev/null || true
    chmod 644 /app/bssci_config.py /app/endpoints.json 2>/dev/null || true
    chmod 666 /app/.env 2>/dev/null || true
    chown $(id -u):$(id -g) /app/bssci_config.py /app/endpoints.json /app/.env 2>/dev/null || true
fi

# Generate self-signed certificates if they don't exist
if [ ! -f "/app/certs/ca_cert.pem" ] || [ ! -f "/app/certs/service_center_cert.pem" ] || [ ! -f "/app/certs/service_center_key.pem" ]; then
    echo "Generating SSL certificates..."
    
    # Generate CA private key
    openssl genrsa -out /app/certs/ca_key.pem 4096
    
    # Generate CA certificate
    openssl req -new -x509 -days 365 -key /app/certs/ca_key.pem -out /app/certs/ca_cert.pem -subj "/C=US/ST=State/L=City/O=Organization/CN=BSSCI-CA"
    
    # Generate service center private key
    openssl genrsa -out /app/certs/service_center_key.pem 4096
    
    # Generate service center certificate signing request
    openssl req -new -key /app/certs/service_center_key.pem -out /app/certs/service_center.csr -subj "/C=US/ST=State/L=City/O=Organization/CN=BSSCI-ServiceCenter"
    
    # Generate service center certificate signed by CA
    openssl x509 -req -in /app/certs/service_center.csr -CA /app/certs/ca_cert.pem -CAkey /app/certs/ca_key.pem -CAcreateserial -out /app/certs/service_center_cert.pem -days 365
    
    # Clean up CSR file
    rm /app/certs/service_center.csr
    
    echo "SSL certificates generated successfully"
fi

# Execute the main command
exec "$@"
