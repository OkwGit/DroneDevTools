#!/usr/bin/env python3
"""
RTK Rover Complete - Combined NTRIP forwarding and RTK status monitoring
Combines ntrip_to_rover.py and rover_test.py functionality in one program
to avoid COM port duplication issues.
"""

import base64
import json
import os
import serial
import serial.tools.list_ports
import socket
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from typing import Dict, Optional, Tuple


# Log directory path
LOG_DIR = r"C:\Users\oxpas\Documents\GitHub\DroneDevTools\RTKtools\RTKbaseTester\logs"

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtk_rover_complete_config.json")

# Default configuration
DEFAULT_CONFIG = {
    # NTRIP Base Station Settings
    "ntrip_host": "192.168.137.172",
    "ntrip_port": 2101,
    "ntrip_mountpoint": "RTCM4",
    "ntrip_username": "XTRTK",
    "ntrip_password": "123456",
    
    # Rover Serial Port Settings
    "rover_port": "COM3",
    "rover_baudrate": 115200,
    "rover_timeout": 1.0,
    "auto_detect_rover": True,
    "rover_device_name": "XTRTK",
    
    # Display Settings
    "display_interval": 0.5,  # Update display every N seconds
    "stats_interval": 5.0,    # Print statistics every N seconds
}


# RTK Fix Quality Codes
QUALITY_NO_FIX = 0
QUALITY_GPS = 1
QUALITY_DGPS = 2
QUALITY_PPS = 3
QUALITY_RTK_FIXED = 4
QUALITY_RTK_FLOAT = 5
QUALITY_ESTIMATED = 6
QUALITY_MANUAL = 7
QUALITY_SIMULATION = 8

QUALITY_NAMES = {
    0: "No Fix",
    1: "GPS",
    2: "DGPS",
    3: "PPS",
    4: "RTK Fixed",
    5: "RTK Float",
    6: "Estimated",
    7: "Manual",
    8: "Simulation",
}


class RTKRoverComplete:
    """Main class combining NTRIP forwarding and rover monitoring."""
    
    def __init__(self, config: dict):
        self.config = config
        self.running = False
        
        # NTRIP connection
        self.ntrip_sock: Optional[socket.socket] = None
        
        # Rover serial connection
        self.rover_ser: Optional[serial.Serial] = None
        
        # Statistics
        self.rtcm_received = 0
        self.rtcm_sent = 0
        self.nmea_received = 0
        
        # RTCM validation
        self.rtcm_valid_frames = 0  # Count of valid RTCM3 frames detected
        self.rtcm_last_received_time: Optional[float] = None
        self.rtcm_buffer = bytearray()
        self.rtcm_msg_types = set()  # Track RTCM message types received
        self.rtcm_first_frame_time: Optional[float] = None  # Time when first RTCM frame received
        
        # Rover data
        self.rover_data: Dict = {}
        self.data_history = []
        self.best_quality = QUALITY_NO_FIX
        self.rtk_float_time: Optional[float] = None
        self.rtk_fixed_time: Optional[float] = None
        
        # RTK status tracking
        self.initial_quality: Optional[int] = None
        self.quality_changes = []  # Track quality changes over time
        self.last_quality_update_time: Optional[float] = None
        
        # Threading
        self.start_time = time.time()
        self.lock = threading.Lock()
    
    def load_config(self, config_path: str = CONFIG_FILE) -> dict:
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
    
    def find_rover_port(self, device_name: str = "XTRTK") -> Optional[str]:
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
    
    def build_ntrip_request(self, host: str, mountpoint: str, user: str, password: str) -> bytes:
        """Build a minimal NTRIP v2 GET request."""
        auth = base64.b64encode(f"{user}:{password}".encode("ascii")).decode("ascii")
        lines = [
            f"GET /{mountpoint} HTTP/1.0",
            f"Host: {host}",
            "User-Agent: RTK-Rover-Complete/1.0",
            f"Authorization: Basic {auth}",
            "Ntrip-Version: Ntrip/2.0",
            "Connection: close",
            "",
            "",
        ]
        return "\r\n".join(lines).encode("ascii")
    
    def connect_ntrip(self) -> Tuple[socket.socket, bytes]:
        """Connect to NTRIP caster."""
        host = self.config["ntrip_host"]
        port = self.config["ntrip_port"]
        mountpoint = self.config["ntrip_mountpoint"]
        user = self.config["ntrip_username"]
        password = self.config["ntrip_password"]
        
        addr = (host, port)
        print(f"🔌 Connecting to NTRIP caster {host}:{port}, mountpoint '{mountpoint}'...")
        
        try:
            sock = socket.create_connection(addr, timeout=10.0)
        except OSError as e:
            print(f"❌ Failed to connect to NTRIP caster: {e}")
            raise
        
        sock.settimeout(30.0)
        
        request = self.build_ntrip_request(host, mountpoint, user, password)
        sock.sendall(request)
        
        # Read response header
        header = b""
        max_header = 64 * 1024
        
        while len(header) < max_header:
            try:
                chunk = sock.recv(1024)
            except socket.timeout:
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
            
            if b"\r\n\r\n" in header:
                break
            
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
    
    def connect_rover(self) -> serial.Serial:
        """Connect to rover device via serial port."""
        port = self.config["rover_port"]
        baudrate = self.config["rover_baudrate"]
        timeout = self.config["rover_timeout"]
        
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
            raise
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            raise
    
    def parse_nmea_gga(self, line: str) -> Optional[Dict]:
        """Parse NMEA GNGGA or GPGGA sentence."""
        if not (line.startswith("$GNGGA") or line.startswith("$GPGGA")):
            return None
        
        try:
            parts = line.split(",")
            if len(parts) < 15:
                return None
            
            time_str = parts[1] if parts[1] else None
            lat_str = parts[2] if parts[2] else None
            lat_dir = parts[3] if parts[3] else None
            lon_str = parts[4] if parts[4] else None
            lon_dir = parts[5] if parts[5] else None
            quality = int(parts[6]) if parts[6] else QUALITY_NO_FIX
            num_sats = int(parts[7]) if parts[7] else 0
            hdop = float(parts[8]) if parts[8] else 0.0
            altitude = float(parts[9]) if parts[9] else 0.0
            geoid_sep = float(parts[11]) if len(parts) > 11 and parts[11] else 0.0
            
            latitude = None
            if lat_str and lat_dir:
                try:
                    lat_deg = float(lat_str[:2])
                    lat_min = float(lat_str[2:])
                    latitude = lat_deg + lat_min / 60.0
                    if lat_dir == "S":
                        latitude = -latitude
                except (ValueError, IndexError):
                    pass
            
            longitude = None
            if lon_str and lon_dir:
                try:
                    lon_deg = float(lon_str[:3])
                    lon_min = float(lon_str[3:])
                    longitude = lon_deg + lon_min / 60.0
                    if lon_dir == "W":
                        longitude = -longitude
                except (ValueError, IndexError):
                    pass
            
            utc_time = None
            if time_str and len(time_str) >= 6:
                try:
                    hour = int(time_str[0:2])
                    minute = int(time_str[2:4])
                    second = int(time_str[4:6])
                    utc_time = f"{hour:02d}:{minute:02d}:{second:02d}"
                except (ValueError, IndexError):
                    pass
            
            return {
                "time": utc_time,
                "latitude": latitude,
                "longitude": longitude,
                "quality": quality,
                "quality_name": QUALITY_NAMES.get(quality, "Unknown"),
                "num_sats": num_sats,
                "hdop": hdop,
                "altitude": altitude,
                "geoid_sep": geoid_sep,
            }
        except (ValueError, IndexError):
            return None
    
    def parse_nmea_rmc(self, line: str) -> Optional[Dict]:
        """Parse NMEA GNRMC or GPRMC sentence."""
        if not (line.startswith("$GNRMC") or line.startswith("$GPRMC")):
            return None
        
        try:
            parts = line.split(",")
            if len(parts) < 12:
                return None
            
            speed_knots = float(parts[7]) if parts[7] else 0.0
            track = float(parts[8]) if parts[8] else 0.0
            
            return {
                "speed_knots": speed_knots,
                "speed_ms": speed_knots * 0.514444,
                "track": track,
            }
        except (ValueError, IndexError):
            return None
    
    def parse_nmea_gsa(self, line: str) -> Optional[Dict]:
        """Parse NMEA GNGSA or GPGSA sentence."""
        if not (line.startswith("$GNGSA") or line.startswith("$GPGSA")):
            return None
        
        try:
            parts = line.split(",")
            if len(parts) < 17:
                return None
            
            pdop = float(parts[15]) if parts[15] else 0.0
            hdop = float(parts[16]) if parts[16] else 0.0
            vdop = float(parts[17]) if len(parts) > 17 and parts[17] else 0.0
            
            return {
                "pdop": pdop,
                "hdop": hdop,
                "vdop": vdop,
            }
        except (ValueError, IndexError):
            return None
    
    def validate_rtcm_data(self, data: bytes):
        """Validate RTCM3 data and count valid frames."""
        self.rtcm_buffer.extend(data)
        current_time = time.time()
        
        # Parse RTCM3 frames
        while True:
            # Look for sync byte 0xD3
            try:
                sync_index = self.rtcm_buffer.index(0xD3)
            except ValueError:
                # No sync byte found
                if len(self.rtcm_buffer) > 1024:
                    self.rtcm_buffer.clear()
                break
            
            if len(self.rtcm_buffer) - sync_index < 3:
                # Not enough data for header
                if sync_index > 0:
                    del self.rtcm_buffer[:sync_index]
                break
            
            # Parse RTCM3 header
            header = self.rtcm_buffer[sync_index + 1 : sync_index + 3]
            length = ((header[0] & 0x03) << 8) | header[1]
            
            frame_len = 3 + length + 3  # sync+header + payload + CRC
            if len(self.rtcm_buffer) - sync_index < frame_len:
                # Wait for more data
                if sync_index > 0:
                    del self.rtcm_buffer[:sync_index]
                break
            
            # Extract frame
            frame = self.rtcm_buffer[sync_index : sync_index + frame_len]
            del self.rtcm_buffer[: sync_index + frame_len]
            
            # Validate frame (basic checks)
            if len(frame) >= 6:
                # Extract message type from payload
                payload = frame[3:-3]
                if len(payload) >= 2:
                    msg_type = ((payload[0] << 4) | (payload[1] >> 4)) & 0x0FFF
                    if msg_type > 0:
                        with self.lock:
                            self.rtcm_valid_frames += 1
                            self.rtcm_msg_types.add(msg_type)
                            self.rtcm_last_received_time = current_time
                            if self.rtcm_first_frame_time is None:
                                self.rtcm_first_frame_time = current_time
    
    def check_rtcm_reception_status(self, elapsed: float) -> Dict[str, any]:
        """Check if rover is receiving valid RTCM data."""
        status = {
            "rtcm_data_flowing": False,
            "rtcm_valid": False,
            "rtcm_status": "Unknown",
            "rtcm_last_received": None,
            "rtcm_frames": 0,
            "rtcm_msg_types": [],
            "rover_using_rtcm": False,
            "rtcm_duration": 0.0,
            "rtk_convergence_estimate": None,
        }
        
        with self.lock:
            status["rtcm_frames"] = self.rtcm_valid_frames
            status["rtcm_msg_types"] = sorted(list(self.rtcm_msg_types))
            status["rtcm_last_received"] = self.rtcm_last_received_time
            
            # Calculate RTCM data duration
            if self.rtcm_first_frame_time:
                status["rtcm_duration"] = elapsed - (self.rtcm_first_frame_time - self.start_time)
            
            # Check if RTCM data is flowing
            if self.rtcm_received > 0:
                status["rtcm_data_flowing"] = True
            
            # Check if valid RTCM frames detected
            if self.rtcm_valid_frames > 0:
                status["rtcm_valid"] = True
            
            # Check if RTCM data is recent (within last 5 seconds)
            if self.rtcm_last_received_time:
                time_since_last = elapsed - (self.rtcm_last_received_time - self.start_time)
                if time_since_last < 5.0:
                    status["rtcm_data_flowing"] = True
            
            # Check if rover is using RTCM (quality improved from initial)
            current_quality = self.rover_data.get("quality", QUALITY_NO_FIX)
            if self.initial_quality is not None:
                if current_quality > self.initial_quality:
                    status["rover_using_rtcm"] = True
                elif current_quality >= QUALITY_RTK_FLOAT:
                    status["rover_using_rtcm"] = True
            
            # RTK convergence estimate
            if status["rtcm_valid"] and current_quality < QUALITY_RTK_FLOAT:
                rtcm_time = status["rtcm_duration"]
                num_sats = self.rover_data.get("num_sats", 0)
                msg_types_count = len(status["rtcm_msg_types"])
                
                # Typical convergence times
                typical_float_time = 60.0  # 1 minute
                typical_fixed_time = 180.0  # 3 minutes
                
                # Adjust based on conditions
                if msg_types_count >= 4 and num_sats >= 12:
                    # Good conditions
                    remaining_float = max(0, typical_float_time - rtcm_time)
                    remaining_fixed = max(0, typical_fixed_time - rtcm_time)
                elif msg_types_count >= 2 and num_sats >= 8:
                    # Moderate conditions
                    remaining_float = max(0, typical_float_time * 1.5 - rtcm_time)
                    remaining_fixed = max(0, typical_fixed_time * 1.5 - rtcm_time)
                else:
                    # Limited conditions
                    remaining_float = max(0, typical_float_time * 2.0 - rtcm_time)
                    remaining_fixed = max(0, typical_fixed_time * 2.0 - rtcm_time)
                
                if remaining_float > 0:
                    if remaining_float < 60:
                        status["rtk_convergence_estimate"] = f"RTK Float: ~{remaining_float:.0f}s"
                    else:
                        status["rtk_convergence_estimate"] = f"RTK Float: ~{remaining_float/60:.1f}min"
                else:
                    status["rtk_convergence_estimate"] = "RTK Float: Any moment..."
            
            # Determine status message
            if status["rover_using_rtcm"] and current_quality >= QUALITY_RTK_FLOAT:
                status["rtcm_status"] = "✅ Rover using RTCM (RTK active)"
            elif status["rover_using_rtcm"]:
                status["rtcm_status"] = "🟡 Rover receiving RTCM (RTK converging)"
            elif status["rtcm_valid"] and status["rtcm_data_flowing"]:
                status["rtcm_status"] = "🟢 RTCM data valid and flowing"
            elif status["rtcm_data_flowing"]:
                status["rtcm_status"] = "🟡 RTCM data flowing (validating...)"
            elif self.rtcm_received > 0:
                status["rtcm_status"] = "⚠️  RTCM data sent but not validated"
            else:
                status["rtcm_status"] = "❌ No RTCM data received"
        
        return status
    
    def ntrip_forward_thread(self):
        """Thread function to forward RTCM data from NTRIP to rover."""
        print("📡 NTRIP forwarding thread started")
        
        try:
            while self.running:
                try:
                    chunk = self.ntrip_sock.recv(4096)
                    
                    if not chunk:
                        print("⚠️  NTRIP connection closed by server.")
                        break
                    
                    with self.lock:
                        self.rtcm_received += len(chunk)
                    
                    # Validate RTCM data
                    self.validate_rtcm_data(chunk)
                    
                    # Forward to rover
                    try:
                        self.rover_ser.write(chunk)
                        with self.lock:
                            self.rtcm_sent += len(chunk)
                    except serial.SerialException as e:
                        print(f"❌ Error writing to rover: {e}")
                        break
                
                except socket.timeout:
                    continue
                except OSError as e:
                    print(f"❌ NTRIP socket error: {e}")
                    break
        
        except Exception as e:
            print(f"❌ Error in NTRIP forwarding thread: {e}")
    
    def rover_read_thread(self):
        """Thread function to read NMEA data from rover."""
        print("📡 Rover reading thread started")
        
        try:
            while self.running:
                try:
                    line = self.rover_ser.readline().decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue
                    
                    with self.lock:
                        self.nmea_received += 1
                    
                    # Parse NMEA sentences
                    gga_data = self.parse_nmea_gga(line)
                    if gga_data:
                        with self.lock:
                            quality = gga_data.get("quality", QUALITY_NO_FIX)
                            
                            # Track initial quality
                            if self.initial_quality is None:
                                self.initial_quality = quality
                            
                            # Track quality changes
                            current_time = time.time()
                            if quality != self.rover_data.get("quality"):
                                self.quality_changes.append({
                                    "time": current_time - self.start_time,
                                    "from": self.rover_data.get("quality", QUALITY_NO_FIX),
                                    "to": quality,
                                })
                                self.last_quality_update_time = current_time
                            
                            self.rover_data.update(gga_data)
                            
                            if quality > self.best_quality:
                                self.best_quality = quality
                                elapsed = current_time - self.start_time
                                if quality == QUALITY_RTK_FLOAT and self.rtk_float_time is None:
                                    self.rtk_float_time = elapsed
                                if quality == QUALITY_RTK_FIXED and self.rtk_fixed_time is None:
                                    self.rtk_fixed_time = elapsed
                            self.data_history.append(self.rover_data.copy())
                    
                    rmc_data = self.parse_nmea_rmc(line)
                    if rmc_data:
                        with self.lock:
                            self.rover_data.update(rmc_data)
                    
                    gsa_data = self.parse_nmea_gsa(line)
                    if gsa_data:
                        with self.lock:
                            self.rover_data.update(gsa_data)
                
                except serial.SerialException as e:
                    print(f"❌ Error reading from rover: {e}")
                    break
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"❌ Error in rover reading thread: {e}")
    
    def display_status(self):
        """Display current status."""
        elapsed = time.time() - self.start_time
        
        # Clear screen
        os.system("cls" if os.name == "nt" else "clear")
        
        print("=" * 70)
        print("RTK Rover Complete - NTRIP Forwarding + RTK Monitoring")
        print("=" * 70)
        print(f"Runtime: {elapsed:.1f}s")
        print()
        
        # RTCM Statistics
        rx_rate = self.rtcm_received / elapsed if elapsed > 0 else 0
        tx_rate = self.rtcm_sent / elapsed if elapsed > 0 else 0
        print(f"📡 RTCM: Received {self.rtcm_received} bytes ({rx_rate:.1f} B/s) | "
              f"Sent {self.rtcm_sent} bytes ({tx_rate:.1f} B/s)")
        print(f"📨 NMEA: Received {self.nmea_received} messages")
        
        # RTCM Reception Status
        rtcm_status = self.check_rtcm_reception_status(elapsed)
        print(f"\n🔍 RTCM Reception Status:")
        print(f"   {rtcm_status['rtcm_status']}")
        if rtcm_status['rtcm_valid']:
            print(f"   Valid Frames: {rtcm_status['rtcm_frames']}")
            if rtcm_status['rtcm_msg_types']:
                msg_types_str = ", ".join(map(str, rtcm_status['rtcm_msg_types'][:10]))
                if len(rtcm_status['rtcm_msg_types']) > 10:
                    msg_types_str += f" ... (+{len(rtcm_status['rtcm_msg_types']) - 10} more)"
                print(f"   RTCM Types: {msg_types_str}")
            if rtcm_status['rtcm_duration'] > 0:
                print(f"   RTCM Duration: {rtcm_status['rtcm_duration']:.1f}s")
        if rtcm_status['rtcm_last_received']:
            time_since = elapsed - (rtcm_status['rtcm_last_received'] - self.start_time)
            if time_since < 5.0:
                print(f"   Last Valid Frame: {time_since:.1f}s ago ✅")
            else:
                print(f"   Last Valid Frame: {time_since:.1f}s ago ⚠️")
        
        # RTK Convergence Estimate
        if rtcm_status['rtk_convergence_estimate']:
            print(f"   ⏳ {rtcm_status['rtk_convergence_estimate']}")
        
        # Quality change indicator
        with self.lock:
            if self.quality_changes:
                latest_change = self.quality_changes[-1]
                from_name = QUALITY_NAMES.get(latest_change['from'], 'Unknown')
                to_name = QUALITY_NAMES.get(latest_change['to'], 'Unknown')
                if latest_change['from'] != latest_change['to']:
                    print(f"   📈 Quality Change: {from_name} → {to_name} "
                          f"(at {latest_change['time']:.1f}s)")
        
        # RTCM Data Rate Check
        with self.lock:
            if self.rtcm_received > 0 and elapsed > 0:
                rtcm_rate = self.rtcm_received / elapsed
                if rtcm_rate < 50:
                    print(f"   ⚠️  RTCM Rate Low: {rtcm_rate:.1f} B/s (expected 200-500 B/s)")
                elif rtcm_rate > 1000:
                    print(f"   ⚠️  RTCM Rate High: {rtcm_rate:.1f} B/s (check connection)")
                else:
                    print(f"   ✅ RTCM Rate Normal: {rtcm_rate:.1f} B/s")
        print()
        
        # RTK Status
        with self.lock:
            quality = self.rover_data.get("quality", QUALITY_NO_FIX)
            quality_name = self.rover_data.get("quality_name", "Unknown")
            best_quality = self.best_quality
        
        if quality == QUALITY_RTK_FIXED:
            status_icon = "🟢"
            status_text = "RTK FIXED (cm-level)"
            rtk_hint = ""
            if self.rtk_fixed_time:
                print(f"⏱️  RTK Fixed achieved in {self.rtk_fixed_time:.1f}s")
        elif quality == QUALITY_RTK_FLOAT:
            status_icon = "🟡"
            status_text = "RTK FLOAT (dm-level)"
            rtk_hint = "💡 RTK Float - Waiting for RTK Fixed convergence..."
            if self.rtk_float_time:
                print(f"⏱️  RTK Float achieved in {self.rtk_float_time:.1f}s")
        elif quality == QUALITY_GPS:
            status_icon = "🔵"
            status_text = "GPS Fix"
            rtk_hint = "⚠️  GPS mode - RTCM data forwarding active, waiting for RTK..."
        elif quality == QUALITY_DGPS:
            status_icon = "🔵"
            status_text = "DGPS Fix"
            rtk_hint = "⚠️  DGPS mode - Check RTCM data"
        else:
            status_icon = "🔴"
            status_text = "No Fix"
            rtk_hint = "❌ No fix - Check antenna and satellite visibility"
        
        print(f"Status: {status_icon} {status_text}")
        print(f"Quality Code: {quality} ({quality_name})")
        
        if best_quality > quality:
            best_name = QUALITY_NAMES.get(best_quality, "Unknown")
            print(f"Best Achieved: {best_name} (Quality {best_quality})")
        
        if rtk_hint:
            print(f"\n{rtk_hint}")
        print()
        
        # Position
        with self.lock:
            lat = self.rover_data.get("latitude")
            lon = self.rover_data.get("longitude")
        
        if lat is not None and lon is not None:
            print(f"Position: {lat:.8f}°N, {lon:.8f}°E")
        else:
            print("Position: No data")
        
        # Other data
        with self.lock:
            altitude = self.rover_data.get("altitude")
            utc_time = self.rover_data.get("time")
            num_sats = self.rover_data.get("num_sats", 0)
            hdop = self.rover_data.get("hdop", 0.0)
            pdop = self.rover_data.get("pdop", 0.0)
            vdop = self.rover_data.get("vdop", 0.0)
            speed_ms = self.rover_data.get("speed_ms")
            track = self.rover_data.get("track")
        
        if altitude is not None:
            print(f"Altitude: {altitude:.2f} m (MSL)")
        if utc_time:
            print(f"UTC Time: {utc_time}")
        print(f"Satellites: {num_sats}")
        if hdop > 0:
            print(f"HDOP: {hdop:.2f}")
        if pdop > 0:
            print(f"PDOP: {pdop:.2f}")
        if vdop > 0:
            print(f"VDOP: {vdop:.2f}")
        if speed_ms is not None:
            print(f"Speed: {speed_ms:.2f} m/s ({speed_ms * 3.6:.2f} km/h)")
        if track is not None:
            print(f"Track: {track:.1f}°")
        
        print()
        print("Press Ctrl+C to stop")
        print("=" * 70)
    
    def display_thread(self):
        """Thread function to update display periodically."""
        display_interval = self.config.get("display_interval", 0.5)
        
        while self.running:
            self.display_status()
            time.sleep(display_interval)
    
    def run(self):
        """Main run function."""
        print("=" * 70)
        print("RTK Rover Complete - Starting...")
        print("=" * 70)
        print()
        
        # Determine rover port
        rover_port = self.config.get("rover_port")
        if self.config.get("auto_detect_rover", True) and (not rover_port or rover_port == "AUTO"):
            device_name = self.config.get("rover_device_name", "XTRTK")
            detected_port = self.find_rover_port(device_name)
            if detected_port:
                rover_port = detected_port
                self.config["rover_port"] = rover_port
            else:
                print("\n❌ Could not auto-detect rover device.")
                print("   Please specify port manually in config file.")
                return False
        
        if not rover_port:
            print("❌ No rover port specified.")
            return False
        
        # Connect to NTRIP
        try:
            self.ntrip_sock, initial_data = self.connect_ntrip()
        except Exception as e:
            print(f"❌ Failed to connect to NTRIP: {e}")
            return False
        
        # Connect to rover
        try:
            self.rover_ser = self.connect_rover()
        except Exception as e:
            print(f"❌ Failed to connect to rover: {e}")
            self.ntrip_sock.close()
            return False
        
        # Send initial RTCM data if present
        if initial_data:
            try:
                self.rover_ser.write(initial_data)
                self.rtcm_sent += len(initial_data)
                print(f"📦 Sent {len(initial_data)} bytes from NTRIP header")
            except Exception as e:
                print(f"⚠️  Error sending initial data: {e}")
        
        # Start threads
        self.running = True
        self.start_time = time.time()
        
        ntrip_thread = threading.Thread(target=self.ntrip_forward_thread, daemon=True)
        rover_thread = threading.Thread(target=self.rover_read_thread, daemon=True)
        display_thread = threading.Thread(target=self.display_thread, daemon=True)
        
        ntrip_thread.start()
        rover_thread.start()
        display_thread.start()
        
        print("\n✅ All threads started. Monitoring RTK status...")
        print("Press Ctrl+C to stop.\n")
        
        try:
            # Wait for threads
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user.")
        finally:
            self.running = False
            time.sleep(0.5)  # Give threads time to finish
            
            try:
                self.ntrip_sock.close()
            except Exception:
                pass
            
            try:
                self.rover_ser.close()
            except Exception:
                pass
            
            elapsed = time.time() - self.start_time
            print(f"\n📊 Final Statistics:")
            print(f"   Runtime: {elapsed:.1f}s")
            print(f"   RTCM received: {self.rtcm_received} bytes")
            print(f"   RTCM sent: {self.rtcm_sent} bytes")
            print(f"   NMEA messages: {self.nmea_received}")
            if elapsed > 0:
                print(f"   Avg RTCM rate: {self.rtcm_received/elapsed:.1f} B/s")
            
            self.write_summary_log(elapsed)
        
        return True
    
    def write_summary_log(self, elapsed: float):
        """Write summary log file."""
        os.makedirs(LOG_DIR, exist_ok=True)
        
        ts = datetime.now()
        log_filename = ts.strftime("rtk_rover_complete_log_%Y%m%d_%H%M%S.txt")
        filename = os.path.join(LOG_DIR, log_filename)
        
        lines = []
        lines.append(f"Time       : {ts.isoformat(sep=' ', timespec='seconds')}")
        lines.append(f"NTRIP Host : {self.config.get('ntrip_host')}:{self.config.get('ntrip_port')}")
        lines.append(f"Mountpoint : {self.config.get('ntrip_mountpoint')}")
        lines.append(f"Rover Port : {self.config.get('rover_port')}")
        lines.append("")
        
        if elapsed > 0:
            lines.append("Result     : COMPLETE")
            lines.append(f"Duration   : {elapsed:.1f} s")
            lines.append(f"RTCM Rx    : {self.rtcm_received} bytes")
            lines.append(f"RTCM Tx    : {self.rtcm_sent} bytes")
            lines.append(f"NMEA Msgs  : {self.nmea_received}")
            lines.append(f"Avg RTCM   : {self.rtcm_received/elapsed:.1f} B/s")
            lines.append("")
            
            # RTCM Validation
            rtcm_status = self.check_rtcm_reception_status(elapsed)
            lines.append("RTCM Reception:")
            lines.append(f"  Status        : {rtcm_status['rtcm_status']}")
            lines.append(f"  Valid Frames  : {rtcm_status['rtcm_frames']}")
            if rtcm_status['rtcm_msg_types']:
                lines.append(f"  RTCM Types    : {', '.join(map(str, rtcm_status['rtcm_msg_types']))}")
            lines.append(f"  Rover Using   : {'Yes' if rtcm_status['rover_using_rtcm'] else 'No'}")
            lines.append("")
            
            if self.data_history:
                best_quality = max((d.get("quality", 0) for d in self.data_history), default=0)
                best_name = QUALITY_NAMES.get(best_quality, "Unknown")
                lines.append(f"Best Fix   : {best_name} (Quality {best_quality})")
                
                if self.initial_quality is not None:
                    initial_name = QUALITY_NAMES.get(self.initial_quality, "Unknown")
                    lines.append(f"Initial Fix: {initial_name} (Quality {self.initial_quality})")
                
                if self.rtk_float_time:
                    lines.append(f"RTK Float  : Achieved in {self.rtk_float_time:.1f}s")
                if self.rtk_fixed_time:
                    lines.append(f"RTK Fixed  : Achieved in {self.rtk_fixed_time:.1f}s")
                
                # Quality changes
                if self.quality_changes:
                    lines.append("")
                    lines.append("Quality Changes:")
                    for change in self.quality_changes:
                        from_name = QUALITY_NAMES.get(change['from'], 'Unknown')
                        to_name = QUALITY_NAMES.get(change['to'], 'Unknown')
                        lines.append(f"  {change['time']:.1f}s: {from_name} → {to_name}")
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            print(f"📝 Summary log written to {filename}")
        except OSError as e:
            print(f"⚠️  Failed to write log file: {e}")


def main():
    """Main entry point."""
    # Load configuration
    config_file = CONFIG_FILE
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                config.update(user_config)
        except Exception as e:
            print(f"⚠️  Error loading config: {e}, using defaults")
    else:
        print(f"⚠️  Config file not found: {config_file}")
        print("   Using default configuration.")
    
    # Create and run
    app = RTKRoverComplete(config)
    success = app.run()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

