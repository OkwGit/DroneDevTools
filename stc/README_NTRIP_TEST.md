# NTRIP Test Tool for XTRTK Base Station

This Python script tests the **本地差分服务** (Local Differential Service) on your XTRTK base station and displays real-time RTCM data.

## Quick Start

1. **Update the IP address** in `ntrip_test.py`:
   ```python
   HOST = "192.168.1.100"  # Change this to your base station IP
   ```

2. **Run the script**:
   ```bash
   python ntrip_test.py
   ```
   
   Or pass the IP as a command-line argument:
   ```bash
   python ntrip_test.py 192.168.1.100
   ```

## What It Does

- Connects to the NTRIP caster on port **2101**
- Authenticates with username **XTRTK** and password **123456**
- Requests mountpoint **RTCM4**
- Displays real-time RTCM data reception statistics
- Parses and counts RTCM message types (1074, 1084, 1094, 1124, 1005, 1006, 1033)
- Shows bytes/second transfer rate

## What to Look For

### ✅ **Good Signs:**
- Connection successful (200 OK)
- Bytes/second increasing continuously
- RTCM message types appearing (especially 1074, 1084, 1094)
- Multiple messages per second

### ⚠️ **Warning Signs:**
- Connection successful but **zero bytes** received → Base station has no GNSS fix
- Only some RTCM types missing → May be normal (some messages are periodic)
- Connection refused → Service not running or wrong port

### ❌ **Error Signs:**
- Authentication failed (401/403) → Wrong username/password
- Mountpoint not found (404) → Wrong mountpoint name
- Connection timeout → Wrong IP or network issue

## Configuration

The script uses these default settings (matching your XTRTK config):

- **Port**: 2101
- **Mountpoint**: RTCM4
- **Username**: XTRTK
- **Password**: 123456
- **Expected RTCM types**: 1074, 1084, 1094, 1124, 1005, 1006, 1033

You can modify these in the script if needed.

## Requirements

- Python 3.6+ (uses standard library only, no external dependencies)

## Troubleshooting

**No data received:**
- Check if base station has GNSS fix (satellites visible)
- Verify the "本地差分服务" is enabled in the web UI
- Check system logs on the Pi if accessible

**Can't connect:**
- Verify IP address (same one you use for web UI)
- Check firewall settings
- Ensure port 2101 is open

**Wrong RTCM types:**
- Some message types are periodic (e.g., 1005, 1006 every few seconds)
- Others are continuous (1074, 1084, 1094)
- Missing types might be normal depending on base station configuration

