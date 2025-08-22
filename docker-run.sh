
#!/bin/bash

echo "Starting BSSCI Service Center..."

# Check if certificates exist
if [ ! -d "./certs" ] || [ ! -f "./certs/service_center_cert.pem" ]; then
    echo "Warning: SSL certificates not found in ./certs/"
    echo "Please ensure you have the required certificates:"
    echo "  - certs/service_center_cert.pem"
    echo "  - certs/service_center_key.pem" 
    echo "  - certs/ca_cert.pem"
    echo ""
fi

# Start with docker-compose
docker-compose up -d

echo "Container started!"
echo ""
echo "Access points:"
echo "  Web GUI: http://localhost:5001"
echo "  TLS Server: localhost:16019"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"
echo ""
echo "To stop:"
echo "  docker-compose down"
