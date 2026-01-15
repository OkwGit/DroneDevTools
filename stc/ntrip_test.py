import base64
import os
import socket
import sys
import time
from collections import Counter
from typing import Dict, Tuple, Optional
from datetime import datetime


# Default configuration matching your XTRTK "本地差分服务"
HOST = "192.168.137.172"  # You can override from CLI: python ntrip_test.py <ip>
PORT = 2101
MOUNTPOINT = "RTCM4"
USERNAME = "XTRTK"
PASSWORD = "123456"

# Enable verbose debugging of the NTRIP handshake
DEBUG = True

# Expected RTCM message types from your config
EXPECTED_TYPES = {1074, 1084, 1094, 1124, 1005, 1006, 1033}

# Log directory path
LOG_DIR = r"C:\Users\oxpas\Documents\GitHub\DroneDevTools\stc\logs"


def build_ntrip_request(host: str, mountpoint: str, user: str, password: str) -> bytes:
    """Build a minimal NTRIP v2 GET request."""
    auth = base64.b64encode(f"{user}:{password}".encode("ascii")).decode("ascii")
    # Use HTTP/1.0 for simplicity; most casters accept it.
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

    if DEBUG:
        print("---- NTRIP request being sent ----")
        print(request.decode("ascii", errors="replace"))
        print("----------------------------------")

    return request


def parse_rtcm3_message_type(payload: bytes) -> int:
    """
    Parse RTCM3 message type from payload.

    RTCM3 framing:
      - 0xD3 sync
      - 6 bits reserved + 10 bits length
      - payload (length bytes)
      - 3-byte CRC

    The first 12 bits of the payload are the message number.
    """
    if len(payload) < 2:
        return -1

    # First two payload bytes contain the 12‑bit message number (big‑endian)
    # Bits: [msg_type(12)] [rest...]
    msg_type = ((payload[0] << 4) | (payload[1] >> 4)) & 0x0FFF
    return msg_type


def read_rtcm_stream(sock: socket.socket, initial_data: bytes = b"") -> Dict[str, object]:
    """
    Read RTCM3 stream from the socket, track statistics and print them periodically.
    
    Args:
        sock: The socket to read from
        initial_data: Optional binary data that was already received (e.g., from header)
    """
    buffer = bytearray(initial_data)
    total_bytes = len(initial_data)  # Count initial data too
    msg_counts: Counter[int] = Counter()
    start_time = time.time()
    last_report = start_time

    # If no bytes arrive for this many seconds, we log a warning.
    # We DO NOT exit on timeout; we just keep waiting.
    sock.settimeout(30.0)

    print("✅ Connected. Waiting for RTCM data...")
    if initial_data:
        print(f"📦 Processing {len(initial_data)} bytes from header...")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            print("⚠️  Timeout while waiting for data (no bytes for 30s) – still listening...")
            continue
        except OSError as e:
            print(f"❌ Socket error: {e}")
            break

        if not chunk:
            print("⚠️  Connection closed by server.")
            break

        buffer.extend(chunk)
        total_bytes += len(chunk)

        # Parse as many RTCM3 frames as possible from the buffer
        while True:
            # Look for sync byte 0xD3
            try:
                sync_index = buffer.index(0xD3)
            except ValueError:
                # No sync byte in buffer yet
                buffer.clear()
                break

            if len(buffer) - sync_index < 3:
                # Not enough data for header yet
                # Keep partial data
                if sync_index > 0:
                    del buffer[:sync_index]
                break

            # Header after sync: 2 bytes (6 bits reserved + 10 bits length)
            header = buffer[sync_index + 1 : sync_index + 3]
            length = ((header[0] & 0x03) << 8) | header[1]

            frame_len = 3 + length + 3  # sync+header + payload + CRC
            if len(buffer) - sync_index < frame_len:
                # Wait for more data
                if sync_index > 0:
                    del buffer[:sync_index]
                break

            frame = buffer[sync_index : sync_index + frame_len]
            # Remove frame from buffer
            del buffer[: sync_index + frame_len]

            payload = frame[3:-3]
            msg_type = parse_rtcm3_message_type(payload)
            if msg_type > 0:
                msg_counts[msg_type] += 1

        now = time.time()
        if now - last_report >= 2.0:
            elapsed = now - start_time
            bps = total_bytes / elapsed if elapsed > 0 else 0.0

            # Prepare counts for expected types
            counts_display = []
            for t in sorted(EXPECTED_TYPES):
                counts_display.append(f"{t}: {msg_counts.get(t, 0)}")
            # Also show top 5 most frequent types (could include others)
            top_types = ", ".join(
                f"{t}({c})" for t, c in msg_counts.most_common(5)
            )

            print(
                f"[{elapsed:6.1f}s] "
                f"bytes={total_bytes}  rate={bps:8.1f} B/s  "
                f"expected: {' | '.join(counts_display)}"
            )
            if top_types:
                print(f"    top types: {top_types}")

            last_report = now

    # Final stats
    elapsed = time.time() - start_time
    return {
        "total_bytes": total_bytes,
        "elapsed": elapsed,
        "msg_counts": dict(msg_counts),
    }


def connect_ntrip(
    host: str,
    port: int,
    mountpoint: str,
    user: str,
    password: str,
) -> Tuple[socket.socket, bytes]:
    """Open TCP connection, send NTRIP request, and return socket + raw header."""
    addr = (host, port)
    print(f"Connecting to NTRIP caster {host}:{port}, mountpoint '{mountpoint}'...")

    try:
        sock = socket.create_connection(addr, timeout=10.0)
    except OSError as e:
        if DEBUG:
            print(f"[DEBUG] socket.create_connection error: {e}")
        raise

    # Allow a bit more time while reading the HTTP/NTRIP header
    sock.settimeout(30.0)

    request = build_ntrip_request(host, mountpoint, user, password)
    if DEBUG:
        print("[DEBUG] Sending NTRIP request...")
    sock.sendall(request)

    # Read HTTP/NTRIP response header (some casters send a big SOURCETABLE or banner)
    # We allow up to 64 KiB before giving up.
    header = b""
    max_header = 64 * 1024
    if DEBUG:
        print("[DEBUG] Starting to read response header from server...")
    while len(header) < max_header:
        try:
            chunk = sock.recv(1024)
        except socket.timeout:
            # If we already see a 200/ICY 200 status line, accept what we have.
            try:
                text = header.decode("iso-8859-1", errors="replace")
            except Exception:
                text = ""
            if "ICY 200" in text or " 200 " in text:
                if DEBUG:
                    print(
                        "[DEBUG] Timeout while reading header, but 200 status "
                        "already detected – proceeding with current header."
                    )
                break

            if DEBUG:
                print(
                    "[DEBUG] Timeout while reading header and no 200 status yet; "
                    f"header length so far: {len(header)} bytes"
                )
            raise ConnectionError("Timed out while waiting for NTRIP response header.")

        if not chunk:
            if DEBUG:
                print(
                    f"[DEBUG] Socket closed while reading header. "
                    f"Current header length: {len(header)} bytes"
                )
            break

        header += chunk
        if DEBUG:
            print(
                f"[DEBUG] Received header chunk: {len(chunk)} bytes, "
                f"total header length: {len(header)} bytes"
            )

        # Normal HTTP/NTRIP header termination
        if b"\r\n\r\n" in header:
            if DEBUG:
                print("[DEBUG] Found '\\r\\n\\r\\n' – end of HTTP header.")
            break

        # Some NTRIP casters send "ICY 200 OK" followed directly by data,
        # without an empty line. If we see a 200 status line, accept it
        # as soon as we have received a reasonable amount of data.
        try:
            text = header.decode("iso-8859-1", errors="replace")
        except Exception:
            text = ""
        if ("ICY 200" in text or " 200 " in text) and len(header) > 128:
            if DEBUG:
                print(
                    "[DEBUG] Detected '200' status without explicit "
                    "'\\r\\n\\r\\n'; assuming start of data after status line."
                )
            break

    if DEBUG:
        print("[DEBUG] Finished reading header (may include some data bytes).")

    return sock, header


def check_response_header(header: bytes) -> Tuple[bytes, bytes]:
    """
    Validate HTTP/NTRIP response status and print diagnostics.
    Returns: (text_header_part, binary_data_part)
    """
    # Find where the text header ends (either \r\n\r\n or start of binary data)
    header_end = header.find(b"\r\n\r\n")
    if header_end != -1:
        header_end += 4  # Include the \r\n\r\n
    
    if header_end == -1:
        # No explicit header terminator, find where binary data starts
        # Look for the first non-printable byte after the status line
        status_end = header.find(b"\r\n")
        if status_end == -1:
            status_end = header.find(b"\n")
        if status_end != -1:
            # Check if there's binary data after status line
            # RTCM3 sync byte is 0xD3, so if we see it, that's where data starts
            data_start = header.find(b"\xD3", status_end + 2)
            if data_start != -1:
                header_end = data_start
            else:
                # Try to find first non-printable byte
                for i in range(status_end + 2, min(len(header), status_end + 200)):
                    if header[i] < 32 and header[i] not in (9, 10, 13):  # Not tab, LF, CR
                        header_end = i
                        break
    
    if header_end == -1:
        header_end = len(header)
    
    # Split header into text and binary parts
    header_text_part = header[:header_end]
    binary_data_part = header[header_end:] if header_end < len(header) else b""
    
    # Decode text part for display
    header_text_decoded = header_text_part.decode("iso-8859-1", errors="replace")
    status_line = header_text_decoded.split("\r\n", 1)[0]
    if "\n" in status_line and "\r\n" not in status_line:
        status_line = status_line.split("\n", 1)[0]

    # Show header preview (only text part)
    print("---- Header preview ----")
    preview_lines = header_text_decoded.replace("\r", "").split("\n")
    for line in preview_lines[:10]:
        if line.strip():  # Only show non-empty lines
            print(line)
    if binary_data_part:
        print(f"... ({len(binary_data_part)} bytes of RTCM3 binary data follows)")
    print("------------------------")

    print("Server response:", status_line)

    if status_line.startswith("ICY 200") or " 200 " in status_line:
        print("✅ NTRIP stream started successfully.\n")
        return header_text_part, binary_data_part

    # Basic error decoding based on README
    if "401" in status_line or "403" in status_line:
        raise ConnectionError("Authentication failed (401/403). Check username/password.")
    if "404" in status_line:
        raise ConnectionError("Mountpoint not found (404). Check mountpoint name.")
    if "500" in status_line:
        raise ConnectionError("Server internal error (500).")

    raise ConnectionError(f"Unexpected response from server: {status_line}")


def write_summary_log(
    host: str,
    stats: Optional[Dict[str, object]],
    error: Optional[str],
) -> None:
    """Write one log file per run summarizing results and errors."""
    # Ensure logs directory exists
    os.makedirs(LOG_DIR, exist_ok=True)
    
    ts = datetime.now()
    log_filename = ts.strftime("ntrip_log_%Y%m%d_%H%M%S.txt")
    filename = os.path.join(LOG_DIR, log_filename)

    lines = []
    lines.append(f"Time       : {ts.isoformat(sep=' ', timespec='seconds')}")
    lines.append(f"Host       : {host}")
    lines.append(f"Port       : {PORT}")
    lines.append(f"Mountpoint : {MOUNTPOINT}")
    lines.append("")

    if stats is not None:
        total_bytes = stats.get("total_bytes", 0)
        elapsed = stats.get("elapsed", 0.0) or 0.0
        msg_counts: Dict[int, int] = stats.get("msg_counts", {})  # type: ignore[assignment]
        bps = total_bytes / elapsed if elapsed > 0 else 0.0

        lines.append("Result     : STREAM RECEIVED")
        lines.append(f"Duration   : {elapsed:.1f} s")
        lines.append(f"Bytes      : {total_bytes}")
        lines.append(f"Avg rate   : {bps:.1f} B/s")
        lines.append("RTCM types :")
        for t in sorted(msg_counts.keys()):
            lines.append(f"  - {t}: {msg_counts[t]}")
    else:
        lines.append("Result     : NO DATA (connection failed before stream)")

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


def main() -> None:
    host = HOST

    # Optional IP override from command line
    if len(sys.argv) >= 2:
        host = sys.argv[1]

    stats: Optional[Dict[str, object]] = None
    error_message: Optional[str] = None

    try:
        sock, header = connect_ntrip(
            host=host,
            port=PORT,
            mountpoint=MOUNTPOINT,
            user=USERNAME,
            password=PASSWORD,
        )
    except (OSError, ConnectionError) as e:
        error_message = f"Failed to connect to NTRIP caster: {e}"
        print(f"❌ {error_message}")
        write_summary_log(host, stats=None, error=error_message)
        sys.exit(1)

    try:
        header_text, binary_data = check_response_header(header)
    except ConnectionError as e:
        error_message = str(e)
        print(f"❌ {error_message}")
        sock.close()
        write_summary_log(host, stats=None, error=error_message)
        sys.exit(1)

    try:
        stats = read_rtcm_stream(sock, initial_data=binary_data)
    except KeyboardInterrupt:
        error_message = "Interrupted by user (KeyboardInterrupt)."
        print("\nInterrupted by user.")
    finally:
        try:
            sock.close()
        except OSError:
            pass
        print("Connection closed.")
        write_summary_log(host, stats=stats, error=error_message)


if __name__ == "__main__":
    main()


