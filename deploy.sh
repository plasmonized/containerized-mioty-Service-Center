
#!/bin/bash

# BSSCI Service Center Deployment Script for NAS

echo "Setting up BSSCI Service Center for Docker deployment..."

# Create data directory with proper permissions
echo "Creating data directory..."
mkdir -p ./data
chmod 755 ./data

# Copy existing endpoints.json to data directory if it exists
if [ -f "endpoints.json" ]; then
    echo "Copying existing endpoints.json to data directory..."
    cp endpoints.json ./data/endpoints.json
    chmod 644 ./data/endpoints.json
else
    echo "Creating empty endpoints.json..."
    echo "[]" > ./data/endpoints.json
    chmod 644 ./data/endpoints.json
fi

# Stop existing container if running
echo "Stopping existing container..."
docker-compose down 2>/dev/null || true

# Build and start the container
echo "Building and starting container..."
docker-compose up -d --build

# Wait a moment for container to start
sleep 5

# Check if container is running
if docker-compose ps | grep -q "Up"; then
    echo "✅ BSSCI Service Center deployed successfully!"
    echo "📋 Checking logs..."
    docker-compose logs --tail=10
    echo ""
    echo "🔍 To monitor logs: docker-compose logs -f"
    echo "🛑 To stop: docker-compose down"
else
    echo "❌ Deployment failed. Check logs:"
    docker-compose logs
fi
