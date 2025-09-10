#!/bin/bash
set -e

echo "🐳 BSSCI Docker Container with Git Support"
echo "=========================================="

# Get current user info
CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)
echo "Running as UID:GID = $CURRENT_UID:$CURRENT_GID"

# Ensure proper permissions on log directory
mkdir -p /app/logs
chmod 755 /app/logs

# Ensure certificates directory exists
mkdir -p /app/certs

# GIT CONFIGURATION SETUP
echo "🔧 Setting up Git configuration..."

# Create global Git configuration
cat > /app/.gitconfig << EOF
[user]
    name = ${GIT_AUTHOR_NAME:-BSSCI Service}
    email = ${GIT_AUTHOR_EMAIL:-bssci@localhost}

[safe]
    directory = /app/repo
    directory = /app
    directory = *

[init]
    defaultBranch = main

[pull]
    rebase = false

[core]
    filemode = false
    autocrlf = false
EOF

# Set Git configuration file permissions
chmod 644 /app/.gitconfig
chown $CURRENT_UID:$CURRENT_GID /app/.gitconfig 2>/dev/null || true

# Configure Git safe directories globally
git config --global --add safe.directory /app/repo 2>/dev/null || true
git config --global --add safe.directory /app 2>/dev/null || true
git config --global --add safe.directory '*' 2>/dev/null || true

# Set Git user configuration
git config --global user.name "${GIT_AUTHOR_NAME:-BSSCI Service}" 2>/dev/null || true
git config --global user.email "${GIT_AUTHOR_EMAIL:-bssci@localhost}" 2>/dev/null || true

# Handle repository permissions if mounted
if [ -d "/app/repo/.git" ]; then
    echo "📁 Git repository detected - fixing permissions..."
    
    # Remove any lock files
    rm -f /app/repo/.git/index.lock 2>/dev/null || true
    rm -f /app/repo/.git/refs/heads/*.lock 2>/dev/null || true
    rm -f /app/repo/.git/refs/remotes/origin/*.lock 2>/dev/null || true
    
    # Set proper ownership for Git repository
    chown -R $CURRENT_UID:$CURRENT_GID /app/repo/.git 2>/dev/null || true
    
    # Ensure Git directories are accessible
    find /app/repo/.git -type d -exec chmod 755 {} \; 2>/dev/null || true
    find /app/repo/.git -type f -exec chmod 644 {} \; 2>/dev/null || true
    
    # Make Git hooks executable
    find /app/repo/.git/hooks -type f -exec chmod +x {} \; 2>/dev/null || true
    
    echo "✅ Git repository permissions fixed"
    
    # Test Git operations
    cd /app/repo
    if git status >/dev/null 2>&1; then
        echo "✅ Git operations working correctly"
    else
        echo "⚠️  Git operations may have issues - continuing anyway"
    fi
    cd /app
fi

# Handle Synology Docker setup
if [ "$SYNOLOGY_DOCKER" = "1" ]; then
    echo "🔧 Synology Docker mode detected - copying config files to writable locations"
    
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
    chown $CURRENT_UID:$CURRENT_GID /app/bssci_config.py /app/endpoints.json /app/.env 2>/dev/null || true
    
    echo "✅ Synology setup complete - config files are now writable"
else
    # Standard Docker setup - fix permissions for configuration files at runtime
    touch /app/.env 2>/dev/null || true
    chmod 644 /app/bssci_config.py /app/endpoints.json 2>/dev/null || true
    chmod 666 /app/.env 2>/dev/null || true
    chown $CURRENT_UID:$CURRENT_GID /app/bssci_config.py /app/endpoints.json /app/.env 2>/dev/null || true
fi

# Generate self-signed certificates if they don't exist
if [ ! -f "/app/certs/ca_cert.pem" ] || [ ! -f "/app/certs/service_center_cert.pem" ] || [ ! -f "/app/certs/service_center_key.pem" ]; then
    echo "🔐 Generating SSL certificates..."
    
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
    
    echo "✅ SSL certificates generated successfully"
fi

echo "🚀 Starting BSSCI Service Center with Git support..."

# Execute the main command
exec "$@"