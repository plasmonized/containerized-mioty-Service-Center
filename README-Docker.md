
# BSSCI Service Center - Docker Deployment

This guide explains how to deploy the BSSCI Service Center using Docker and Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+

## Quick Start

### Development Deployment

```bash
# Build and start the service
docker-compose up --build

# Run in background
docker-compose up -d --build
```

The service will be available at:
- Web UI: http://localhost:5056
- TLS Server: localhost:16019

### Production Deployment

```bash
# Use production configuration
docker-compose -f docker-compose.prod.yml up -d --build
```

The service will be available at:
- Web UI: http://localhost:5000
- TLS Server: localhost:16018

## Configuration

### Environment Variables

Set these in your environment or `.env` file:

```bash
UID=1000          # User ID for file permissions
GID=1000          # Group ID for file permissions
```

### Volumes

The following directories are mounted as volumes:

- `./certs` - SSL certificates (read-only)
- `./endpoints.json` - Sensor configuration
- `./bssci_config.py` - Service configuration
- `./logs` - Application logs

### Certificates

The container will automatically generate self-signed SSL certificates if none are provided in the `./certs` directory.

For production, provide your own certificates:

```bash
certs/
├── ca_cert.pem
├── service_center_cert.pem
└── service_center_key.pem
```

## Management Commands

```bash
# View logs
docker-compose logs -f

# Stop service
docker-compose down

# Restart service
docker-compose restart

# Update and restart
docker-compose pull && docker-compose up -d

# Remove everything (including volumes)
docker-compose down -v
```

## Health Check

The container includes a health check that verifies both the TLS server (port 16018) and Web UI (port 5000) are responding.

Check health status:
```bash
docker-compose ps
```

## Troubleshooting

### Permission Issues

If you encounter permission issues with logs or certificates:

```bash
# Set correct ownership
sudo chown -R $USER:$USER certs/ logs/

# Or run with specific user
UID=$(id -u) GID=$(id -g) docker-compose up
```

### Certificate Issues

Regenerate certificates:

```bash
# Remove old certificates
rm -rf certs/*

# Restart container (will auto-generate)
docker-compose restart
```

### Port Conflicts

If ports are already in use, modify the port mappings in `docker-compose.yml`:

```yaml
ports:
  - "16020:16018"  # Change external port
  - "5057:5000"    # Change external port
```

## Security Notes

- Change default MQTT credentials in `bssci_config.py`
- Use proper SSL certificates for production
- Restrict network access to required ports only
- Regular security updates of base images
