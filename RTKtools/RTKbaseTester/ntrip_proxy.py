#!/usr/bin/env python3
"""
NTRIP Proxy Server
==================
This script acts as a bridge between an NTRIP caster and uPrecise (or other NTRIP clients).
It connects to the remote NTRIP caster and serves RTCM data locally via NTRIP protocol.

Usage:
    python ntrip_proxy.py
    
Configuration:
    Loads settings from config.json in the same directory.
    Local server defaults to 127.0.0.1:8888 (configurable).
"""

import argparse
import base64
import json
import os
import socket
import sys
import threading
import time
from collections import Counter
from typing import Dict, Optional, Tuple
from datetime import datetime


# Default configuration
DEFAULT_CONFIG = {
    "host": "192.168.137.172",
    "port": 2101,
    "mountpoint": "RTCM4",
    "username": "XTRTK",
    "password": "123456",
    "rtcm_messages": [1074, 1084, 1094, 1124, 1005, 1006, 1033],
    "receiver_option": "",
    "debug": True,
    "local_host": "127.0.0.1",
    "local_port": 8888,
}

# Configuration file path
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


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


def build_ntrip_request(host: str, mountpoint: str, user: str, password: str, debug: bool = False) -> bytes:
    """Build a minimal NTRIP v2 GET request."""
    auth = base64.b64encode(f"{user}:{password}".encode("ascii")).decode("ascii")
    lines = [
        f"GET /{mountpoint} HTTP/1.0",
        f"Host: {host}",
        "User-Agent: NTRIP PythonClient/1.0",
        f"Authorization: Basic {auth}",
        "Ntrip-Version: Ntrip/2.0",
        "Connection: close",
        "",
        "",
    ]
    request = "\r\n".join(lines).encode("ascii")

    if debug:
        print("---- NTRIP request being sent ----")
        print(request.decode("ascii", errors="replace"))
        print("----------------------------------")

    return request


def connect_ntrip(
    host: str,
    port: int,
    mountpoint: str,
    user: str,
    password: str,
    debug: bool = False,
) -> Tuple[socket.socket, bytes]:
    """Connect to NTRIP caster and return socket + initial data."""
    addr = (host, port)
    print(f"Connecting to NTRIP caster {host}:{port}, mountpoint '{mountpoint}'...")

    try:
        sock = socket.create_connection(addr, timeout=10.0)
    except OSError as e:
        if debug:
            print(f"[DEBUG] socket.create_connection error: {e}")
        raise

    sock.settimeout(30.0)

    request = build_ntrip_request(host, mountpoint, user, password, debug=debug)
    if debug:
        print("[DEBUG] Sending NTRIP request...")
    sock.sendall(request)

    # Read HTTP/NTRIP response header
    header = b""
    max_header = 64 * 1024
    if debug:
        print("[DEBUG] Starting to read response header from server...")
    
    while len(header) < max_header:
        try:
            chunk = sock.recv(1024)
        except socket.timeout:
            try:
                text = header.decode("iso-8859-1", errors="replace")
            except Exception:
                text = ""
            if "ICY 200" in text or " 200 " in text:
                if debug:
                    print("[DEBUG] Timeout while reading header, but 200 status detected – proceeding.")
                break
            if debug:
                print(f"[DEBUG] Timeout while reading header; header length: {len(header)} bytes")
            raise ConnectionError("Timed out while waiting for NTRIP response header.")

        if not chunk:
            if debug:
                print(f"[DEBUG] Socket closed while reading header. Header length: {len(header)} bytes")
            break

        header += chunk
        if debug:
            print(f"[DEBUG] Received header chunk: {len(chunk)} bytes, total: {len(header)} bytes")

        if b"\r\n\r\n" in header:
            if debug:
                print("[DEBUG] Found '\\r\\n\\r\\n' – end of HTTP header.")
            break

        try:
            text = header.decode("iso-8859-1", errors="replace")
        except Exception:
            text = ""
        if ("ICY 200" in text or " 200 " in text) and len(header) > 128:
            if debug:
                print("[DEBUG] Detected '200' status without explicit '\\r\\n\\r\\n'; assuming start of data.")
            break

    if debug:
        print("[DEBUG] Finished reading header (may include some data bytes).")

    return sock, header


def check_response_header(header: bytes) -> Tuple[bytes, bytes]:
    """Validate HTTP/NTRIP response status and split header/data."""
    header_end = header.find(b"\r\n\r\n")
    if header_end != -1:
        header_end += 4
    
    if header_end == -1:
        status_end = header.find(b"\r\n")
        if status_end == -1:
            status_end = header.find(b"\n")
        if status_end != -1:
            data_start = header.find(b"\xD3", status_end + 2)
            if data_start != -1:
                header_end = data_start
            else:
                for i in range(status_end + 2, min(len(header), status_end + 200)):
                    if header[i] < 32 and header[i] not in (9, 10, 13):
                        header_end = i
                        break
    
    if header_end == -1:
        header_end = len(header)
    
    header_text_part = header[:header_end]
    binary_data_part = header[header_end:] if header_end < len(header) else b""
    
    header_text_decoded = header_text_part.decode("iso-8859-1", errors="replace")
    status_line = header_text_decoded.split("\r\n", 1)[0]
    if "\n" in status_line and "\r\n" not in status_line:
        status_line = status_line.split("\n", 1)[0]

    print("---- Header preview ----")
    preview_lines = header_text_decoded.replace("\r", "").split("\n")
    for line in preview_lines[:10]:
        if line.strip():
            print(line)
    if binary_data_part:
        print(f"... ({len(binary_data_part)} bytes of RTCM3 binary data follows)")
    print("------------------------")

    print("Server response:", status_line)

    if status_line.startswith("ICY 200") or " 200 " in status_line:
        print("✅ NTRIP stream started successfully.\n")
        return header_text_part, binary_data_part

    if "401" in status_line or "403" in status_line:
        raise ConnectionError("Authentication failed (401/403). Check username/password.")
    if "404" in status_line:
        raise ConnectionError("Mountpoint not found (404). Check mountpoint name.")
    if "500" in status_line:
        raise ConnectionError("Server internal error (500).")

    raise ConnectionError(f"Unexpected response from server: {status_line}")


def build_ntrip_response() -> bytes:
    """Build NTRIP server response (ICY 200 OK)."""
    response = "ICY 200 OK\r\n\r\n"
    return response.encode("ascii")


class ClientManager:
    """Manages connected clients and broadcasts RTCM data to them."""
    
    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()
    
    def add_client(self, client_sock: socket.socket, addr: Tuple[str, int]):
        """Add a client to the broadcast list."""
        with self.lock:
            self.clients.append((client_sock, addr))
        print(f"📡 Client connected from {addr[0]}:{addr[1]} (total: {len(self.clients)})")
    
    def remove_client(self, client_sock: socket.socket, addr: Tuple[str, int]):
        """Remove a client from the broadcast list."""
        with self.lock:
            try:
                self.clients.remove((client_sock, addr))
            except ValueError:
                pass
        print(f"🔌 Client {addr[0]}:{addr[1]} disconnected (remaining: {len(self.clients)})")
    
    def broadcast(self, data: bytes):
        """Broadcast data to all connected clients."""
        with self.lock:
            disconnected = []
            for client_sock, addr in self.clients:
                try:
                    client_sock.sendall(data)
                except Exception:
                    disconnected.append((client_sock, addr))
            
            # Remove disconnected clients
            for client_sock, addr in disconnected:
                try:
                    self.clients.remove((client_sock, addr))
                except ValueError:
                    pass
                try:
                    client_sock.close()
                except Exception:
                    pass
    
    def get_count(self):
        """Get number of connected clients."""
        with self.lock:
            return len(self.clients)


def handle_client(client_sock: socket.socket, addr: Tuple[str, int], client_manager: ClientManager, initial_data: bytes, stats: Dict):
    """Handle a client connection - send initial response and add to broadcast list."""
    try:
        # Read client request (NTRIP GET request)
        client_sock.settimeout(5.0)
        request = client_sock.recv(4096)
        
        if request:
            request_text = request.decode("ascii", errors="replace")
            print(f"📥 Client {addr[0]}:{addr[1]} request:\n{request_text[:200]}")
        
        # Send NTRIP response
        response = build_ntrip_response()
        client_sock.sendall(response)
        print(f"✅ Sent NTRIP response to {addr[0]}:{addr[1]}")
        
        # Send initial data if available
        if initial_data:
            try:
                client_sock.sendall(initial_data)
                with stats["lock"]:
                    stats["bytes_sent"] += len(initial_data)
            except Exception as e:
                print(f"⚠️  Error sending initial data to {addr[0]}:{addr[1]}: {e}")
                return
        
        # Add client to broadcast list
        client_manager.add_client(client_sock, addr)
        
        # Keep connection alive (client will receive data via broadcast)
        client_sock.settimeout(None)
        while True:
            # Just keep the connection alive - data is sent via broadcast
            try:
                data = client_sock.recv(1)
                if not data:
                    break
            except Exception:
                break
                
    except Exception as e:
        print(f"❌ Error handling client {addr[0]}:{addr[1]}: {e}")
    finally:
        client_manager.remove_client(client_sock, addr)
        try:
            client_sock.close()
        except Exception:
            pass


def forward_ntrip_stream(ntrip_sock: socket.socket, initial_data: bytes, client_manager: ClientManager, stats: Dict):
    """Background thread to read from NTRIP caster and broadcast to all clients."""
    # Send initial data to any existing clients
    if initial_data:
        client_manager.broadcast(initial_data)
        with stats["lock"]:
            stats["bytes_sent"] += len(initial_data)
    
    while True:
        try:
            chunk = ntrip_sock.recv(4096)
            if not chunk:
                print("⚠️  NTRIP caster connection closed.")
                break
            
            with stats["lock"]:
                stats["bytes_received"] += len(chunk)
                stats["last_activity"] = time.time()
            
            # Broadcast to all clients
            client_manager.broadcast(chunk)
            with stats["lock"]:
                stats["bytes_sent"] += len(chunk)
                
        except socket.timeout:
            continue
        except OSError as e:
            print(f"❌ NTRIP socket error: {e}")
            break


def main():
    parser = argparse.ArgumentParser(
        description="NTRIP Proxy Server - Bridge between NTRIP caster and uPrecise"
    )
    parser.add_argument("--local-host", help="Local server host (default: from config)")
    parser.add_argument("--local-port", type=int, help="Local server port (default: from config)")
    parser.add_argument("--config", help="Path to config.json file")
    args = parser.parse_args()

    # Load configuration
    config_path = args.config if args.config else CONFIG_FILE
    config = load_config(config_path)
    
    # Extract configuration
    ntrip_host = config["host"]
    ntrip_port = config["port"]
    mountpoint = config["mountpoint"]
    username = config["username"]
    password = config["password"]
    debug = config.get("debug", True)
    
    local_host = args.local_host if args.local_host else config.get("local_host", "127.0.0.1")
    local_port = args.local_port if args.local_port else config.get("local_port", 8888)
    
    # Display configuration
    print("=" * 60)
    print("NTRIP Proxy Server Configuration")
    print("=" * 60)
    print(f"NTRIP Caster  : {ntrip_host}:{ntrip_port}")
    print(f"Mountpoint    : {mountpoint}")
    print(f"Username      : {username}")
    print(f"Password      : {'*' * len(password)}")
    print(f"Local Server  : {local_host}:{local_port}")
    print("=" * 60)
    print()

    # Connect to NTRIP caster
    try:
        ntrip_sock, header = connect_ntrip(
            host=ntrip_host,
            port=ntrip_port,
            mountpoint=mountpoint,
            user=username,
            password=password,
            debug=debug,
        )
    except (OSError, ConnectionError) as e:
        print(f"❌ Failed to connect to NTRIP caster: {e}")
        sys.exit(1)

    try:
        header_text, binary_data = check_response_header(header)
    except ConnectionError as e:
        print(f"❌ {e}")
        ntrip_sock.close()
        sys.exit(1)

    # Statistics
    stats = {
        "bytes_received": 0,
        "bytes_sent": 0,
        "last_activity": time.time(),
        "lock": threading.Lock(),
    }

    # Client manager for broadcasting
    client_manager = ClientManager()

    # Create local NTRIP server
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((local_host, local_port))
    server_sock.listen(5)
    
    print(f"🌐 Local NTRIP server listening on {local_host}:{local_port}")
    print(f"   Configure uPrecise to connect to: {local_host}:{local_port}")
    print(f"   Mountpoint: {mountpoint}")
    print(f"   Username: {username}")
    print(f"   Password: {password}")
    print()
    print("Press Ctrl+C to stop.\n")

    # Start background thread to read from NTRIP caster and broadcast to clients
    forward_thread = threading.Thread(
        target=forward_ntrip_stream,
        args=(ntrip_sock, binary_data, client_manager, stats),
        daemon=True
    )
    forward_thread.start()

    # Accept client connections
    try:
        while True:
            try:
                client_sock, addr = server_sock.accept()
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                
                # Handle client in a separate thread
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_sock, addr, client_manager, binary_data, stats),
                    daemon=True
                )
                client_thread.start()
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"⚠️  Error accepting client: {e}")
                time.sleep(0.1)
                
    except KeyboardInterrupt:
        print("\n🛑 Stopping server...")
    finally:
        try:
            server_sock.close()
            ntrip_sock.close()
        except Exception:
            pass
        
        with stats["lock"]:
            print(f"\n📊 Statistics:")
            print(f"   Bytes received from caster: {stats['bytes_received']}")
            print(f"   Bytes sent to clients: {stats['bytes_sent']}")
        
        print("Server stopped.")


if __name__ == "__main__":
    main()
