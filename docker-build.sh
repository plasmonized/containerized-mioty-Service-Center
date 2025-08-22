
#!/bin/bash

echo "Building BSSCI Service Center Docker image..."

# Build the Docker image
docker build -t bssci-service-center:latest .

echo "Build complete!"
echo ""
echo "To run the container:"
echo "  docker-compose up -d"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
echo ""
echo "Access points:"
echo "  Web GUI: http://localhost:5055"
echo "  TLS Server: localhost:16019"
