#!/bin/bash
# Synology Docker Update Script
# Fixes permission issues during backup/update

echo "🔧 SYNOLOGY DOCKER UPDATE HELPER"
echo "================================="

# Set correct permissions for backup directory
sudo mkdir -p backup_$(date +%Y%m%d_%H%M%S) 2>/dev/null || mkdir -p backup_$(date +%Y%m%d_%H%M%S)
sudo chown -R 1000:1000 backup_* 2>/dev/null || chown -R 1000:1000 backup_* 2>/dev/null || true

# Set correct permissions for Docker volumes
sudo chown -R 1000:1000 logs/ certs/ *.json *.py .env 2>/dev/null || chown -R 1000:1000 logs/ certs/ *.json *.py .env 2>/dev/null || true

# Docker compose update with proper permissions
echo "📦 Updating Docker container..."
docker-compose down --remove-orphans
docker-compose pull
docker-compose up -d --force-recreate

echo "✅ Update complete! Check container status:"
docker-compose ps
docker-compose logs --tail=10