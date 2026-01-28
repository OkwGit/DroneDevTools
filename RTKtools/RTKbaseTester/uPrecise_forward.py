#!/usr/bin/env python3
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
    def __init__(self, host, port):
        self.host = host
        self.port = port
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
                client, _addr = self.server.accept()
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                with self.client_lock:
                    self.close_client()
                    self.client = client
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


def send_serial_bytes(mav, device, data, baud, exclusive):
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


def main():
    parser = argparse.ArgumentParser(
        description="Forward GPS2 (SERIAL4) over MAVLink to uPrecise via TCP."
    )
    parser.add_argument("--mavlink-port", default="COM14", help="MAVLink port (telemetry radio)")
    parser.add_argument("--mavlink-baud", type=int, default=57600, help="MAVLink baud rate")
    parser.add_argument("--gps-baud", type=int, default=115200, help="GPS2 baud rate")
    parser.add_argument("--device", type=int, default=GPS2_DEVICE, help="SERIAL_CONTROL device (3=GPS2)")
    parser.add_argument("--tcp-host", default="127.0.0.1", help="TCP listen host")
    parser.add_argument("--tcp-port", type=int, default=500, help="TCP listen port")
    parser.add_argument("--request-interval-ms", type=int, default=50, help="Poll interval")
    parser.add_argument("--show-gps2", action="store_true", help="Print GPS2 data received")
    parser.add_argument("--show-tcp", action="store_true", help="Print TCP data sent to GPS2")
    parser.add_argument("--show-hex", action="store_true", help="Print GPS2 data as hex")
    parser.add_argument("--show-meta", action="store_true", help="Print SERIAL_CONTROL metadata")
    parser.add_argument("--no-exclusive", action="store_true", help="Do not take exclusive port access")
    parser.add_argument("--send", action="append", help="Send raw command to GPS2 (can repeat)")
    parser.add_argument("--send-file", help="Send commands from file (one per line)")
    args = parser.parse_args()

    mav = mavutil.mavlink_connection(args.mavlink_port, baud=args.mavlink_baud, autoreconnect=True)
    print("Waiting for MAVLink heartbeat...")
    mav.wait_heartbeat()
    print(f"Connected: sysid={mav.target_system} compid={mav.target_component}")

    bridge = TcpBridge(args.tcp_host, args.tcp_port)
    bridge.start()
    print(f"TCP server listening on {args.tcp_host}:{args.tcp_port}")

    def queue_commands():
        commands = []
        if args.send_file:
            try:
                with open(args.send_file, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        commands.append(line)
            except Exception as exc:
                print(f"Failed to read --send-file: {exc}")
                sys.exit(1)
        if args.send:
            commands.extend(args.send)
        return commands

    def send_commands():
        commands = queue_commands()
        if not commands:
            return
        time.sleep(1.0)
        for cmd in commands:
            payload = cmd
            if not payload.endswith("\r\n"):
                payload += "\r\n"
            print(f"[SEND -> GPS2] {cmd}")
            send_serial_bytes(mav, args.device, payload.encode("ascii", "ignore"),
                              args.gps_baud, exclusive=not args.no_exclusive)
            time.sleep(0.2)

    def mavlink_loop():
        next_request = 0
        last_empty_print = 0
        last_magic_hint = 0
        exclusive = not args.no_exclusive
        while True:
            now = time.time()
            if now >= next_request:
                flags = FLAG_RESPOND | FLAG_MULTI
                if exclusive:
                    flags |= FLAG_EXCLUSIVE
                mav.mav.serial_control_send(
                    args.device,
                    flags,
                    10,
                    args.gps_baud,
                    0,
                    b"\x00" * 70,
                )
                next_request = now + (args.request_interval_ms / 1000.0)

            msg = mav.recv_match(type="SERIAL_CONTROL", blocking=False)
            if msg is not None and getattr(msg, "count", 0) > 0 and msg.device == args.device:
                data = bytes(msg.data[: msg.count])
                if args.show_meta:
                    print(f"[SERIAL_CONTROL] device={msg.device} count={msg.count} flags=0x{msg.flags:02x}")
                if args.show_gps2:
                    if is_all_zero(data):
                        if now - last_empty_print >= 1.0:
                            print("[GPS2 -> TCP] <no data>")
                            last_empty_print = now
                    else:
                        print(f"[GPS2 -> TCP] ({len(data)} bytes) {format_ascii(data)}")
                if args.show_hex and not is_all_zero(data):
                    print(f"[GPS2 -> TCP][hex] {data.hex(' ')}")
                if len(data) > 0 and all(b == data[0] for b in data) and data[0] in (0xFE, 0xFD):
                    if now - last_magic_hint >= 1.0:
                        print("[hint] Got MAVLink magic bytes. You may be reading a telemetry port, not GPS2.")
                        last_magic_hint = now
                client = bridge.get_client()
                if client:
                    try:
                        client.sendall(data)
                    except Exception:
                        bridge.close_client()
            time.sleep(0.005)

    def tcp_to_gps_loop():
        while True:
            client = bridge.get_client()
            if client is None:
                time.sleep(0.05)
                continue
            try:
                data = client.recv(2048)
                if not data:
                    bridge.close_client()
                    continue
                if args.show_tcp:
                    print(f"[TCP -> GPS2] {format_ascii(data)}")
                send_serial_bytes(mav, args.device, data, args.gps_baud, exclusive=not args.no_exclusive)
            except Exception:
                bridge.close_client()

    threading.Thread(target=mavlink_loop, daemon=True).start()
    threading.Thread(target=tcp_to_gps_loop, daemon=True).start()
    threading.Thread(target=send_commands, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        bridge.stop()


if __name__ == "__main__":
    main()
