import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from typing import List, Dict, Any
import bssci_config

# Global TLS server instance reference
tls_server_instance = None

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors and return JSON"""
    app.logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'running': False,
        'service_type': 'web_ui',
        'tls_server': {'active': False},
        'mqtt_broker': {'active': False},
        'base_stations': {'total_connected': 0, 'total_connecting': 0, 'connected': [], 'connecting': []}
    }), 500

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors for API endpoints"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    return error

# Global variables for log storage and configuration
log_entries: List[Dict[str, Any]] = []
max_log_entries = 1000

# Custom log handler to capture all logs with timezone support
class WebUILogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        # Set timezone to UTC+2 (Central European Time)
        self.timezone = timezone(timedelta(hours=2))

    def emit(self, record):
        global log_entries

        # Filter out noisy web request logs to reduce clutter
        if record.name == 'werkzeug' and any(x in record.getMessage() for x in [
            'GET /api/', 'GET /logs', 'GET /sensors', 'GET /config', 'GET /', 'GET /static/'
        ]):
            return  # Skip web request logs

        # Convert UTC timestamp to local timezone
        utc_time = datetime.fromtimestamp(record.created, tz=timezone.utc)
        local_time = utc_time.astimezone(self.timezone)
        current_time = local_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        message = record.getMessage()

        # Check if this exact message was logged in the last second (duplicate detection)
        if log_entries:
            last_entry = log_entries[-1]
            try:
                last_time = datetime.strptime(last_entry['timestamp'], '%Y-%m-%d %H:%M:%S.%f')
                time_diff = abs((local_time.replace(tzinfo=None) - last_time).total_seconds())

                if (time_diff < 1.0 and  # Within 1 second
                    last_entry['message'] == message and
                    last_entry['logger'] == record.name):
                    return  # Skip duplicate message
            except:
                pass  # If timestamp parsing fails, continue with logging

        log_entry = {
            'timestamp': current_time,
            'level': record.levelname,
            'logger': record.name,
            'message': message,
            'source': 'memory'
        }
        log_entries.append(log_entry)

        # Keep only the last max_log_entries
        if len(log_entries) > max_log_entries:
            log_entries = log_entries[-max_log_entries:]

# Add our custom handler to the root logger (only once)
if not any(isinstance(h, WebUILogHandler) for h in logging.getLogger().handlers):
    web_handler = WebUILogHandler()
    logging.getLogger().addHandler(web_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    # Specifically capture important logs
    logging.getLogger('TLSServer').setLevel(logging.DEBUG)
    logging.getLogger('mqtt_interface').setLevel(logging.DEBUG)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/sensors')
def sensors():
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
        sensors = []
    return render_template('sensors.html', sensors=sensors)

@app.route('/api/sensors', methods=['GET'])
def get_sensors():
    try:
        global tls_server_instance
        tls_server = tls_server_instance
        
        if tls_server and hasattr(tls_server, 'get_sensor_registration_status'):
            try:
                # Get sensor registration status from TLS server
                sensor_status = tls_server.get_sensor_registration_status()
                
                # Fix registration status - if sensor has received data, it should be marked as registered
                for eui, sensor_data in sensor_status.items():
                    # If sensor has preferred downlink path or has been seen recently, mark as registered
                    if (sensor_data.get('preferredDownlinkPath') or 
                        sensor_data.get('last_seen_timestamp', 0) > 0):
                        sensor_data['registered'] = True
                        if not sensor_data.get('base_stations'):
                            # If no base stations recorded but data received, add from preferred path
                            if sensor_data.get('preferredDownlinkPath', {}).get('baseStation'):
                                sensor_data['base_stations'] = [sensor_data['preferredDownlinkPath']['baseStation']]
                                sensor_data['total_registrations'] = 1
                    
                    # Calculate proper activity status
                    current_time = time.time()
                    last_seen = sensor_data.get('last_seen_timestamp', 0)
                    
                    if last_seen > 0:
                        hours_since_last_seen = (current_time - last_seen) / 3600
                        sensor_data['hours_since_last_seen'] = hours_since_last_seen
                        
                        # Set activity status based on actual thresholds
                        warning_threshold = getattr(bssci_config, 'AUTO_DETACH_WARNING_TIMEOUT', 129600) / 3600  # Convert to hours
                        detach_threshold = getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200) / 3600  # Convert to hours
                        
                        if hours_since_last_seen >= detach_threshold:
                            sensor_data['activity_status'] = 'auto_detach_pending'
                        elif hours_since_last_seen >= warning_threshold:
                            sensor_data['activity_status'] = 'warning'
                            sensor_data['warning_info'] = {
                                'hours_inactive': hours_since_last_seen,
                                'hours_until_detach': max(0, detach_threshold - hours_since_last_seen),
                                'warning_sent': sensor_data.get('warning_sent', False)
                            }
                        else:
                            sensor_data['activity_status'] = 'active'
                    else:
                        sensor_data['activity_status'] = 'no_data'
                        sensor_data['hours_since_last_seen'] = 0
                
                return jsonify(sensor_status)
            except Exception as e:
                print(f"Error getting sensor status from TLS server: {e}")
        
        # Fallback to file only
        try:
            sensor_file = getattr(bssci_config, 'SENSOR_CONFIG_FILE', 'endpoints.json')
            print(f"Loading sensors from file: {sensor_file}")
            with open(sensor_file, 'r') as f:
                sensors = json.load(f)
                print(f"Loaded {len(sensors)} sensors from file")
                sensor_status = {}
                for sensor in sensors:
                    eui = sensor['eui'].lower()
                    sensor_status[eui] = {
                        'eui': sensor['eui'],
                        'nwKey': sensor['nwKey'],
                        'shortAddr': sensor['shortAddr'],
                        'bidi': sensor['bidi'],
                        'registered': False,
                        'registration_info': {},
                        'base_stations': [],
                        'total_registrations': 0,
                        'preferredDownlinkPath': sensor.get('preferredDownlinkPath', None),
                        'activity_status': 'no_data',
                        'hours_since_last_seen': 0
                    }
                print(f"Processed sensor status for {len(sensor_status)} sensors")
                return jsonify(sensor_status)
        except FileNotFoundError:
            sensor_file = getattr(bssci_config, 'SENSOR_CONFIG_FILE', 'endpoints.json')
            print(f"Sensor config file not found: {sensor_file}")
            return jsonify({})
        except json.JSONDecodeError as e:
            sensor_file = getattr(bssci_config, 'SENSOR_CONFIG_FILE', 'endpoints.json')
            print(f"Invalid JSON in sensor config file {sensor_file}: {e}")
            return jsonify({})
            
    except Exception as e:
        print(f"Error in get_sensors: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors', methods=['POST'])
def add_sensor():
    data = request.json
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
        sensors = []

    # Check if sensor already exists
    for sensor in sensors:
        if sensor['eui'].lower() == data['eui'].lower():
            # Update existing sensor
            sensor.update(data)
            break
    else:
        # Add new sensor
        sensors.append(data)

    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        return jsonify({'success': True, 'message': 'Sensor saved successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/<eui>', methods=['DELETE'])
def delete_sensor(eui):
    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
    except:
        sensors = []

    sensors = [s for s in sensors if s['eui'].lower() != eui.lower()]

    try:
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump(sensors, f, indent=4)
        return jsonify({'success': True, 'message': 'Sensor deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/<eui>/detach', methods=['POST'])
def detach_sensor(eui):
    """Detach a specific sensor from all base stations"""
    try:
        global tls_server_instance
        tls_server = tls_server_instance
        if tls_server and hasattr(tls_server, 'detach_sensor_sync'):
            success = tls_server.detach_sensor_sync(eui)
            return jsonify({'success': success, 'message': f'Sensor {eui} {"detached" if success else "detach failed"}'})
        else:
            return jsonify({'success': False, 'message': 'TLS server not available'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/attach-all', methods=['POST'])
def attach_all_sensors():
    """Attach all configured sensors to base stations"""
    try:
        global tls_server_instance
        tls_server = tls_server_instance
        
        if not tls_server:
            return jsonify({'success': False, 'message': 'TLS server not available'})
        
        # Get all sensors from config file
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
                sensors = json.load(f)
        except:
            sensors = []
        
        if not sensors:
            return jsonify({'success': False, 'message': 'No sensors configured to attach'})
        
        # Force reload sensor config to ensure all sensors are loaded
        tls_server.reload_sensor_config()
        
        attached_count = len(sensors)
        message = f'All sensors ready for attachment. {attached_count} sensors loaded and will be attached when base stations register them.'
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/detach-all', methods=['POST'])
def detach_all_sensors():
    """Detach all sensors from base stations"""
    try:
        global tls_server_instance
        tls_server = tls_server_instance
        
        if not tls_server:
            return jsonify({'success': False, 'message': 'TLS server not available'})
        
        if hasattr(tls_server, 'detach_all_sensors_sync'):
            detached_count = tls_server.detach_all_sensors_sync()
            message = f'Successfully detached {detached_count} sensors from all base stations.'
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'message': 'Detach all function not available'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/clear', methods=['POST'])
def clear_all_sensors():
    """Clear all sensor configurations and detach all sensors"""
    try:
        detached_count = 0

        # First detach all sensors from base stations
        global tls_server_instance
        tls_server = tls_server_instance
        if tls_server and hasattr(tls_server, 'detach_all_sensors_sync'):
            detached_count = tls_server.detach_all_sensors_sync()

        # Clear the file
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump([], f, indent=4)

        # Also clear from TLS server if available
        if tls_server and hasattr(tls_server, 'clear_all_sensors'):
            tls_server.clear_all_sensors()

        message = f'All sensors cleared successfully. Detached {detached_count} sensors from base stations.'
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/reload', methods=['POST'])
def reload_sensors():
    """Force reload sensor configuration in TLS server"""
    try:
        global tls_server_instance
        tls_server = tls_server_instance
        if tls_server:
            tls_server.reload_sensor_config()
            return jsonify({'success': True, 'message': 'Sensor configuration reloaded successfully'})
        else:
            return jsonify({'success': False, 'message': 'TLS server not available'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/config')
def config():
    try:
        # Force reload the config module to get latest values
        import importlib
        import sys
        if 'bssci_config' in sys.modules:
            importlib.reload(sys.modules['bssci_config'])
        
        import bssci_config
        
        config_data = {
            'LISTEN_HOST': getattr(bssci_config, 'LISTEN_HOST', '0.0.0.0'),
            'LISTEN_PORT': getattr(bssci_config, 'LISTEN_PORT', 16018),
            'MQTT_BROKER': getattr(bssci_config, 'MQTT_BROKER', 'localhost'),
            'MQTT_PORT': getattr(bssci_config, 'MQTT_PORT', 1883),
            'MQTT_USERNAME': getattr(bssci_config, 'MQTT_USERNAME', ''),
            'MQTT_PASSWORD': getattr(bssci_config, 'MQTT_PASSWORD', ''),
            'BASE_TOPIC': getattr(bssci_config, 'BASE_TOPIC', 'bssci/'),
            'STATUS_INTERVAL': getattr(bssci_config, 'STATUS_INTERVAL', 30),
            'DEDUPLICATION_DELAY': getattr(bssci_config, 'DEDUPLICATION_DELAY', 2.0),
            'AUTO_DETACH_ENABLED': getattr(bssci_config, 'AUTO_DETACH_ENABLED', True),
            'AUTO_DETACH_TIMEOUT': getattr(bssci_config, 'AUTO_DETACH_TIMEOUT', 259200),
            'AUTO_DETACH_WARNING_TIMEOUT': getattr(bssci_config, 'AUTO_DETACH_WARNING_TIMEOUT', 129600),
            'AUTO_DETACH_CHECK_INTERVAL': getattr(bssci_config, 'AUTO_DETACH_CHECK_INTERVAL', 3600)
        }
        return render_template('config.html', config=config_data)
    except Exception as e:
        logger.error(f"Error loading config page: {e}")
        # Return default config if there's an error
        default_config = {
            'LISTEN_HOST': '0.0.0.0',
            'LISTEN_PORT': 16018,
            'MQTT_BROKER': 'localhost',
            'MQTT_PORT': 1883,
            'MQTT_USERNAME': '',
            'MQTT_PASSWORD': '',
            'BASE_TOPIC': 'bssci/',
            'STATUS_INTERVAL': 30,
            'DEDUPLICATION_DELAY': 2.0,
            'AUTO_DETACH_ENABLED': True,
            'AUTO_DETACH_TIMEOUT': 259200,
            'AUTO_DETACH_WARNING_TIMEOUT': 129600,
            'AUTO_DETACH_CHECK_INTERVAL': 3600
        }
        return render_template('config.html', config=default_config)

@app.route('/api/config', methods=['POST'])
def update_config():
    try:
        data = request.json
        
        # Convert hours to seconds for timeout values
        auto_detach_timeout = int(data.get('AUTO_DETACH_TIMEOUT', 72)) * 3600
        auto_detach_warning_timeout = int(data.get('AUTO_DETACH_WARNING_TIMEOUT', 36)) * 3600
        auto_detach_check_interval = int(data.get('AUTO_DETACH_CHECK_INTERVAL', 1)) * 3600
        
        # Update the .env file - this is the primary configuration source
        env_content = f"""# TLS Server Configuration
LISTEN_HOST={data['LISTEN_HOST']}
LISTEN_PORT={data['LISTEN_PORT']}

# SSL/TLS Certificate Configuration
CERT_FILE=certs/service_center_cert.pem
KEY_FILE=certs/service_center_key.pem
CA_FILE=certs/ca_cert.pem

# MQTT Configuration
MQTT_BROKER={data['MQTT_BROKER']}
MQTT_PORT={data['MQTT_PORT']}
MQTT_USERNAME={data['MQTT_USERNAME']}
MQTT_PASSWORD={data['MQTT_PASSWORD']}
BASE_TOPIC={data['BASE_TOPIC']}

# Application Configuration
SENSOR_CONFIG_FILE=endpoints.json
STATUS_INTERVAL={data['STATUS_INTERVAL']}
DEDUPLICATION_DELAY={data['DEDUPLICATION_DELAY']}

# Web Interface Configuration
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_DEBUG=false

# Auto-detach Configuration
AUTO_DETACH_ENABLED={str(data.get('AUTO_DETACH_ENABLED', True)).lower()}
AUTO_DETACH_TIMEOUT={auto_detach_timeout}
AUTO_DETACH_HOURS={auto_detach_timeout // 3600}
AUTO_DETACH_WARNING_TIMEOUT={auto_detach_warning_timeout}
AUTO_DETACH_WARNING_HOURS={auto_detach_warning_timeout // 3600}
AUTO_DETACH_CHECK_INTERVAL={auto_detach_check_interval}

# Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/bssci_service.log

# Security
SECRET_KEY=your-secret-key-here"""
        
        # Write to .env file
        with open('.env', 'w') as f:
            f.write(env_content)
        
        # Reload environment variables
        from dotenv import load_dotenv
        load_dotenv(override=True)
            
        # Force reload of the bssci_config module to pick up new .env values
        import importlib
        import sys
        if 'bssci_config' in sys.modules:
            importlib.reload(sys.modules['bssci_config'])
            
        return jsonify({'success': True, 'message': 'Configuration updated in .env file and reloaded successfully.'})
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'success': False, 'message': f'Configuration update failed: {str(e)}'})

@app.route('/certificates')
def certificates():
    return render_template('certificates.html')

@app.route('/logs')
def logs():
    return render_template('logs.html')

@app.route('/api/logs')
def get_logs():
    global log_entries

    # Get query parameters for filtering
    level_filter = request.args.get('level', 'all').upper()
    logger_filter = request.args.get('logger', 'all')
    limit = int(request.args.get('limit', 100))

    # Filter logs based on parameters
    filtered_logs = log_entries

    if level_filter != 'ALL':
        filtered_logs = [log for log in filtered_logs if log['level'] == level_filter]

    if logger_filter != 'all':
        filtered_logs = [log for log in filtered_logs if logger_filter.lower() in log['logger'].lower()]

    # Return the most recent logs (up to limit)
    recent_logs = filtered_logs[-limit:] if len(filtered_logs) > limit else filtered_logs

    return jsonify({
        'logs': recent_logs,
        'total_logs': len(log_entries),
        'filtered_logs': len(filtered_logs),
        'source': 'memory'
    })

# Global variable to store TLS server instance
# tls_server_instance = None # Already defined at the top

def set_tls_server(server):
    """Set the TLS server instance"""
    global tls_server_instance
    tls_server_instance = server

def get_bssci_service_status():
    """Get the status of the BSSCI service"""
    try:
        global tls_server_instance
        tls_server = tls_server_instance
        
        if not tls_server:
            return {
                'running': False,
                'service_type': 'web_ui',
                'tls_server': {'active': False},
                'mqtt_broker': {'active': False},
                'base_stations': {'total_connected': 0, 'total_connecting': 0, 'connected': [], 'connecting': []},
                'total_sensors': 0,
                'registered_sensors': 0,
                'pending_requests': 0,
                'error': 'TLS server not available'
            }
            
        # Get base station status safely
        bs_status = {'total_connected': 0, 'total_connecting': 0, 'connected': [], 'connecting': []}
        try:
            if hasattr(tls_server, 'connected_base_stations') and hasattr(tls_server, 'connecting_base_stations'):
                # Build base station status directly from TLS server attributes
                connected_stations = []
                for writer, bs_eui in getattr(tls_server, 'connected_base_stations', {}).items():
                    addr = writer.get_extra_info("peername") if writer else None
                    connected_stations.append({
                        "eui": bs_eui,
                        "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                        "status": "connected"
                    })
                
                connecting_stations = []
                for writer, bs_eui in getattr(tls_server, 'connecting_base_stations', {}).items():
                    addr = writer.get_extra_info("peername") if writer else None
                    connecting_stations.append({
                        "eui": bs_eui,
                        "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                        "status": "connecting"
                    })
                
                bs_status = {
                    "connected": connected_stations,
                    "connecting": connecting_stations,
                    "total_connected": len(connected_stations),
                    "total_connecting": len(connecting_stations)
                }
            elif hasattr(tls_server, 'get_base_station_status'):
                bs_status = tls_server.get_base_station_status()
        except Exception as e:
            print(f"Error getting base station status: {e}")
            
        # Get sensor status safely
        sensor_status = {}
        try:
            if hasattr(tls_server, 'get_sensor_registration_status'):
                sensor_status = tls_server.get_sensor_registration_status()
        except Exception as e:
            print(f"Error getting sensor status: {e}")

        # Build response safely
        response = {
            'running': True,
            'service_type': 'web_ui',
            'base_stations': bs_status,
            'tls_server': {
                'active': True,
                'listening_port': getattr(bssci_config, 'LISTEN_PORT', 16018),
                'connected_base_stations': bs_status.get('total_connected', 0),
                'total_sensors': len(sensor_status),
                'registered_sensors': len([s for s in sensor_status.values() if s.get('registered', False)])
            },
            'mqtt_broker': {
                'active': True,
                'broker_host': getattr(bssci_config, 'MQTT_BROKER', 'localhost'),
                'broker_port': getattr(bssci_config, 'MQTT_PORT', 1883)
            },
            'total_sensors': len(sensor_status),
            'registered_sensors': len([s for s in sensor_status.values() if s.get('registered', False)]),
            'pending_requests': len(getattr(tls_server, 'pending_attach_requests', {}))
        }
        
        return response
        
    except Exception as e:
        print(f"Error in get_bssci_service_status: {e}")
        import traceback
        traceback.print_exc()
        return {
            'running': False,
            'service_type': 'web_ui',
            'tls_server': {'active': False},
            'mqtt_broker': {'active': False},
            'base_stations': {'total_connected': 0, 'total_connecting': 0, 'connected': [], 'connecting': []},
            'total_sensors': 0,
            'registered_sensors': 0,
            'pending_requests': 0,
            'error': f'Status error: {str(e)}'
        }

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    global log_entries
    log_entries = []
    return jsonify({'success': True, 'message': 'Logs cleared successfully'})

@app.route('/api/bssci/status')
def bssci_status():
    try:
        status = get_bssci_service_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error in bssci_status endpoint: {e}")
        error_response = {
            'running': False,
            'error': f'Service status error: {str(e)}',
            'service_type': 'web_ui',
            'tls_server': {'active': False},
            'mqtt_broker': {'active': False},
            'base_stations': {'total_connected': 0, 'total_connecting': 0, 'connected': [], 'connecting': []},
            'total_sensors': 0,
            'registered_sensors': 0,
            'pending_requests': 0
        }
        return jsonify(error_response), 500

@app.route('/api/base_stations')
def get_base_stations():
    """Get status of connected base stations"""
    try:
        global tls_server_instance
        tls_server = tls_server_instance

        if not tls_server:
            return jsonify({
                "connected": [],
                "connecting": [],
                "total_connected": 0,
                "total_connecting": 0,
                "error": "TLS server not initialized"
            }), 503

        # Try to get status directly from TLS server attributes first
        try:
            if hasattr(tls_server, 'connected_base_stations') and hasattr(tls_server, 'connecting_base_stations'):
                connected_stations = []
                for writer, bs_eui in getattr(tls_server, 'connected_base_stations', {}).items():
                    try:
                        addr = writer.get_extra_info("peername") if writer else None
                        connected_stations.append({
                            "eui": bs_eui,
                            "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                            "status": "connected"
                        })
                    except Exception as e:
                        print(f"Error processing connected station {bs_eui}: {e}")
                
                connecting_stations = []
                for writer, bs_eui in getattr(tls_server, 'connecting_base_stations', {}).items():
                    try:
                        addr = writer.get_extra_info("peername") if writer else None
                        connecting_stations.append({
                            "eui": bs_eui,
                            "address": f"{addr[0]}:{addr[1]}" if addr else "unknown",
                            "status": "connecting"
                        })
                    except Exception as e:
                        print(f"Error processing connecting station {bs_eui}: {e}")
                
                return jsonify({
                    "connected": connected_stations,
                    "connecting": connecting_stations,
                    "total_connected": len(connected_stations),
                    "total_connecting": len(connecting_stations)
                })
        except Exception as e:
            print(f"Error accessing TLS server attributes directly: {e}")

        # Fallback to method if available
        if hasattr(tls_server, 'get_base_station_status'):
            try:
                status = tls_server.get_base_station_status()
                return jsonify(status)
            except Exception as e:
                print(f"Error calling get_base_station_status: {e}")
        
        # Final fallback
        return jsonify({
            "connected": [],
            "connecting": [],
            "total_connected": 0,
            "total_connecting": 0,
            "error": "Unable to retrieve base station status"
        }), 503
            
    except Exception as e:
        print(f"Error in get_base_stations endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "connected": [],
            "connecting": [],
            "total_connected": 0,
            "total_connecting": 0,
            "error": f"Base stations error: {str(e)}"
        }), 500

@app.route('/api/certificates/status')
def get_certificate_status():
    """Get status of SSL certificates"""
    import os
    from datetime import datetime
    try:
        cert_files = {
            'ca': 'certs/ca_cert.pem',
            'service': 'certs/service_center_cert.pem',
            'key': 'certs/service_center_key.pem'
        }

        status = {'certificates': {}}

        for cert_type, file_path in cert_files.items():
            if os.path.exists(file_path):
                status['certificates'][cert_type] = True
                # Try to get certificate expiry date
                try:
                    if cert_type != 'key':  # Don't try to parse private key as certificate
                        import ssl
                        import socket
                        from cryptography import x509
                        from cryptography.hazmat.backends import default_backend

                        with open(file_path, 'rb') as f:
                            cert_data = f.read()
                            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
                            expiry = cert.not_valid_after
                            status['certificates'][f'{cert_type}_expires'] = expiry.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass  # If we can't read the certificate, just mark as present
            else:
                status['certificates'][cert_type] = False

        return jsonify({'success': True, 'certificates': status['certificates']})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/certificates/download/<filename>')
def download_certificate(filename):
    """Download a certificate file"""
    import os
    from flask import send_file, abort

    # Security: only allow specific certificate files
    allowed_files = ['ca_cert.pem', 'service_center_cert.pem', 'service_center_key.pem']
    if filename not in allowed_files:
        abort(404)

    file_path = os.path.join('certs', filename)
    if not os.path.exists(file_path):
        abort(404)

    return send_file(file_path, as_attachment=True, download_name=filename)

@app.route('/api/certificates/upload/<cert_type>', methods=['POST'])
def upload_certificate(cert_type):
    """Upload a new certificate"""
    import os
    from werkzeug.utils import secure_filename

    if 'certificate' not in request.files:
        return jsonify({'success': False, 'message': 'No file provided'})

    file = request.files['certificate']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})

    # Map cert types to filenames
    cert_mapping = {
        'ca': 'ca_cert.pem',
        'service': 'service_center_cert.pem',
        'key': 'service_center_key.pem'
    }

    if cert_type not in cert_mapping:
        return jsonify({'success': False, 'message': 'Invalid certificate type'})

    try:
        # Ensure certs directory exists
        os.makedirs('certs', exist_ok=True)

        # Backup existing file
        target_file = os.path.join('certs', cert_mapping[cert_type])
        if os.path.exists(target_file):
            backup_file = target_file + '.backup'
            os.rename(target_file, backup_file)

        # Save new file
        file.save(target_file)

        return jsonify({'success': True, 'message': f'{cert_type.upper()} certificate uploaded successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/certificates/generate', methods=['POST'])
def generate_certificates():
    """Generate new SSL certificates"""
    import os
    import subprocess

    try:
        # Ensure certs directory exists
        os.makedirs('certs', exist_ok=True)

        # Generate new certificates using OpenSSL with static, validated commands
        import shlex

        # Execute certificate generation commands with completely static strings

        # Generate CA private key
        result = subprocess.run(['openssl', 'genrsa', '-out', 'certs/ca_key.pem', '2048'],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({'success': False, 'message': f'CA key generation failed: {result.stderr}'})

        # Generate CA certificate
        result = subprocess.run(['openssl', 'req', '-new', '-x509', '-key', 'certs/ca_key.pem', '-out', 'certs/ca_cert.pem', '-days', '365', '-subj', '/C=US/ST=State/L=City/O=BSSCI/CN=BSSCI-CA'],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({'success': False, 'message': f'CA certificate generation failed: {result.stderr}'})

        # Generate service private key
        result = subprocess.run(['openssl', 'genrsa', '-out', 'certs/service_center_key.pem', '2048'],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({'success': False, 'message': f'Service key generation failed: {result.stderr}'})

        # Generate service certificate request
        result = subprocess.run(['openssl', 'req', '-new', '-key', 'certs/service_center_key.pem', '-out', 'certs/service_center.csr', '-subj', '/C=US/ST=State/L=City/O=BSSCI/CN=bssci-service'],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({'success': False, 'message': f'Service certificate request generation failed: {result.stderr}'})

        # Sign service certificate with CA
        result = subprocess.run(['openssl', 'x509', '-req', '-in', 'certs/service_center.csr', '-CA', 'certs/ca_cert.pem', '-CAkey', 'certs/ca_key.pem', '-CAcreateserial', '-out', 'certs/service_center_cert.pem', '-days', '365'],
                               capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return jsonify({'success': False, 'message': f'Service certificate signing failed: {result.stderr}'})

        # Clean up temporary files
        temp_files = ['certs/service_center.csr', 'certs/ca_cert.srl']
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return jsonify({'success': True, 'message': 'New certificates generated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/certificates/backup')
def backup_certificates():
    """Download all certificates as ZIP"""
    import os
    import tempfile
    import zipfile
    from flask import send_file

    try:
        # Create temporary ZIP file
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')

        with zipfile.ZipFile(temp_zip.name, 'w') as zipf:
            cert_files = ['ca_cert.pem', 'service_center_cert.pem', 'service_center_key.pem']
            for cert_file in cert_files:
                file_path = os.path.join('certs', cert_file)
                if os.path.exists(file_path):
                    zipf.write(file_path, cert_file)

        return send_file(temp_zip.name, as_attachment=True, download_name='bssci_certificates_backup.zip')
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/certificates/restore', methods=['POST'])
def restore_certificates():
    """Restore certificates from ZIP backup"""
    import os
    import tempfile
    import zipfile

    if 'backup' not in request.files:
        return jsonify({'success': False, 'message': 'No backup file provided'})

    file = request.files['backup']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})

    try:
        # Save uploaded ZIP to temporary location
        temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        file.save(temp_zip.name)

        # Extract certificates
        with zipfile.ZipFile(temp_zip.name, 'r') as zipf:
            # Ensure certs directory exists
            os.makedirs('certs', exist_ok=True)

            # Extract only certificate files
            cert_files = ['ca_cert.pem', 'service_center_cert.pem', 'service_center_key.pem']
            for cert_file in cert_files:
                if cert_file in zipf.namelist():
                    target_path = os.path.join('certs', cert_file)
                    # Backup existing file
                    if os.path.exists(target_path):
                        os.rename(target_path, target_path + '.backup')
                    # Extract new file
                    zipf.extract(cert_file, 'certs')

        # Clean up temporary file
        os.unlink(temp_zip.name)

        return jsonify({'success': True, 'message': 'Certificates restored successfully from backup'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/container/restart', methods=['POST'])
def restart_container():
    """Force restart the entire container"""
    import subprocess
    import threading
    import time
    import os

    def container_restart_in_background():
        """Perform container restart in a separate thread"""
        try:
            time.sleep(1)  # Small delay to allow response to be sent
            
            logger.info("Forcing container restart")
            try:
                # Send SIGTERM to PID 1 (init process) to restart the container
                subprocess.run(['kill', '-TERM', '1'], check=False, timeout=5)
            except Exception as e:
                logger.error(f"Container restart failed: {e}")
                # Fallback: exit the main process which should cause container restart
                os._exit(0)
                
        except Exception as e:
            logger.error(f"Error during container restart: {e}")
            os._exit(1)

    try:
        # Start restart in background thread
        restart_thread = threading.Thread(target=container_restart_in_background)
        restart_thread.daemon = True
        restart_thread.start()
        
        return jsonify({'success': True, 'message': 'Container restart initiated. The container will restart completely to reload all environment variables.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restart the BSSCI service with full environment reload"""
    import subprocess
    import threading
    import time
    import os

    def restart_in_background():
        """Perform the restart operation in a separate thread"""
        try:
            time.sleep(1)  # Small delay to allow response to be sent

            # Check if we're running in Docker
            is_docker = os.path.exists('/.dockerenv') or os.getenv('CONTAINER') == '1'
            
            if is_docker:
                # In Docker, we need to restart the entire container to reload .env
                logger.info("Docker environment detected - triggering container restart")
                try:
                    # Send SIGTERM to PID 1 (init process) to restart the container gracefully
                    subprocess.run(['kill', '-TERM', '1'], check=False, timeout=5)
                except Exception as e:
                    logger.error(f"Container restart failed: {e}")
                    # Fallback to process restart
                    _restart_processes()
            else:
                # In regular environment, restart processes and reload environment
                logger.info("Regular environment detected - restarting processes")
                _restart_processes()
                
        except Exception as e:
            logger.error(f"Error during restart: {e}")
            # Fallback to basic process restart
            _restart_processes()

    def _restart_processes():
        """Restart Python processes"""
        try:
            # Kill existing processes
            subprocess.run(['pkill', '-f', 'python.*web_main.py'], check=False, timeout=10)
            subprocess.run(['pkill', '-f', 'python.*main.py'], check=False, timeout=10)
            subprocess.run(['pkill', '-f', 'python.*sync_main.py'], check=False, timeout=10)

            time.sleep(3)  # Wait for processes to terminate

            # Reload environment and start the service again
            subprocess.Popen(['python', 'web_main.py'],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           env=dict(os.environ))  # Pass current environment
        except Exception as e:
            logger.error(f"Error restarting processes: {e}")

    try:
        # Start restart in background thread
        restart_thread = threading.Thread(target=restart_in_background)
        restart_thread.daemon = True
        restart_thread.start()

        return jsonify({'success': True, 'message': 'Service restart initiated. In Docker environments, the entire container will restart to reload environment variables.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)