
#!/bin/bash
set -e

echo "=== BSSCI Docker Entrypoint - Synology Edition ==="
echo "Current user: $(id)"
echo "Current working directory: $(pwd)"

# Synology-specific setup
if [ "$SYNOLOGY_DOCKER" = "1" ]; then
    echo "=== Synology Docker Environment Detected ==="
    
    # Create writable copies of config files in container
    echo "Setting up writable configuration files..."
    
    # Copy host config files to writable locations
    if [ -f "/tmp/host_endpoints.json" ]; then
        cp /tmp/host_endpoints.json /app/endpoints.json
        chmod 666 /app/endpoints.json
        echo "✓ endpoints.json copied and made writable"
    else
        echo "[]" > /app/endpoints.json
        chmod 666 /app/endpoints.json
        echo "✓ Created empty endpoints.json"
    fi
    
    if [ -f "/tmp/host_bssci_config.py" ]; then
        cp /tmp/host_bssci_config.py /app/bssci_config.py
        chmod 666 /app/bssci_config.py
        echo "✓ bssci_config.py copied and made writable"
    else
        echo "# Default BSSCI Configuration" > /app/bssci_config.py
        chmod 666 /app/bssci_config.py
        echo "✓ Created default bssci_config.py"
    fi
    
    # Set up sync mechanism for config changes back to host
    mkdir -p /app/sync
    echo "#!/bin/bash" > /app/sync_to_host.sh
    echo "# This script would sync changes back to host in a real deployment" >> /app/sync_to_host.sh
    echo "# For Synology, manual backup of /app/endpoints.json and /app/bssci_config.py is recommended" >> /app/sync_to_host.sh
    chmod +x /app/sync_to_host.sh
else
    echo "=== Standard Docker Environment ==="
    # Standard permission fixes for non-Synology environments
    chmod 666 /app/bssci_config.py /app/endpoints.json 2>/dev/null || true
fi

# Ensure directories exist with proper permissions
mkdir -p /app/logs /app/certs
chmod 755 /app/logs /app/certs

echo "=== Final File Permissions Check ==="
ls -la /app/bssci_config.py /app/endpoints.json /app/logs 2>/dev/null || echo "Some files not accessible"

# Test writability
echo "=== Testing Configuration File Write Access ==="
if echo "# Test write" >> /app/bssci_config.py 2>/dev/null; then
    sed -i '$d' /app/bssci_config.py  # Remove test line
    echo "✓ bssci_config.py is writable"
else
    echo "✗ bssci_config.py is NOT writable"
fi

if echo "test" > /tmp/test_endpoints.json && cat /tmp/test_endpoints.json > /app/endpoints.json 2>/dev/null; then
    rm /tmp/test_endpoints.json
    echo "✓ endpoints.json is writable"
else
    echo "✗ endpoints.json is NOT writable"
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

echo "=== Container startup complete ==="

# Execute the main command
exec "$@"
