
#!/bin/bash
set -e

# Ensure proper permissions on log directory
mkdir -p /app/logs
chmod 755 /app/logs

# Ensure certificates directory exists
mkdir -p /app/certs

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
