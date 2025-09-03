# BSSCI Service Center

## Overview

The BSSCI Service Center is a comprehensive IoT device management system that provides secure communication between mioty sensors, base stations, and MQTT brokers. It implements the BSSCI (Base Station Service Center Interface) protocol for managing sensor attachments, data collection, and system monitoring. The system serves as a central hub that enables secure TLS communication with base stations while providing bidirectional MQTT integration for external systems.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Components

The system follows a multi-layered architecture with clear separation of concerns:

**TLS Server Layer**: Implements the BSSCI protocol for secure communication with mioty base stations using TLS encryption. Handles base station connections, sensor attachment/detachment requests, and real-time data collection.

**MQTT Interface Layer**: Provides bidirectional communication with external systems through MQTT topics. Publishes sensor data and base station status while subscribing to configuration updates and commands.

**Web Interface Layer**: Flask-based web application offering real-time management and monitoring capabilities. Provides dashboards for system status, sensor management, configuration, and log viewing.

**Message Processing**: Implements MessagePack-based protocol encoding/decoding with message deduplication capabilities to handle duplicate sensor data from multiple base stations.

### Data Flow Architecture

The system uses asynchronous queue-based communication between components:
- MQTT output queue for publishing sensor data and status updates
- MQTT input queue for receiving configuration changes and commands
- Real-time message processing with deduplication buffers
- Auto-detach system for sensor lifecycle management

### Certificate Management

SSL/TLS infrastructure using CA-signed certificates for secure base station authentication. The system supports certificate generation, validation, and management through the web interface.

### Configuration Management

Environment-based configuration system supporting:
- TLS server settings (host, port, certificates)
- MQTT broker configuration (host, port, authentication)
- Sensor configuration file management
- Auto-detach timeouts and intervals
- Message deduplication parameters

### Sensor Management

JSON-based sensor configuration with support for:
- EUI-based sensor identification
- Network key management
- Short address allocation
- Bidirectional communication flags
- Dynamic attach/detach operations

## External Dependencies

**MQTT Broker**: External MQTT broker for data publishing and configuration management. Supports standard MQTT authentication and configurable topic structures.

**MessagePack**: Binary serialization format for efficient BSSCI protocol communication.

**Flask Web Framework**: Python web framework for the management interface with Bootstrap UI components.

**SSL/TLS Certificates**: CA-signed certificates for secure base station communication.

**Docker Support**: Containerized deployment with Docker Compose for both development and production environments.

**Environment Configuration**: dotenv support for configuration management with fallback defaults.

**Logging Infrastructure**: Structured logging with timezone support and multiple output targets.