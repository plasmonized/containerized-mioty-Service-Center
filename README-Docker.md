
# Docker Deployment Guide

## Quick Start

### Development
```bash
docker-compose up --build
```

### Production
```bash
docker-compose -f docker-compose.prod.yml up --build -d
```

## Services

- **TLS Server**: Port 16018 (for mioty base stations)
- **Synchronous BSSCI Service**: Uses threading instead of asyncio

## Required Files

Before starting, ensure you have:

1. **Certificates** in `./certs/` directory:
   - `service_center_cert.pem`
   - `service_center_key.pem` 
   - `ca_cert.pem`

2. **Configuration** in `bssci_config.py`:
   - MQTT broker settings
   - Server listen settings

3. **Sensor Configuration** in `endpoints.json`:
   - Endpoint definitions

## Environment Variables

- `RUN_MODE=service-only`: Run the synchronous BSSCI service
- `PYTHONUNBUFFERED=1`: Enable real-time logging

## Volumes

- `./certs:/app/certs:ro` - SSL certificates (read-only)
- `./endpoints.json:/app/endpoints.json` - Sensor configuration
- `./bssci_config.py:/app/bssci_config.py` - Application configuration
- `./logs:/app/logs` - Log files

## Health Checks

The container includes health checks for:
- TLS Server on port 16018

## Accessing the Services

### Development
- TLS Server: localhost:16019 (mapped from 16018)

### Production  
- TLS Server: localhost:16018

## Logs

- Container logs: `docker-compose logs -f`
- Application logs: `./logs/bssci.log`

## Commands

```bash
# Build only
docker-compose build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Restart services
docker-compose restart
```
