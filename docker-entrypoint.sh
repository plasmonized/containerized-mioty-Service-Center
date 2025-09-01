
#!/bin/bash
set -e

echo "=== Docker Environment Debug Information ==="
echo "Current user: $(id)"
echo "Current working directory: $(pwd)"
echo "Environment variables:"
echo "  UID: ${UID:-not_set}"
echo "  GID: ${GID:-not_set}"
echo "  USER: ${USER:-not_set}"
echo "  HOME: ${HOME:-not_set}"

echo "=== File System Permissions Before Changes ==="
ls -la /app/ | head -10
echo "Current file ownership:"
ls -la /app/bssci_config.py /app/endpoints.json 2>/dev/null || echo "Config files not found"

# Ensure proper permissions on log directory
echo "=== Setting up directories ==="
mkdir -p /app/logs
chmod 755 /app/logs

# Ensure certificates directory exists
mkdir -p /app/certs

# Try multiple permission fix strategies
echo "=== Attempting permission fixes ==="

# Strategy 1: Try to take ownership if we're root
if [ "$(id -u)" = "0" ]; then
    echo "Running as root - attempting to fix ownership"
    chown -R $(id -u):$(id -g) /app/bssci_config.py /app/endpoints.json /app/logs 2>/dev/null || true
    chmod 666 /app/bssci_config.py /app/endpoints.json 2>/dev/null || true
else
    echo "Running as non-root user $(id -u):$(id -g)"
fi

# Strategy 2: Try chmod regardless of ownership
echo "Setting file permissions..."
chmod 666 /app/bssci_config.py /app/endpoints.json 2>/dev/null || echo "chmod failed - continuing anyway"

# Strategy 3: Test if files are actually writable
echo "=== Testing file writability ==="
if [ -w "/app/bssci_config.py" ]; then
    echo "✓ bssci_config.py is writable"
else
    echo "✗ bssci_config.py is NOT writable"
    # Try to copy to a writable location and symlink back
    if cp /app/bssci_config.py /tmp/bssci_config.py 2>/dev/null; then
        echo "Attempting to create writable copy in /tmp"
        rm -f /app/bssci_config.py
        ln -sf /tmp/bssci_config.py /app/bssci_config.py
    fi
fi

if [ -w "/app/endpoints.json" ]; then
    echo "✓ endpoints.json is writable"
else
    echo "✗ endpoints.json is NOT writable"
    # Try to copy to a writable location and symlink back
    if cp /app/endpoints.json /tmp/endpoints.json 2>/dev/null; then
        echo "Attempting to create writable copy in /tmp"
        rm -f /app/endpoints.json
        ln -sf /tmp/endpoints.json /app/endpoints.json
    fi
fi

echo "=== File System Permissions After Changes ==="
ls -la /app/bssci_config.py /app/endpoints.json /app/logs 2>/dev/null || echo "Some files not accessible"

echo "=== Mount information ==="
mount | grep "/app" || echo "No /app mounts found"

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
