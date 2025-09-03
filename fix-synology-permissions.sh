
#!/bin/bash

echo "=== BSSCI Synology Permission Fix Script ==="

# Get the current directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Working directory: $SCRIPT_DIR"

# Check if we're on Synology
if [ -f "/etc/synoinfo.conf" ]; then
    echo "✓ Synology NAS detected"
else
    echo "⚠ This script is designed for Synology NAS"
fi

# Stop any running containers
echo "Stopping existing containers..."
docker-compose -f docker-compose.synology.yml down 2>/dev/null || true

# Fix file permissions on the host
echo "=== Fixing host file permissions ==="

# Make sure files exist
touch "$SCRIPT_DIR/endpoints.json"
touch "$SCRIPT_DIR/bssci_config.py"

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/certs"

# Set appropriate permissions for Synology
echo "Setting file permissions for Synology..."
chmod 644 "$SCRIPT_DIR/endpoints.json"
chmod 644 "$SCRIPT_DIR/bssci_config.py"
chmod 755 "$SCRIPT_DIR/logs"
chmod 755 "$SCRIPT_DIR/certs"

# Set ownership to current user
USER_ID=$(id -u)
GROUP_ID=$(id -g)
echo "Setting ownership to $USER_ID:$GROUP_ID"

chown $USER_ID:$GROUP_ID "$SCRIPT_DIR/endpoints.json"
chown $USER_ID:$GROUP_ID "$SCRIPT_DIR/bssci_config.py"
chown -R $USER_ID:$GROUP_ID "$SCRIPT_DIR/logs"
chown -R $USER_ID:$GROUP_ID "$SCRIPT_DIR/certs"

# Show current permissions
echo "=== Current file permissions ==="
ls -la "$SCRIPT_DIR/endpoints.json"
ls -la "$SCRIPT_DIR/bssci_config.py"
ls -la "$SCRIPT_DIR/logs"

echo "=== Synology Setup Notes ==="
echo "1. Configuration files will be copied to writable container locations"
echo "2. Changes made via web UI are container-local only"
echo "3. To persist config changes, manually backup:"
echo "   docker cp bssci-service-center:/app/bssci_config.py ./bssci_config.py"
echo "   docker cp bssci-service-center:/app/endpoints.json ./endpoints.json"
echo ""
echo "4. If you get permission errors:"
echo "   sudo chown -R 1000:1000 ."
echo "   chmod 755 logs certs"
echo "   chmod 644 *.py *.json"
echo ""
echo "=== Starting container with Synology configuration ==="
docker-compose -f docker-compose.synology.yml up --build -d

echo "=== Container started ==="
echo "Web UI: http://localhost:5056"
echo "TLS Server: localhost:16019"
