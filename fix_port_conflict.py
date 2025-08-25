
#!/usr/bin/env python3
"""
Fix port conflicts for BSSCI server
"""

import subprocess
import sys
import time

def find_processes_on_port(port):
    """Find processes using the specified port"""
    try:
        result = subprocess.run(['lsof', '-ti', f':{port}'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            pids = [pid.strip() for pid in result.stdout.split('\n') if pid.strip()]
            return pids
        return []
    except FileNotFoundError:
        # lsof not available, try netstat
        try:
            result = subprocess.run(['netstat', '-tlnp'], 
                                  capture_output=True, text=True)
            lines = result.stdout.split('\n')
            pids = []
            for line in lines:
                if f':{port}' in line and 'LISTEN' in line:
                    parts = line.split()
                    if len(parts) > 6 and '/' in parts[6]:
                        pid = parts[6].split('/')[0]
                        pids.append(pid)
            return pids
        except:
            return []

def kill_processes(pids):
    """Kill processes by PID"""
    for pid in pids:
        try:
            subprocess.run(['kill', '-9', pid], check=True)
            print(f"✅ Killed process {pid}")
        except subprocess.CalledProcessError:
            print(f"❌ Failed to kill process {pid}")

def main():
    port = 16017
    print(f"🔍 Checking for processes on port {port}...")
    
    pids = find_processes_on_port(port)
    
    if pids:
        print(f"⚠️  Found {len(pids)} process(es) using port {port}: {', '.join(pids)}")
        response = input("Kill these processes? (y/N): ")
        
        if response.lower() == 'y':
            kill_processes(pids)
            time.sleep(1)
            
            # Check again
            remaining_pids = find_processes_on_port(port)
            if remaining_pids:
                print(f"❌ Some processes still running: {', '.join(remaining_pids)}")
            else:
                print(f"✅ Port {port} is now free")
        else:
            print("❌ Port conflict not resolved")
    else:
        print(f"✅ Port {port} is free")

if __name__ == "__main__":
    main()
