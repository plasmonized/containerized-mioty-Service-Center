
import json
import logging
import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from typing import List, Dict, Any
import bssci_config

app = Flask(__name__)
app.secret_key = 'bssci-ui-secret-key'

# Global variables for log storage and configuration
log_entries: List[Dict[str, Any]] = []
max_log_entries = 1000

# Custom log handler to capture all logs
# Consolidated WebUILogHandler - single definition to avoid duplicates

class WebUILogHandler(logging.Handler):
    def emit(self, record):
        global log_entries
        
        # Filter out noisy web request logs to reduce clutter
        if record.name == 'werkzeug' and any(x in record.getMessage() for x in [
            'GET /api/', 'GET /logs', 'GET /sensors', 'GET /config', 'GET /', 'GET /static/'
        ]):
            return  # Skip web request logs
            
        # Avoid duplicate handlers by checking if this exact message was just logged
        current_time = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        message = record.getMessage()
        
        # Check if this exact message was logged in the last second (duplicate detection)
        if log_entries:
            last_entry = log_entries[-1]
            time_diff = abs(record.created - datetime.strptime(last_entry['timestamp'], '%Y-%m-%d %H:%M:%S.%f').timestamp())
            if (time_diff < 1.0 and  # Within 1 second
                last_entry['message'] == message and 
                last_entry['logger'] == record.name):
                return  # Skip duplicate message
            
        log_entry = {
            'timestamp': current_time,
            'level': record.levelname,
            'logger': record.name,
            'message': message
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
        # Also reload TLS server config to sync
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server:
                tls_server.reload_sensor_config()
                # Get registration status
                return jsonify(tls_server.get_sensor_registration_status())
        except:
            pass  # Fallback to file only
        
        with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
            sensors = json.load(f)
            # Convert to registration status format
            sensor_status = {}
            for sensor in sensors:
                eui = sensor['eui'].lower()
                sensor_status[eui] = {
                    'eui': sensor['eui'],
                    'nwKey': sensor['nwKey'],
                    'shortAddr': sensor['shortAddr'],
                    'bidi': sensor['bidi'],
                    'registered': False,
                    'registration_info': {}
                }
            return jsonify(sensor_status)
    except:
        return jsonify({})

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

@app.route('/api/sensors/clear', methods=['POST'])
def clear_all_sensors():
    """Clear all sensor configurations"""
    try:
        # Clear the file
        with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
            json.dump([], f, indent=4)
        
        # Also clear from TLS server if available
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server:
                tls_server.clear_all_sensors()
        except:
            pass  # TLS server not available, that's okay
        
        return jsonify({'success': True, 'message': 'All sensors cleared successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sensors/reload', methods=['POST'])
def reload_sensors():
    """Force reload sensor configuration in TLS server"""
    try:
        from web_main import get_tls_server
        tls_server = get_tls_server()
        if tls_server:
            tls_server.reload_sensor_config()
            return jsonify({'success': True, 'message': 'Sensor configuration reloaded successfully'})
        else:
            return jsonify({'success': False, 'message': 'TLS server not available'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/config')
def config():
    config_data = {
        'LISTEN_HOST': bssci_config.LISTEN_HOST,
        'LISTEN_PORT': bssci_config.LISTEN_PORT,
        'MQTT_BROKER': bssci_config.MQTT_BROKER,
        'MQTT_PORT': bssci_config.MQTT_PORT,
        'MQTT_USERNAME': bssci_config.MQTT_USERNAME,
        'MQTT_PASSWORD': bssci_config.MQTT_PASSWORD,
        'BASE_TOPIC': bssci_config.BASE_TOPIC,
        'STATUS_INTERVAL': bssci_config.STATUS_INTERVAL,
        'HTTP_FORWARD_ENABLED': getattr(bssci_config, 'HTTP_FORWARD_ENABLED', True),
        'HTTP_FORWARD_URL': getattr(bssci_config, 'HTTP_FORWARD_URL', 'https://mioty-cloud.replit.app'),
        'SERVICE_CENTER_URL': getattr(bssci_config, 'SERVICE_CENTER_URL', 'https://your-service-center.replit.app')
    }
    return render_template('config.html', config=config_data)

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.json
    config_content = f'''LISTEN_HOST = "{data['LISTEN_HOST']}"
LISTEN_PORT = {data['LISTEN_PORT']}

CERT_FILE = "certs/service_center_cert.pem"
KEY_FILE = "certs/service_center_key.pem"
CA_FILE = "certs/ca_cert.pem"

MQTT_BROKER = "{data['MQTT_BROKER']}"
MQTT_PORT = {data['MQTT_PORT']}
MQTT_USERNAME = "{data['MQTT_USERNAME']}"
MQTT_PASSWORD = "{data['MQTT_PASSWORD']}"
BASE_TOPIC = "{data['BASE_TOPIC']}"

SENSOR_CONFIG_FILE = "endpoints.json"
STATUS_INTERVAL = {data['STATUS_INTERVAL']}  # seconds

# HTTP Forwarding Configuration (optional)
HTTP_FORWARD_ENABLED = {str(data.get('HTTP_FORWARD_ENABLED', True))}
HTTP_FORWARD_URL = "{data.get('HTTP_FORWARD_URL', 'https://mioty-cloud.replit.app')}"

# Service Center Integration (optional)
SERVICE_CENTER_URL = "{data.get('SERVICE_CENTER_URL', 'https://your-service-center.replit.app')}"
'''
    
    try:
        with open('bssci_config.py', 'w') as f:
            f.write(config_content)
        return jsonify({'success': True, 'message': 'Configuration updated successfully. Restart required.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

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
        'bssci_status': get_bssci_service_status()
    })

def get_bssci_service_status():
    """Get the status of the BSSCI service"""
    try:
        from web_main import get_tls_server, get_mqtt_client
        
        # TLS Server Status
        tls_server = get_tls_server()
        tls_status = {
            'active': tls_server is not None,
            'listening_port': bssci_config.LISTEN_PORT if tls_server else None,
            'connected_base_stations': 0,
            'total_sensors': 0,
            'registered_sensors': 0,
            'pending_requests': 0
        }
        
        if tls_server:
            bs_status = tls_server.get_base_station_status()
            sensor_status = tls_server.get_sensor_registration_status()
            
            tls_status.update({
                'connected_base_stations': bs_status['total_connected'],
                'total_sensors': len(sensor_status),
                'registered_sensors': len([s for s in sensor_status.values() if s['registered']]),
                'pending_requests': len(tls_server.pending_attach_requests)
            })
        
        # MQTT Status
        mqtt_client = get_mqtt_client()
        mqtt_status = {
            'active': mqtt_client is not None,
            'broker_host': bssci_config.MQTT_BROKER,
            'broker_port': bssci_config.MQTT_PORT,
            'username': bssci_config.MQTT_USERNAME,
            'base_topic': bssci_config.BASE_TOPIC,
            'connected': False,
            'out_queue_size': 0,
            'in_queue_size': 0
        }
        
        if mqtt_client:
            mqtt_status.update({
                'connected': True,  # Assume connected if client exists
                'out_queue_size': mqtt_client.mqtt_out_queue.qsize() if hasattr(mqtt_client, 'mqtt_out_queue') else 0,
                'in_queue_size': mqtt_client.mqtt_in_queue.qsize() if hasattr(mqtt_client, 'mqtt_in_queue') else 0
            })
        
        # HTTP Forwarding Status
        http_status = {
            'enabled': getattr(bssci_config, 'HTTP_FORWARD_ENABLED', False),
            'target_url': getattr(bssci_config, 'HTTP_FORWARD_URL', 'Not configured')
        }
        
        return {
            'running': tls_status['active'] and mqtt_status['active'],
            'tls_server': tls_status,
            'mqtt_broker': mqtt_status,
            'http_forwarding': http_status,
            'uptime_seconds': int(time.time() - (getattr(get_bssci_service_status, 'start_time', time.time()))),
            'last_updated': time.time()
        }
        
    except Exception as e:
        return {
            'running': False,
            'error': str(e),
            'tls_server': {'active': False},
            'mqtt_broker': {'active': False},
            'http_forwarding': {'enabled': False}
        }

# Initialize start time for uptime calculation
if not hasattr(get_bssci_service_status, 'start_time'):
    get_bssci_service_status.start_time = time.time()

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    global log_entries
    log_entries = []
    return jsonify({'success': True, 'message': 'Logs cleared successfully'})

@app.route('/api/bssci/status')
def bssci_status():
    return jsonify(get_bssci_service_status())

# HTTP API Integration Endpoints for Service Center Communication

@app.route('/api/sensors/import-from-service-center', methods=['POST'])
def import_sensors_from_service_center():
    """Receive sensors exported from mioty service center"""
    try:
        data = request.get_json()
        sensors = data.get('sensors', [])
        source = data.get('source', 'unknown')
        
        logger.info(f"\n🔄 ===== SENSOR IMPORT RECEIVED =====")
        logger.info(f"   Source: {source}")
        logger.info(f"   Sensors: {len(sensors)} to import")
        logger.info(f"🔄 ===================================\n")
        
        results = {'imported': [], 'errors': [], 'skipped': []}
        
        # Load existing sensors
        try:
            with open(bssci_config.SENSOR_CONFIG_FILE, 'r') as f:
                existing_sensors = json.load(f)
        except:
            existing_sensors = []
        
        existing_euis = [s['eui'].lower() for s in existing_sensors]
        
        for sensor in sensors:
            try:
                eui = sensor.get('eui', '').lower()
                name = sensor.get('name', f'Sensor-{eui[-4:]}')
                nw_key = sensor.get('nwKey', '0011223344556677889AABBCCDDEEFF00')
                short_addr = sensor.get('shortAddr', eui[-4:].upper())
                
                # Check if sensor already exists
                if eui in existing_euis:
                    results['skipped'].append({
                        'eui': eui,
                        'name': name,
                        'reason': 'Already registered in BSSCI'
                    })
                    logger.info(f"⏭️  Skipping {eui} - already exists")
                    continue
                
                # Add new sensor to configuration
                new_sensor = {
                    "eui": eui.upper(),
                    "nwKey": nw_key,
                    "shortAddr": short_addr,
                    "bidi": sensor.get('bidi', False)
                }
                
                existing_sensors.append(new_sensor)
                existing_euis.append(eui)
                
                results['imported'].append({
                    'eui': eui,
                    'name': name,
                    'status': 'registered'
                })
                logger.info(f"✅ Imported and registered {name} ({eui})")
                    
            except Exception as e:
                results['errors'].append({
                    'sensor': sensor,
                    'error': str(e)
                })
                logger.error(f"❌ Error processing {sensor.get('eui', 'unknown')}: {e}")
        
        # Save updated sensor configuration
        if results['imported']:
            try:
                with open(bssci_config.SENSOR_CONFIG_FILE, 'w') as f:
                    json.dump(existing_sensors, f, indent=4)
                
                # Reload TLS server configuration
                try:
                    from web_main import get_tls_server
                    tls_server = get_tls_server()
                    if tls_server:
                        tls_server.reload_sensor_config()
                except:
                    pass
                    
            except Exception as e:
                logger.error(f"❌ Failed to save sensor configuration: {e}")
                return jsonify({'error': f'Failed to save configuration: {str(e)}'}), 500
        
        logger.info(f"\n📊 Import Summary: {len(results['imported'])} imported, {len(results['skipped'])} skipped, {len(results['errors'])} errors\n")
        
        return jsonify({
            'success': True,
            'message': f"Processed {len(sensors)} sensors: {len(results['imported'])} imported, {len(results['skipped'])} skipped",
            'results': results
        })
        
    except Exception as e:
        logger.error(f"❌ Import error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bssci/uplink/<sensor_eui>', methods=['POST'])
def receive_sensor_data(sensor_eui):
    """Receive real-time sensor data from service center"""
    try:
        uplink_data = request.get_json()
        
        logger.info(f"\n📡 ===== SENSOR DATA RECEIVED =====")
        logger.info(f"   Sensor: {sensor_eui}")
        logger.info(f"   Base Station: {uplink_data.get('bs_eui', 'N/A')}")
        logger.info(f"   RSSI: {uplink_data.get('rssi', 'N/A')} dBm")
        logger.info(f"   SNR: {uplink_data.get('snr', 'N/A')} dB")
        logger.info(f"   Data: {uplink_data.get('data', [])}")
        logger.info(f"📡 =================================\n")
        
        # Validate BSSCI format
        required_fields = ['bs_eui', 'rxTime', 'snr', 'rssi', 'cnt', 'data']
        if not all(field in uplink_data for field in required_fields):
            return jsonify({'error': 'Invalid BSSCI uplink format'}), 400
        
        # Process the sensor data - store in log for now
        logger.info(f"🔧 Processing data from {sensor_eui}: {len(uplink_data.get('data', []))} bytes")
        
        # You can add more sophisticated data processing here
        # For now, we'll just acknowledge receipt
        logger.info(f"✅ Processed data from {sensor_eui}")
        
        return jsonify({
            'status': 'success',
            'message': f'Data from {sensor_eui} processed successfully'
        })
            
    except Exception as e:
        logger.error(f"❌ Data processing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bssci/base-station-status/<base_station_eui>', methods=['POST'])
def receive_base_station_status(base_station_eui):
    """Receive base station status from external service center"""
    try:
        status_data = request.get_json()
        
        logger.info(f"\n📊 ===== BASE STATION STATUS RECEIVED =====")
        logger.info(f"   Base Station: {base_station_eui}")
        logger.info(f"   CPU Load: {status_data.get('cpuLoad', 'N/A')}")
        logger.info(f"   Memory Load: {status_data.get('memLoad', 'N/A')}")
        logger.info(f"   Duty Cycle: {status_data.get('dutyCycle', 'N/A')}")
        logger.info(f"   Status Code: {status_data.get('code', 'N/A')}")
        logger.info(f"📊 =========================================\n")
        
        return jsonify({
            'status': 'success',
            'message': f'Base station status from {base_station_eui} received successfully'
        })
            
    except Exception as e:
        logger.error(f"❌ Status processing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/bssci/batch', methods=['POST'])
def receive_batch_data():
    """Receive batch data from service center"""
    try:
        batch_data = request.get_json()
        uplinks = batch_data.get('uplinks', [])
        base_station_statuses = batch_data.get('baseStationStatuses', [])
        
        logger.info(f"\n📦 ===== BATCH DATA RECEIVED =====")
        logger.info(f"   Uplinks: {len(uplinks)}")
        logger.info(f"   Base Station Statuses: {len(base_station_statuses)}")
        logger.info(f"📦 ===============================\n")
        
        # Process uplinks
        for uplink in uplinks:
            logger.info(f"🔧 Processing uplink from {uplink.get('sensor_eui', 'unknown')}")
        
        # Process base station statuses
        for status in base_station_statuses:
            logger.info(f"🔧 Processing status from {status.get('base_station_eui', 'unknown')}")
        
        return jsonify({
            'status': 'success',
            'message': f'Batch data processed: {len(uplinks)} uplinks, {len(base_station_statuses)} statuses'
        })
            
    except Exception as e:
        logger.error(f"❌ Batch processing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/base_stations')
def get_base_stations():
    """Get status of connected base stations"""
    try:
        # Import here to avoid circular import
        from web_main import get_tls_server, get_mqtt_client
        tls_server = get_tls_server()
        
        if tls_server:
            status = tls_server.get_base_station_status()
            
            # Add additional status info
            status['last_updated'] = time.time()
            status['tls_server_running'] = True
            
            # Add MQTT status if available
            try:
                mqtt_client = get_mqtt_client()
                if mqtt_client:
                    status['mqtt_status'] = 'connected'
                else:
                    status['mqtt_status'] = 'disconnected'
            except:
                status['mqtt_status'] = 'unknown'
            
            return jsonify(status)
        else:
            return jsonify({
                "connected": [],
                "connecting": [],
                "total_connected": 0,
                "total_connecting": 0,
                "tls_server_running": False,
                "mqtt_status": "unknown",
                "error": "TLS server not initialized"
            })
    except Exception as e:
        return jsonify({
            "connected": [],
            "connecting": [],
            "total_connected": 0,
            "total_connecting": 0,
            "tls_server_running": False,
            "mqtt_status": "unknown",
            "error": str(e)
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
