#!/usr/bin/env python3
"""
NTRIP to Rover Bridge - 将 NTRIP 基站的 RTCM 数据转发到 Rover 设备
Connects to NTRIP base station, receives RTCM data, and forwards it to rover via serial port
"""

import base64
import json
import os
import serial
import serial.tools.list_ports
import socket
import sys
import time
from datetime import datetime
from typing import Optional, Tuple


# Log directory path
LOG_DIR = r"C:\Users\oxpas\Documents\GitHub\DroneDevTools\RTKtools\RTKbaseTester\logs"

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ntrip_to_rover_config.json")

# Default configuration
DEFAULT_CONFIG = {
    # NTRIP Base Station Settings
    "ntrip_host": "192.168.137.172",
    "ntrip_port": 2101,
    "ntrip_mountpoint": "RTCM4",
    "ntrip_username": "XTRTK",
    "ntrip_password": "123456",
    
    # Rover Serial Port Settings
    "rover_port": "COM3",  # Will auto-detect if not specified
    "rover_baudrate": 115200,
    "rover_timeout": 1.0,
    "auto_detect_rover": True,
    "rover_device_name": "XTRTK",
    
    # Statistics
    "stats_interval": 5.0,  # Print statistics every N seconds
}


def load_config(config_path: str = CONFIG_FILE) -> dict:
    """Load configuration from JSON file."""
    if not os.path.exists(config_path):
        print(f"⚠️  Config file not found: {config_path}")
        print("   Using default configuration.")
        return DEFAULT_CONFIG.copy()
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        merged_config = DEFAULT_CONFIG.copy()
        merged_config.update(config)
        
        print(f"✅ Loaded configuration from: {config_path}")
        return merged_config
    except Exception as e:
        print(f"⚠️  Error reading config file: {e}")
        print("   Using default configuration.")
        return DEFAULT_CONFIG.copy()


def find_rover_port(device_name: str = "XTRTK") -> Optional[str]:
    """Try to find the rover device port automatically."""
    print("🔍 Searching for rover device...")
    ports = serial.tools.list_ports.comports()
    
    for port in ports:
        print(f"   Found: {port.device} - {port.description}")
        if device_name.upper() in port.description.upper():
            print(f"✅ Found rover device: {port.device}")
            return port.device
    
    print("⚠️  Rover device not found automatically.")
    print("   Available ports:")
    for port in ports:
        print(f"      {port.device} - {port.description}")
    return None


def build_ntrip_request(host: str, mountpoint: str, user: str, password: str) -> bytes:
    """Build a minimal NTRIP v2 GET request."""
    auth = base64.b64encode(f"{user}:{password}".encode("ascii")).decode("ascii")
    lines = [
        f"GET /{mountpoint} HTTP/1.0",
        f"Host: {host}",
        "User-Agent: NTRIP-PythonBridge/1.0",
        f"Authorization: Basic {auth}",
        "Ntrip-Version: Ntrip/2.0",
        "Connection: close",
        "",
        "",
    ]
    return "\r\n".join(lines).encode("ascii")


def connect_ntrip(
    host: str,
    port: int,
    mountpoint: str,
    user: str,
    password: str,
) -> Tuple[socket.socket, bytes]:
    """Connect to NTRIP caster and return socket + header."""
    addr = (host, port)
    print(f"🔌 Connecting to NTRIP caster {host}:{port}, mountpoint '{mountpoint}'...")
    
    try:
        sock = socket.create_connection(addr, timeout=10.0)
    except OSError as e:
        print(f"❌ Failed to connect to NTRIP caster: {e}")
        raise
    
    sock.settimeout(30.0)
    
    request = build_ntrip_request(host, mountpoint, user, password)
    sock.sendall(request)
    
    # Read response header
    header = b""
    max_header = 64 * 1024
    
    while len(header) < max_header:
        try:
            chunk = sock.recv(1024)
        except socket.timeout:
            # Check if we already have a 200 status
            try:
                text = header.decode("iso-8859-1", errors="replace")
            except Exception:
                text = ""
            if "ICY 200" in text or " 200 " in text:
                break
            raise ConnectionError("Timed out while waiting for NTRIP response header.")
        
        if not chunk:
            break
        
        header += chunk
        
        # Check for header termination
        if b"\r\n\r\n" in header:
            break
        
        # Check for 200 status without explicit termination
        try:
            text = header.decode("iso-8859-1", errors="replace")
        except Exception:
            text = ""
        if ("ICY 200" in text or " 200 " in text) and len(header) > 128:
            break
    
    # Check response
    header_text = header.decode("iso-8859-1", errors="replace")
    status_line = header_text.split("\r\n", 1)[0]
    
    if "ICY 200" in status_line or " 200 " in status_line:
        print("✅ NTRIP connection established!")
        # Extract binary data from header if present
        header_end = header.find(b"\r\n\r\n")
        if header_end != -1:
            header_end += 4
        else:
            # Find where binary data starts (RTCM sync byte 0xD3)
            status_end = header.find(b"\r\n")
            if status_end == -1:
                status_end = header.find(b"\n")
            if status_end != -1:
                data_start = header.find(b"\xD3", status_end + 2)
                if data_start != -1:
                    header_end = data_start
                else:
                    header_end = len(header)
            else:
                header_end = len(header)
        
        binary_data = header[header_end:] if header_end < len(header) else b""
        return sock, binary_data
    else:
        sock.close()
        if "401" in status_line or "403" in status_line:
            raise ConnectionError("Authentication failed (401/403). Check username/password.")
        if "404" in status_line:
            raise ConnectionError("Mountpoint not found (404). Check mountpoint name.")
        raise ConnectionError(f"Unexpected response: {status_line}")


def connect_rover(port: str, baudrate: int = 115200, timeout: float = 1.0) -> Optional[serial.Serial]:
    """Connect to rover device via serial port."""
    try:
        print(f"🔌 Connecting to rover at {port} ({baudrate} baud)...")
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
        print(f"✅ Rover connected successfully!")
        return ser
    except serial.SerialException as e:
        print(f"❌ Failed to connect to rover: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None


def forward_rtcm_data(
    ntrip_sock: socket.socket,
    rover_ser: serial.Serial,
    initial_data: bytes = b"",
    stats_interval: float = 5.0,
):
    """Forward RTCM data from NTRIP socket to rover serial port."""
    print("\n📡 Starting RTCM data forwarding...")
    print("Press Ctrl+C to stop.\n")
    
    total_bytes_received = len(initial_data)
    total_bytes_sent = 0
    start_time = time.time()
    last_stats = start_time
    
    # Send initial data if present
    if initial_data:
        try:
            rover_ser.write(initial_data)
            total_bytes_sent += len(initial_data)
            print(f"📦 Sent {len(initial_data)} bytes from header")
        except Exception as e:
            print(f"⚠️  Error sending initial data: {e}")
    
    # Set socket timeout for reading
    ntrip_sock.settimeout(1.0)
    
    try:
        while True:
            try:
                # Read data from NTRIP socket
                chunk = ntrip_sock.recv(4096)
                
                if not chunk:
                    print("⚠️  NTRIP connection closed by server.")
                    break
                
                total_bytes_received += len(chunk)
                
                # Forward to rover
                try:
                    rover_ser.write(chunk)
                    total_bytes_sent += len(chunk)
                except serial.SerialException as e:
                    print(f"❌ Error writing to rover: {e}")
                    break
                except Exception as e:
                    print(f"⚠️  Error forwarding data: {e}")
                    continue
                
            except socket.timeout:
                # Timeout is OK, just continue
                continue
            except OSError as e:
                print(f"❌ NTRIP socket error: {e}")
                break
            
            # Print statistics periodically
            now = time.time()
            if now - last_stats >= stats_interval:
                elapsed = now - start_time
                rx_rate = total_bytes_received / elapsed if elapsed > 0 else 0
                tx_rate = total_bytes_sent / elapsed if elapsed > 0 else 0
                
                print(
                    f"[{elapsed:.1f}s] "
                    f"Received: {total_bytes_received} bytes ({rx_rate:.1f} B/s) | "
                    f"Sent: {total_bytes_sent} bytes ({tx_rate:.1f} B/s)"
                )
                last_stats = now
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user.")
    finally:
        elapsed = time.time() - start_time
        print(f"\n📊 Final Statistics:")
        print(f"   Runtime: {elapsed:.1f}s")
        print(f"   Total received: {total_bytes_received} bytes")
        print(f"   Total sent: {total_bytes_sent} bytes")
        if elapsed > 0:
            print(f"   Avg receive rate: {total_bytes_received/elapsed:.1f} B/s")
            print(f"   Avg send rate: {total_bytes_sent/elapsed:.1f} B/s")


def write_summary_log(config: dict, total_received: int, total_sent: int, elapsed: float, error: Optional[str] = None):
    """Write summary log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    ts = datetime.now()
    log_filename = ts.strftime("ntrip_to_rover_log_%Y%m%d_%H%M%S.txt")
    filename = os.path.join(LOG_DIR, log_filename)
    
    lines = []
    lines.append(f"Time       : {ts.isoformat(sep=' ', timespec='seconds')}")
    lines.append(f"NTRIP Host : {config.get('ntrip_host')}:{config.get('ntrip_port')}")
    lines.append(f"Mountpoint : {config.get('ntrip_mountpoint')}")
    lines.append(f"Rover Port : {config.get('rover_port')}")
    lines.append("")
    
    if elapsed > 0:
        lines.append("Result     : DATA FORWARDED")
        lines.append(f"Duration   : {elapsed:.1f} s")
        lines.append(f"Received   : {total_received} bytes")
        lines.append(f"Sent       : {total_sent} bytes")
        lines.append(f"Rx Rate    : {total_received/elapsed:.1f} B/s")
        lines.append(f"Tx Rate    : {total_sent/elapsed:.1f} B/s")
    else:
        lines.append("Result     : NO DATA")
    
    lines.append("")
    if error:
        lines.append("Error      :")
        lines.append(f"  {error}")
    else:
        lines.append("Error      : (none)")
    
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"📝 Summary log written to {filename}")
    except OSError as e:
        print(f"⚠️  Failed to write log file: {e}")


def main():
    """Main function."""
    print("=" * 70)
    print("NTRIP to Rover Bridge - RTCM Data Forwarding")
    print("=" * 70)
    print()
    
    # Load configuration
    config = load_config()
    
    # Determine rover port
    rover_port = config.get("rover_port")
    if config.get("auto_detect_rover", True) and (not rover_port or rover_port == "AUTO"):
        device_name = config.get("rover_device_name", "XTRTK")
        detected_port = find_rover_port(device_name)
        if detected_port:
            rover_port = detected_port
        else:
            print("\n❌ Could not auto-detect rover device.")
            print("   Please specify port manually in config file.")
            sys.exit(1)
    
    if not rover_port:
        print("❌ No rover port specified.")
        sys.exit(1)
    
    # Connect to NTRIP base station
    try:
        ntrip_sock, initial_data = connect_ntrip(
            host=config["ntrip_host"],
            port=config["ntrip_port"],
            mountpoint=config["ntrip_mountpoint"],
            user=config["ntrip_username"],
            password=config["ntrip_password"],
        )
    except Exception as e:
        print(f"❌ Failed to connect to NTRIP: {e}")
        write_summary_log(config, 0, 0, 0, str(e))
        sys.exit(1)
    
    # Connect to rover
    rover_ser = connect_rover(
        port=rover_port,
        baudrate=config.get("rover_baudrate", 115200),
        timeout=config.get("rover_timeout", 1.0),
    )
    
    if not rover_ser:
        ntrip_sock.close()
        write_summary_log(config, 0, 0, 0, "Failed to connect to rover")
        sys.exit(1)
    
    # Forward data
    start_time = time.time()
    total_received = len(initial_data)
    total_sent = 0
    error_message = None
    
    try:
        forward_rtcm_data(
            ntrip_sock=ntrip_sock,
            rover_ser=rover_ser,
            initial_data=initial_data,
            stats_interval=config.get("stats_interval", 5.0),
        )
    except Exception as e:
        error_message = str(e)
        print(f"❌ Error: {e}")
    finally:
        try:
            ntrip_sock.close()
        except Exception:
            pass
        try:
            rover_ser.close()
        except Exception:
            pass
        
        elapsed = time.time() - start_time
        print("\n✅ Connections closed.")
        write_summary_log(config, total_received, total_sent, elapsed, error_message)


if __name__ == "__main__":
    main()

