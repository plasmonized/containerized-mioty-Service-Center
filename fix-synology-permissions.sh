
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

# Set liberal permissions for testing
echo "Setting file permissions..."
chmod 666 "$SCRIPT_DIR/endpoints.json"
chmod 666 "$SCRIPT_DIR/bssci_config.py"
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

# Test writability
echo "=== Testing file writability ==="
if echo "test" >> "$SCRIPT_DIR/endpoints.json"; then
    echo "✓ endpoints.json is writable"
    # Remove test line
    sed -i '$d' "$SCRIPT_DIR/endpoints.json"
else
    echo "✗ endpoints.json is NOT writable"
fi

if echo "# test" >> "$SCRIPT_DIR/bssci_config.py"; then
    echo "✓ bssci_config.py is writable"
    # Remove test line
    sed -i '$d' "$SCRIPT_DIR/bssci_config.py"
else
    echo "✗ bssci_config.py is NOT writable"
fi

echo "=== Permission fix complete ==="
echo "You can now run: docker-compose -f docker-compose.synology.yml up --build"
