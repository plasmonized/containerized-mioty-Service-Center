#!/bin/bash
set -e

echo "🐳 BSSCI Synology Docker Container with Git Support"
echo "=================================================="

# Synology Docker specific setup
if [ "$SYNOLOGY_DOCKER" = "1" ]; then
    echo "🔧 Synology Docker mode detected"
    
    # Get target user IDs (Synology typically uses 1000:1000)
    TARGET_UID=${PUID:-1000}
    TARGET_GID=${PGID:-1000}
    
    echo "Target user: UID=$TARGET_UID, GID=$TARGET_GID"
    
    # Create user and group if they don't exist
    if ! getent group $TARGET_GID >/dev/null 2>&1; then
        groupadd -g $TARGET_GID bssci
    fi
    
    if ! getent passwd $TARGET_UID >/dev/null 2>&1; then
        useradd -u $TARGET_UID -g $TARGET_GID -s /bin/bash -d /app bssci
    fi
    
    # Create and set permissions on necessary directories
    mkdir -p /app/logs /app/certs
    
    # GIT CONFIGURATION SETUP FOR SYNOLOGY
    echo "🔧 Setting up Git configuration for Synology..."
    
    # Create global Git configuration
    cat > /app/.gitconfig << EOF
[user]
    name = ${GIT_AUTHOR_NAME:-BSSCI Service}
    email = ${GIT_AUTHOR_EMAIL:-bssci@synology.local}

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
    trustctime = false

[credential]
    helper = store
EOF
    
    # Set Git configuration file permissions
    chmod 644 /app/.gitconfig
    chown $TARGET_UID:$TARGET_GID /app/.gitconfig
    
    # Handle repository permissions if mounted
    if [ -d "/app/repo/.git" ]; then
        echo "📁 Git repository detected - fixing Synology permissions..."
        
        # Remove any lock files
        rm -f /app/repo/.git/index.lock 2>/dev/null || true
        rm -f /app/repo/.git/refs/heads/*.lock 2>/dev/null || true
        rm -f /app/repo/.git/refs/remotes/origin/*.lock 2>/dev/null || true
        
        # Set proper ownership for Git repository
        chown -R $TARGET_UID:$TARGET_GID /app/repo/.git 2>/dev/null || true
        
        # Ensure Git directories are accessible
        find /app/repo/.git -type d -exec chmod 755 {} \; 2>/dev/null || true
        find /app/repo/.git -type f -exec chmod 644 {} \; 2>/dev/null || true
        
        # Make Git hooks executable
        find /app/repo/.git/hooks -type f -exec chmod +x {} \; 2>/dev/null || true
        
        echo "✅ Git repository permissions fixed for Synology"
    fi
    
    # Copy config files from host mounts to writable container locations
    echo "📋 Copying configuration files..."
    
    if [ -f "/tmp/host_bssci_config.py" ]; then
        cp /tmp/host_bssci_config.py /app/bssci_config.py
        chown $TARGET_UID:$TARGET_GID /app/bssci_config.py
        chmod 644 /app/bssci_config.py
        echo "✅ Copied bssci_config.py to writable location"
    fi
    
    if [ -f "/tmp/host_endpoints.json" ]; then
        cp /tmp/host_endpoints.json /app/endpoints.json
        chown $TARGET_UID:$TARGET_GID /app/endpoints.json
        chmod 644 /app/endpoints.json
        echo "✅ Copied endpoints.json to writable location"
    fi
    
    if [ -f "/tmp/host_.env" ]; then
        cp /tmp/host_.env /app/.env
        chown $TARGET_UID:$TARGET_GID /app/.env
        chmod 644 /app/.env
        echo "✅ Copied .env to writable location"
    else
        # Ensure .env exists
        touch /app/.env
        chown $TARGET_UID:$TARGET_GID /app/.env
        chmod 666 /app/.env
    fi
    
    # Set proper ownership on all app files
    chown -R $TARGET_UID:$TARGET_GID /app/logs /app/certs
    chmod 755 /app/logs /app/certs
    
    echo "✅ Synology setup complete - config files are now writable with Git support"
    
    # Test Git operations as target user
    if [ -d "/app/repo/.git" ]; then
        echo "🧪 Testing Git operations..."
        su -s /bin/bash bssci -c "cd /app/repo && git config --global --add safe.directory /app/repo && git status >/dev/null 2>&1" && echo "✅ Git operations working" || echo "⚠️ Git operations may need attention"
    fi
    
else
    echo "🔧 Standard Docker mode (non-Synology)"
    TARGET_UID=$(id -u)
    TARGET_GID=$(id -g)
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
    
    # Set proper ownership
    chown $TARGET_UID:$TARGET_GID /app/certs/*
    
    echo "✅ SSL certificates generated successfully"
fi

echo "🚀 Starting BSSCI Service Center with Synology Git support..."

# For Synology, switch to target user before starting the application
if [ "$SYNOLOGY_DOCKER" = "1" ]; then
    exec su -s /bin/bash bssci -c "cd /app && $*"
else
    exec "$@"
fi