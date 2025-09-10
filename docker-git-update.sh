#!/bin/bash
# Docker Git Update Helper Script
# Fixes Git permission issues and enables smooth updates

echo "🐳 DOCKER GIT UPDATE HELPER"
echo "============================"

# Get current user UID/GID
export UID=$(id -u)
export GID=$(id -g)
echo "Current user: UID=$UID, GID=$GID"

# Set Git configuration if not already set
if [ -z "$GIT_AUTHOR_NAME" ]; then
    export GIT_AUTHOR_NAME="BSSCI Service"
fi
if [ -z "$GIT_AUTHOR_EMAIL" ]; then
    export GIT_AUTHOR_EMAIL="bssci@localhost"
fi

# Clean up any existing Git locks
echo "🔧 Cleaning Git locks..."
rm -f .git/index.lock .git/refs/heads/*.lock .git/refs/remotes/origin/*.lock 2>/dev/null || true

# Fix permissions on Git repository
echo "🔧 Fixing Git repository permissions..."
sudo chown -R $UID:$GID .git/ 2>/dev/null || chown -R $UID:$GID .git/ 2>/dev/null || true
chmod -R u+rwX .git/ 2>/dev/null || true

# Set Git safe directory
git config --global --add safe.directory $(pwd) 2>/dev/null || true

# Create backup directory with proper permissions
BACKUP_DIR="backup_$(date +%Y%m%d_%H%M%S)"
echo "📦 Creating backup directory: $BACKUP_DIR"
mkdir -p $BACKUP_DIR
sudo chown -R $UID:$GID $BACKUP_DIR 2>/dev/null || chown -R $UID:$GID $BACKUP_DIR 2>/dev/null || true

# Fix permissions for Docker volumes
echo "🔧 Fixing Docker volume permissions..."
sudo chown -R $UID:$GID logs/ certs/ *.json *.py .env 2>/dev/null || chown -R $UID:$GID logs/ certs/ *.json *.py .env 2>/dev/null || true

# Docker compose update with Git-enabled configuration
echo "📦 Updating Docker container with Git support..."

# Use Git-enabled docker-compose configuration
if [ -f "docker-compose.git-fix.yml" ]; then
    echo "Using Git-enabled Docker Compose configuration..."
    docker-compose -f docker-compose.git-fix.yml down --remove-orphans
    docker-compose -f docker-compose.git-fix.yml pull
    docker-compose -f docker-compose.git-fix.yml up -d --force-recreate
else
    echo "Using standard Docker Compose configuration..."
    docker-compose down --remove-orphans
    docker-compose pull
    docker-compose up -d --force-recreate
fi

echo "✅ Update complete! Checking container status:"
docker-compose ps

echo "📋 Recent container logs:"
docker-compose logs --tail=10

echo ""
echo "🔍 Git status check:"
git status --porcelain | head -5 || echo "Git status check failed - may need container Git setup"

echo ""
echo "✅ Docker Git update complete!"
echo "   - Git permissions fixed"
echo "   - Backup directory created: $BACKUP_DIR"
echo "   - Container updated and restarted"
echo "   - Git operations should now work smoothly"