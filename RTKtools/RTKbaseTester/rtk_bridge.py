#!/usr/bin/env python3
"""
RTK Bridge - Complete Bidirectional Bridge
===========================================
This script provides a complete bridge between Rover and uPrecise:
- GPS2 data from Rover → TCP port 500 → uPrecise (for RTK processing)
- RTCM data from uPrecise → TCP port 5001 → Rover (for RTK corrections)

Usage:
    py rtk_bridge.py --mavlink-port COM8 --mavlink-baud 9600 --gps-baud 115200 --device 3 --no-exclusive
"""

import argparse
import socket
import threading
import time
import string
import sys
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


def is_all_zero(data):
    for b in data:
        if b != 0:
            return False
    return True


class TcpBridge:
    """TCP bridge that can handle multiple clients on different ports."""
    
    def __init__(self, host, port, name="TCP"):
        self.host = host
        self.port = port
        self.name = name
        self.server = None
        self.client = None
        self.client_lock = threading.Lock()
        self.running = False

    def start(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((self.host, self.port))
        self.server.listen(1)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self):
        self.running = False
        try:
            if self.server:
                self.server.close()
        except Exception:
            pass
        self.close_client()

    def _accept_loop(self):
        while self.running:
            try:
                client, addr = self.server.accept()
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with self.client_lock:
                    self.close_client()
                    self.client = client
                print(f"✅ [{self.name}] Client connected from {addr[0]}:{addr[1]}")
            except Exception:
                time.sleep(0.2)

    def close_client(self):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None

    def get_client(self):
        with self.client_lock:
            return self.client

    def send(self, data):
        """Send data to connected client."""
        client = self.get_client()
        if client:
            try:
                client.sendall(data)
                return True
            except Exception:
                self.close_client()
        return False

    def recv(self, size=4096):
        """Receive data from connected client."""
        client = self.get_client()
        if client:
            try:
                return client.recv(size)
            except Exception:
                self.close_client()
        return None


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


def gps2_to_tcp_loop(mav, device, gps_baud, bridge, request_interval_ms, exclusive, show_gps2, show_hex):
    """Read GPS2 data and forward to TCP bridge."""
    next_request = 0
    last_empty_print = 0
    
    while True:
        now = time.time()
        if now >= next_request:
            flags = FLAG_RESPOND | FLAG_MULTI
            if exclusive:
                flags |= FLAG_EXCLUSIVE
            mav.mav.serial_control_send(
                device,
                flags,
                10,
                gps_baud,
                0,
                b"\x00" * 70,
            )
            next_request = now + (request_interval_ms / 1000.0)

        msg = mav.recv_match(type="SERIAL_CONTROL", blocking=False)
        if msg is not None and getattr(msg, "count", 0) > 0 and msg.device == device:
            data = bytes(msg.data[: msg.count])
            if not is_all_zero(data):
                if show_gps2:
                    print(f"[GPS2 -> TCP] ({len(data)} bytes) {format_ascii(data)}")
                if show_hex:
                    print(f"[GPS2 -> TCP][hex] {data.hex(' ')}")
                
                # Forward to TCP bridge
                bridge.send(data)
            elif now - last_empty_print >= 1.0:
                if show_gps2:
                    print("[GPS2 -> TCP] <no data>")
                last_empty_print = now
        
        time.sleep(0.005)


def tcp_to_gps2_loop(mav, device, gps_baud, bridge, exclusive, show_tcp, show_hex):
    """Read RTCM data from TCP bridge and forward to GPS2."""
    while True:
        data = bridge.recv(2048)
        if data is None:
            time.sleep(0.05)
            continue
        
        if not data:
            bridge.close_client()
            continue
        
        if show_tcp:
            print(f"[TCP -> GPS2] ({len(data)} bytes) {format_ascii(data)}")
        if show_hex:
            hex_str = " ".join(f"{b:02x}" for b in data[:32])
            print(f"[TCP -> GPS2][hex] {hex_str}...")
        
        # Forward to GPS2 via MAVLink
        send_serial_bytes(mav, device, data, gps_baud, exclusive=exclusive)
        
        time.sleep(0.001)


def serial_to_gps2_loop(mav, device, gps_baud, serial_port, serial_baud, exclusive, show_rtcm, show_hex):
    """Read RTCM data from serial port and forward to GPS2."""
    try:
        import serial
    except ImportError:
        print("❌ Error: pyserial not installed. Install with: pip install pyserial")
        return
    
    print(f"📡 Serial Mode: Reading RTCM from {serial_port} at {serial_baud} baud...")
    
    try:
        ser = serial.Serial(serial_port, serial_baud, timeout=1.0)
        print(f"✅ Opened serial port {serial_port}")
    except Exception as e:
        print(f"❌ Failed to open serial port {serial_port}: {e}")
        return
    
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
            
            if show_rtcm:
                print(f"[Serial -> GPS2] ({len(data)} bytes) {format_ascii(data[:50])}...")
            if show_hex:
                hex_str = " ".join(f"{b:02x}" for b in data[:32])
                print(f"[Serial -> GPS2][hex] {hex_str}...")
            
            # Forward to GPS2 via MAVLink
            send_serial_bytes(mav, device, data, gps_baud, exclusive=exclusive)
            stats["bytes_sent"] += len(data)
            
            # Print statistics every 5 seconds
            elapsed = time.time() - stats["last_activity"]
            if elapsed >= 5.0:
                print(f"📊 RTCM Stats: Received={stats['bytes_received']} bytes, Sent={stats['bytes_sent']} bytes")
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
        description="Complete RTK Bridge: GPS2 ↔ uPrecise (bidirectional)"
    )
    parser.add_argument("--mavlink-port", default="COM8", help="MAVLink port (telemetry radio)")
    parser.add_argument("--mavlink-baud", type=int, default=9600, help="MAVLink baud rate")
    parser.add_argument("--gps-baud", type=int, default=115200, help="GPS2 baud rate")
    parser.add_argument("--device", type=int, default=GPS2_DEVICE, help="SERIAL_CONTROL device (3=GPS2)")
    parser.add_argument("--tcp-host", default="127.0.0.1", help="TCP listen host")
    parser.add_argument("--gps-tcp-port", type=int, default=500, help="TCP port for GPS2 data (uPrecise input)")
    parser.add_argument("--rtcm-tcp-port", type=int, default=5001, help="TCP port for RTCM data (uPrecise output via TCP)")
    parser.add_argument("--rtcm-serial-port", help="Serial port for RTCM data (uPrecise output via serial, e.g., COM9)")
    parser.add_argument("--rtcm-serial-baud", type=int, default=115200, help="Serial port baud rate for RTCM (default: 115200)")
    parser.add_argument("--request-interval-ms", type=int, default=50, help="Poll interval for GPS2")
    parser.add_argument("--show-gps2", action="store_true", help="Print GPS2 data received")
    parser.add_argument("--show-rtcm", action="store_true", help="Print RTCM data received")
    parser.add_argument("--show-hex", action="store_true", help="Print data as hex")
    parser.add_argument("--no-exclusive", action="store_true", help="Do not take exclusive port access")
    args = parser.parse_args()

    # Connect to MAVLink
    print(f"Connecting to MAVLink on {args.mavlink_port} at {args.mavlink_baud} baud...")
    mav = mavutil.mavlink_connection(args.mavlink_port, baud=args.mavlink_baud, autoreconnect=True)
    print("Waiting for MAVLink heartbeat...")
    mav.wait_heartbeat()
    print(f"✅ Connected: sysid={mav.target_system} compid={mav.target_component}")

    # Create TCP bridge for GPS2 data (always needed)
    gps_bridge = TcpBridge(args.tcp_host, args.gps_tcp_port, "GPS2→uPrecise")
    gps_bridge.start()
    
    print(f"🌐 TCP Bridge for GPS2 data listening on {args.tcp_host}:{args.gps_tcp_port}")
    print(f"   Configure uPrecise to connect as TCP client to receive GPS2 data")
    
    exclusive = not args.no_exclusive

    # Start thread for GPS2 → TCP forwarding
    threading.Thread(
        target=gps2_to_tcp_loop,
        args=(mav, args.device, args.gps_baud, gps_bridge, args.request_interval_ms, exclusive, args.show_gps2, args.show_hex),
        daemon=True
    ).start()
    
    # Handle RTCM output: TCP or Serial
    if args.rtcm_serial_port:
        # Serial mode: Read RTCM from serial port
        print(f"📡 Serial mode for RTCM: Reading from {args.rtcm_serial_port} at {args.rtcm_serial_baud} baud")
        print(f"   Configure uPrecise to output RTCM to serial port {args.rtcm_serial_port}")
        print()
        
        threading.Thread(
            target=serial_to_gps2_loop,
            args=(mav, args.device, args.gps_baud, args.rtcm_serial_port, args.rtcm_serial_baud, exclusive, args.show_rtcm, args.show_hex),
            daemon=True
        ).start()
    else:
        # TCP mode: Read RTCM from TCP bridge
        rtcm_bridge = TcpBridge(args.tcp_host, args.rtcm_tcp_port, "uPrecise→Rover")
        rtcm_bridge.start()
        
        print(f"🌐 TCP Bridge for RTCM data listening on {args.tcp_host}:{args.rtcm_tcp_port}")
        print(f"   Configure uPrecise to output RTCM to this TCP port")
        print()
        
        threading.Thread(
            target=tcp_to_gps2_loop,
            args=(mav, args.device, args.gps_baud, rtcm_bridge, exclusive, args.show_rtcm, args.show_hex),
            daemon=True
        ).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping bridge...")
        gps_bridge.stop()
        if not args.rtcm_serial_port:
            rtcm_bridge.stop()


if __name__ == "__main__":
    main()
