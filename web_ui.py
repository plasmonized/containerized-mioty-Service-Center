
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for
from typing import List, Dict, Any
import bssci_config

app = Flask(__name__)
app.secret_key = 'bssci-ui-secret-key'

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
        # Try to get data from TLS server first (includes preferred paths)
        try:
            from web_main import get_tls_server
            tls_server = get_tls_server()
            if tls_server:
                tls_server.reload_sensor_config()
                # Get registration status with preferred paths
                sensor_status = tls_server.get_sensor_registration_status()
                
                # Also get preferred downlink paths from the TLS server
                if hasattr(tls_server, 'preferred_downlink_paths'):
                    for eui, path_info in tls_server.preferred_downlink_paths.items():
                        if eui in sensor_status:
                            sensor_status[eui]['preferredDownlinkPath'] = path_info
                
                return jsonify(sensor_status)
        except Exception as e:
            print(f"Error getting data from TLS server: {e}")
        
        # Fallback to file only
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
                    'registration_info': {},
                    'preferredDownlinkPath': sensor.get('preferredDownlinkPath', None)
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
        'DEDUPLICATION_DELAY': bssci_config.DEDUPLICATION_DELAY
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
DEDUPLICATION_DELAY = {data['DEDUPLICATION_DELAY']}  # seconds to wait for duplicate messages before forwarding
'''
    
    try:
        with open('bssci_config.py', 'w') as f:
            f.write(config_content)
        return jsonify({'success': True, 'message': 'Configuration updated successfully. Restart required.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

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

def get_bssci_service_status():
    """Get the status of the BSSCI service"""
    try:
        from web_main import get_tls_server
        tls_server = get_tls_server()
        if tls_server:
            bs_status = tls_server.get_base_station_status()
            sensor_status = tls_server.get_sensor_registration_status()
            
            return {
                'running': True,
                'base_stations': bs_status,
                'tls_server': {
                    'total_sensors': len(sensor_status),
                    'registered_sensors': len([s for s in sensor_status.values() if s['registered']]),
                    'pending_requests': len(tls_server.pending_attach_requests)
                }
            }
        else:
            return {'running': False, 'error': 'TLS server not available'}
    except Exception as e:
        return {'running': False, 'error': str(e)}

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    global log_entries
    log_entries = []
    return jsonify({'success': True, 'message': 'Logs cleared successfully'})

@app.route('/api/bssci/status')
def bssci_status():
    return jsonify(get_bssci_service_status())

@app.route('/api/base_stations')
def get_base_stations():
    """Get status of connected base stations"""
    try:
        # Import here to avoid circular import
        from web_main import get_tls_server
        tls_server = get_tls_server()
        
        if tls_server:
            status = tls_server.get_base_station_status()
            return jsonify(status)
        else:
            return jsonify({
                "connected": [],
                "connecting": [],
                "total_connected": 0,
                "total_connecting": 0,
                "error": "TLS server not initialized"
            })
    except Exception as e:
        return jsonify({
            "connected": [],
            "connecting": [],
            "total_connected": 0,
            "total_connecting": 0,
            "error": str(e)
        })

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
        
        # Generate new certificates using OpenSSL
        # This is a basic certificate generation - in production you might want more sophisticated setup
        commands = [
            # Generate CA private key
            ['openssl', 'genrsa', '-out', 'certs/ca_key.pem', '2048'],
            # Generate CA certificate
            ['openssl', 'req', '-new', '-x509', '-key', 'certs/ca_key.pem', '-out', 'certs/ca_cert.pem', '-days', '365', '-subj', '/C=US/ST=State/L=City/O=BSSCI/CN=BSSCI-CA'],
            # Generate service private key
            ['openssl', 'genrsa', '-out', 'certs/service_center_key.pem', '2048'],
            # Generate service certificate request
            ['openssl', 'req', '-new', '-key', 'certs/service_center_key.pem', '-out', 'certs/service_center.csr', '-subj', '/C=US/ST=State/L=City/O=BSSCI/CN=bssci-service'],
            # Sign service certificate with CA
            ['openssl', 'x509', '-req', '-in', 'certs/service_center.csr', '-CA', 'certs/ca_cert.pem', '-CAkey', 'certs/ca_key.pem', '-CAcreateserial', '-out', 'certs/service_center_cert.pem', '-days', '365']
        ]
        
        for cmd in commands:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return jsonify({'success': False, 'message': f'Certificate generation failed: {result.stderr}'})
        
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

@app.route('/api/service/restart', methods=['POST'])
def restart_service():
    """Restart the BSSCI service"""
    import subprocess
    import threading
    import time
    
    def restart_in_background():
        """Perform the restart operation in a separate thread"""
        try:
            time.sleep(1)  # Small delay to allow response to be sent
            
            # Kill existing processes
            subprocess.run(['pkill', '-f', 'python.*web_main.py'], check=False)
            subprocess.run(['pkill', '-f', 'python.*main.py'], check=False)
            subprocess.run(['pkill', '-f', 'python.*sync_main.py'], check=False)
            
            time.sleep(2)  # Wait for processes to terminate
            
            # Start the service again
            subprocess.Popen(['python', 'web_main.py'], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Error during restart: {e}")
    
    try:
        # Start restart in background thread
        restart_thread = threading.Thread(target=restart_in_background)
        restart_thread.daemon = True
        restart_thread.start()
        
        return jsonify({'success': True, 'message': 'Service restart initiated'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
