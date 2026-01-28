#!/usr/bin/env python3
"""
RTCM to Rover Forwarder
========================
This script forwards RTCM correction data from uPrecise to the rover via MAVLink.

It can work in two modes:
1. TCP Mode: Connect to uPrecise's RTCM TCP output and forward to rover
2. Serial Mode: Read from a serial port where uPrecise outputs RTCM and forward to rover

Usage:
    # TCP mode (if uPrecise outputs RTCM to TCP):
    py rtcm_to_rover.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --tcp-port 5001
    
    # Serial mode (if uPrecise outputs RTCM to serial port):
    py rtcm_to_rover.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --serial-port COM9 --serial-baud 115200
"""

import argparse
import socket
import sys
import threading
import time
import string
from pymavlink import mavutil

GPS2_DEVICE = 3  # MAVLink SERIAL_CONTROL_DEV_GPS2

FLAG_REPLY = 1
FLAG_RESPOND = 2
FLAG_EXCLUSIVE = 4
FLAG_BLOCKING = 8
FLAG_MULTI = 16


def format_ascii(data):
    printable = set(string.printable)
    return "".join(chr(b) if chr(b) in printable else "." for b in data)


def send_serial_bytes(mav, device, data, baud, exclusive):
    """Send data to GPS2 via MAVLink SERIAL_CONTROL."""
    offset = 0
    flags = FLAG_EXCLUSIVE if exclusive else 0
    while offset < len(data):
        chunk = data[offset:offset + 70]
        count = len(chunk)
        if count < 70:
            chunk = chunk + b"\x00" * (70 - count)
        mav.mav.serial_control_send(
            device,
            flags,
            0,
            baud,
            count,
            chunk,
        )
        offset += count
        time.sleep(0.01)


def tcp_mode(mav, device, gps_baud, tcp_port, exclusive, show_data, show_hex):
    """Forward RTCM data from TCP connection to rover."""
    print(f"🌐 TCP Mode: Listening on 127.0.0.1:{tcp_port} for RTCM data from uPrecise...")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", tcp_port))
    server.listen(1)
    
    stats = {
        "bytes_received": 0,
        "bytes_sent": 0,
        "last_activity": time.time(),
    }
    
    try:
        while True:
            print("Waiting for uPrecise RTCM output connection...")
            client, addr = server.accept()
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print(f"✅ Connected to uPrecise RTCM output from {addr[0]}:{addr[1]}")
            
            try:
                while True:
                    data = client.recv(4096)
                    if not data:
                        print("⚠️  uPrecise RTCM output connection closed")
                        break
                    
                    stats["bytes_received"] += len(data)
                    stats["last_activity"] = time.time()
                    
                    if show_data:
                        print(f"[RTCM -> Rover] ({len(data)} bytes) {format_ascii(data[:50])}...")
                    if show_hex:
                        hex_str = " ".join(f"{b:02x}" for b in data[:32])
                        print(f"[RTCM -> Rover][hex] {hex_str}...")
                    
                    # Forward to rover via MAVLink
                    send_serial_bytes(mav, device, data, gps_baud, exclusive=exclusive)
                    stats["bytes_sent"] += len(data)
                    
                    # Print statistics every 5 seconds
                    elapsed = time.time() - stats["last_activity"]
                    if elapsed >= 5.0:
                        print(f"📊 Stats: Received={stats['bytes_received']} bytes, Sent={stats['bytes_sent']} bytes")
                        stats["last_activity"] = time.time()
                        
            except Exception as e:
                print(f"❌ Error in TCP connection: {e}")
            finally:
                try:
                    client.close()
                except Exception:
                    pass
                    
    except KeyboardInterrupt:
        print("\n🛑 Stopping TCP server...")
    finally:
        try:
            server.close()
        except Exception:
            pass


def serial_mode(mav, device, gps_baud, serial_port, serial_baud, exclusive, show_data, show_hex):
    """Forward RTCM data from serial port to rover."""
    try:
        import serial
    except ImportError:
        print("❌ Error: pyserial not installed. Install with: pip install pyserial")
        sys.exit(1)
    
    print(f"📡 Serial Mode: Reading RTCM from {serial_port} at {serial_baud} baud...")
    
    try:
        ser = serial.Serial(serial_port, serial_baud, timeout=1.0)
        print(f"✅ Opened serial port {serial_port}")
    except Exception as e:
        print(f"❌ Failed to open serial port {serial_port}: {e}")
        sys.exit(1)
    
    stats = {
        "bytes_received": 0,
        "bytes_sent": 0,
        "last_activity": time.time(),
    }
    
    try:
        while True:
            data = ser.read(4096)
            if not data:
                time.sleep(0.1)
                continue
            
            stats["bytes_received"] += len(data)
            stats["last_activity"] = time.time()
            
            if show_data:
                print(f"[RTCM -> Rover] ({len(data)} bytes) {format_ascii(data[:50])}...")
            if show_hex:
                hex_str = " ".join(f"{b:02x}" for b in data[:32])
                print(f"[RTCM -> Rover][hex] {hex_str}...")
            
            # Forward to rover via MAVLink
            send_serial_bytes(mav, device, data, gps_baud, exclusive=exclusive)
            stats["bytes_sent"] += len(data)
            
            # Print statistics every 5 seconds
            elapsed = time.time() - stats["last_activity"]
            if elapsed >= 5.0:
                print(f"📊 Stats: Received={stats['bytes_received']} bytes, Sent={stats['bytes_sent']} bytes")
                stats["last_activity"] = time.time()
                
    except KeyboardInterrupt:
        print("\n🛑 Stopping serial reader...")
    finally:
        try:
            ser.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Forward RTCM correction data from uPrecise to rover via MAVLink"
    )
    parser.add_argument("--mavlink-port", default="COM8", help="MAVLink port (telemetry radio)")
    parser.add_argument("--mavlink-baud", type=int, default=9600, help="MAVLink baud rate")
    parser.add_argument("--gps-baud", type=int, default=115200, help="GPS2 baud rate")
    parser.add_argument("--device", type=int, default=GPS2_DEVICE, help="SERIAL_CONTROL device (3=GPS2)")
    parser.add_argument("--no-exclusive", action="store_true", help="Do not take exclusive port access")
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--tcp-port", type=int, help="TCP mode: Port to listen for RTCM data from uPrecise")
    mode_group.add_argument("--serial-port", help="Serial mode: Serial port where uPrecise outputs RTCM")
    
    parser.add_argument("--serial-baud", type=int, default=115200, help="Serial port baud rate (for serial mode)")
    parser.add_argument("--show-data", action="store_true", help="Print RTCM data being forwarded")
    parser.add_argument("--show-hex", action="store_true", help="Print RTCM data as hex")
    
    args = parser.parse_args()
    
    # Connect to MAVLink
    # Use the same format as uPrecise_forward.py (direct port name)
    print(f"Connecting to MAVLink on {args.mavlink_port} at {args.mavlink_baud} baud...")
    mav = mavutil.mavlink_connection(args.mavlink_port, baud=args.mavlink_baud, autoreconnect=True)
    print("Waiting for MAVLink heartbeat...")
    mav.wait_heartbeat()
    print(f"✅ Connected: sysid={mav.target_system} compid={mav.target_component}")
    
    exclusive = not args.no_exclusive
    
    # Run in appropriate mode
    if args.tcp_port:
        tcp_mode(mav, args.device, args.gps_baud, args.tcp_port, exclusive, args.show_data, args.show_hex)
    elif args.serial_port:
        serial_mode(mav, args.device, args.gps_baud, args.serial_port, args.serial_baud, exclusive, args.show_data, args.show_hex)


if __name__ == "__main__":
    main()
