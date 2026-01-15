#!/usr/bin/env python3
"""
RTK Rover Tester - Test RTK fix status and GNSS data from rover device
Connects to rover via Bluetooth (serial port) and displays real-time RTK status
"""

import json
import os
import serial
import serial.tools.list_ports
import sys
import time
from datetime import datetime
from typing import Dict, Optional, Tuple


# Log directory path
LOG_DIR = r"C:\Users\oxpas\Documents\GitHub\DroneDevTools\RTKtools\RTKbaseTester\logs"

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rover_config.json")

# Default configuration
DEFAULT_CONFIG = {
    "port": "COM3",  # Will auto-detect if not specified
    "baudrate": 115200,
    "timeout": 1.0,
    "auto_detect": True,
    "device_name": "XTRTK",  # Part of device name to search for
}


# RTK Fix Quality Codes (from NMEA GNGGA/GPGGA)
QUALITY_NO_FIX = 0
QUALITY_GPS = 1
QUALITY_DGPS = 2
QUALITY_PPS = 3
QUALITY_RTK_FIXED = 4  # RTK Fixed (cm-level accuracy)
QUALITY_RTK_FLOAT = 5  # RTK Float (dm-level accuracy)
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


def load_config(config_path: str = CONFIG_FILE) -> Dict:
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


def parse_nmea_gga(line: str) -> Optional[Dict]:
    """Parse NMEA GNGGA or GPGGA sentence."""
    if not (line.startswith("$GNGGA") or line.startswith("$GPGGA")):
        return None
    
    try:
        parts = line.split(",")
        if len(parts) < 15:
            return None
        
        # Extract fields
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
        
        # Parse latitude (DDMM.MMMMM format)
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
        
        # Parse longitude (DDDMM.MMMMM format)
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
        
        # Parse time (HHMMSS.SSS format)
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
    except (ValueError, IndexError) as e:
        return None


def parse_nmea_rmc(line: str) -> Optional[Dict]:
    """Parse NMEA GNRMC or GPRMC sentence for speed and track."""
    if not (line.startswith("$GNRMC") or line.startswith("$GPRMC")):
        return None
    
    try:
        parts = line.split(",")
        if len(parts) < 12:
            return None
        
        speed_knots = float(parts[7]) if parts[7] else 0.0
        track = float(parts[8]) if parts[8] else 0.0
        date_str = parts[9] if parts[9] else None
        
        return {
            "speed_knots": speed_knots,
            "speed_ms": speed_knots * 0.514444,  # Convert knots to m/s
            "track": track,
            "date": date_str,
        }
    except (ValueError, IndexError):
        return None


def parse_nmea_gsa(line: str) -> Optional[Dict]:
    """Parse NMEA GNGSA or GPGSA sentence for DOP values."""
    if not (line.startswith("$GNGSA") or line.startswith("$GPGSA")):
        return None
    
    try:
        parts = line.split(",")
        if len(parts) < 17:
            return None
        
        mode = parts[1] if parts[1] else None
        fix_type = int(parts[2]) if parts[2] else 1  # 1=no fix, 2=2D, 3=3D
        pdop = float(parts[15]) if parts[15] else 0.0
        hdop = float(parts[16]) if parts[16] else 0.0
        vdop = float(parts[17]) if len(parts) > 17 and parts[17] else 0.0
        
        return {
            "mode": mode,
            "fix_type": fix_type,
            "pdop": pdop,
            "hdop": hdop,
            "vdop": vdop,
        }
    except (ValueError, IndexError):
        return None


def connect_rover(port: str, baudrate: int = 115200, timeout: float = 1.0) -> Optional[serial.Serial]:
    """Connect to rover device via serial port."""
    try:
        print(f"🔌 Connecting to {port} at {baudrate} baud...")
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
        )
        print(f"✅ Connected successfully!")
        return ser
    except serial.SerialException as e:
        print(f"❌ Failed to connect: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None


def display_status(data: Dict, start_time: float, best_quality: int = 0, rtk_float_time: Optional[float] = None, rtk_fixed_time: Optional[float] = None):
    """Display current RTK status and GNSS data."""
    elapsed = time.time() - start_time
    
    # Clear screen (works on Windows and Unix)
    os.system("cls" if os.name == "nt" else "clear")
    
    print("=" * 70)
    print("RTK Rover Status Monitor")
    print("=" * 70)
    print(f"Runtime: {elapsed:.1f}s")
    print()
    
    # RTK Fix Status
    quality = data.get("quality", QUALITY_NO_FIX)
    quality_name = data.get("quality_name", "Unknown")
    
    # Color coding for status
    if quality == QUALITY_RTK_FIXED:
        status_icon = "🟢"
        status_text = f"RTK FIXED (cm-level)"
        rtk_hint = ""
        if rtk_fixed_time:
            print(f"⏱️  RTK Fixed achieved in {rtk_fixed_time:.1f}s")
    elif quality == QUALITY_RTK_FLOAT:
        status_icon = "🟡"
        status_text = f"RTK FLOAT (dm-level)"
        rtk_hint = "💡 RTK Float - Waiting for RTK Fixed convergence..."
        if rtk_float_time:
            print(f"⏱️  RTK Float achieved in {rtk_float_time:.1f}s")
    elif quality == QUALITY_GPS:
        status_icon = "🔵"
        status_text = "GPS Fix"
        rtk_hint = "⚠️  GPS mode - Ensure rover is receiving RTCM data from NTRIP base station"
    elif quality == QUALITY_DGPS:
        status_icon = "🔵"
        status_text = "DGPS Fix"
        rtk_hint = "⚠️  DGPS mode - Check RTCM data connection"
    else:
        status_icon = "🔴"
        status_text = "No Fix"
        rtk_hint = "❌ No fix - Check antenna and satellite visibility"
    
    print(f"Status: {status_icon} {status_text}")
    print(f"Quality Code: {quality} ({quality_name})")
    
    # Show best quality achieved
    if best_quality > quality:
        best_name = QUALITY_NAMES.get(best_quality, "Unknown")
        print(f"Best Achieved: {best_name} (Quality {best_quality})")
    
    if rtk_hint:
        print(f"\n{rtk_hint}")
    print()
    
    # Position
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is not None and lon is not None:
        print(f"Position: {lat:.8f}°N, {lon:.8f}°E")
    else:
        print("Position: No data")
    
    # Altitude
    altitude = data.get("altitude")
    if altitude is not None:
        print(f"Altitude: {altitude:.2f} m (MSL)")
        geoid_sep = data.get("geoid_sep", 0)
        if geoid_sep:
            print(f"Geoid Separation: {geoid_sep:.2f} m")
    
    # Time
    utc_time = data.get("time")
    if utc_time:
        print(f"UTC Time: {utc_time}")
    
    # Satellites
    num_sats = data.get("num_sats", 0)
    print(f"Satellites: {num_sats}")
    
    # DOP values
    hdop = data.get("hdop", 0.0)
    pdop = data.get("pdop", 0.0)
    vdop = data.get("vdop", 0.0)
    if hdop > 0:
        print(f"HDOP: {hdop:.2f}")
    if pdop > 0:
        print(f"PDOP: {pdop:.2f}")
    if vdop > 0:
        print(f"VDOP: {vdop:.2f}")
    
    # Speed and Track
    speed_ms = data.get("speed_ms")
    track = data.get("track")
    if speed_ms is not None:
        print(f"Speed: {speed_ms:.2f} m/s ({speed_ms * 3.6:.2f} km/h)")
    if track is not None:
        print(f"Track: {track:.1f}°")
    
    print()
    print("Press Ctrl+C to stop")
    print("=" * 70)


def write_summary_log(port: str, config: Dict, data_history: list, error: Optional[str] = None):
    """Write summary log file."""
    os.makedirs(LOG_DIR, exist_ok=True)
    
    ts = datetime.now()
    log_filename = ts.strftime("rover_log_%Y%m%d_%H%M%S.txt")
    filename = os.path.join(LOG_DIR, log_filename)
    
    lines = []
    lines.append(f"Time       : {ts.isoformat(sep=' ', timespec='seconds')}")
    lines.append(f"Port       : {port}")
    lines.append(f"Baudrate   : {config.get('baudrate', 'N/A')}")
    lines.append("")
    
    if data_history:
        # Find best fix achieved
        best_quality = max((d.get("quality", 0) for d in data_history), default=0)
        best_quality_name = QUALITY_NAMES.get(best_quality, "Unknown")
        
        lines.append(f"Best Fix   : {best_quality_name} (Quality {best_quality})")
        lines.append(f"Total Updates: {len(data_history)}")
        lines.append("")
        
        # Count fix types
        fix_counts = {}
        for d in data_history:
            q = d.get("quality", 0)
            name = QUALITY_NAMES.get(q, "Unknown")
            fix_counts[name] = fix_counts.get(name, 0) + 1
        
        lines.append("Fix Type Distribution:")
        for fix_type, count in sorted(fix_counts.items()):
            lines.append(f"  {fix_type}: {count}")
        lines.append("")
        
        # Last known position
        last_data = data_history[-1]
        lat = last_data.get("latitude")
        lon = last_data.get("longitude")
        if lat is not None and lon is not None:
            lines.append(f"Last Position: {lat:.8f}°N, {lon:.8f}°E")
        if last_data.get("altitude"):
            lines.append(f"Last Altitude: {last_data.get('altitude'):.2f} m")
    else:
        lines.append("Result     : NO DATA RECEIVED")
    
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
    config = load_config()
    
    # Determine port
    port = config.get("port")
    if config.get("auto_detect", True) and (not port or port == "AUTO"):
        device_name = config.get("device_name", "XTRTK")
        detected_port = find_rover_port(device_name)
        if detected_port:
            port = detected_port
        else:
            print("\n❌ Could not auto-detect rover device.")
            print("   Please specify port manually in config file or connect device.")
            sys.exit(1)
    
    if not port:
        print("❌ No port specified. Please set 'port' in config file.")
        sys.exit(1)
    
    # Connect to rover
    ser = connect_rover(
        port=port,
        baudrate=config.get("baudrate", 115200),
        timeout=config.get("timeout", 1.0),
    )
    
    if not ser:
        sys.exit(1)
    
    print("\n📡 Reading GNSS data from rover...")
    print("Press Ctrl+C to stop.\n")
    time.sleep(1)
    
    # Data storage
    current_data = {}
    data_history = []
    start_time = time.time()
    last_display = 0.0
    display_interval = 0.5  # Update display every 0.5 seconds
    best_quality = QUALITY_NO_FIX
    rtk_float_time = None
    rtk_fixed_time = None
    
    try:
        while True:
            try:
                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                
                # Parse different NMEA sentence types
                gga_data = parse_nmea_gga(line)
                if gga_data:
                    current_data.update(gga_data)
                    quality = gga_data.get("quality", QUALITY_NO_FIX)
                    if quality > best_quality:
                        best_quality = quality
                        # Track RTK convergence times
                        elapsed = time.time() - start_time
                        if quality == QUALITY_RTK_FLOAT and rtk_float_time is None:
                            rtk_float_time = elapsed
                        if quality == QUALITY_RTK_FIXED and rtk_fixed_time is None:
                            rtk_fixed_time = elapsed
                    data_history.append(current_data.copy())
                
                rmc_data = parse_nmea_rmc(line)
                if rmc_data:
                    current_data.update(rmc_data)
                
                gsa_data = parse_nmea_gsa(line)
                if gsa_data:
                    current_data.update(gsa_data)
                
                # Update display periodically
                now = time.time()
                if now - last_display >= display_interval:
                    display_status(current_data, start_time, best_quality, rtk_float_time, rtk_fixed_time)
                    last_display = now
                    
            except serial.SerialException as e:
                print(f"\n❌ Serial error: {e}")
                break
            except KeyboardInterrupt:
                print("\n\nInterrupted by user.")
                break
            except Exception as e:
                print(f"\n⚠️  Error parsing data: {e}")
                continue
    
    finally:
        ser.close()
        print("Connection closed.")
        write_summary_log(port, config, data_history)


if __name__ == "__main__":
    main()

