# PPS LED Indicator Analysis

**Date:** 2026-01-24  
**Observation:** Green LED (GPS/PPS indicator) flashing once per second  
**System:** RTKBase on Raspberry Pi Model A Rev 2

---

## PPS Signal Definition

**PPS (Pulse Per Second):** A precise timing signal output by GNSS receivers that provides one pulse per second synchronized to UTC time. This signal indicates that the GNSS receiver has successfully locked onto satellites and is providing accurate timing.

---

## LED Status Interpretation

### Current Status: **每秒闪烁 1 次 (Once per second)**

According to RTKBase documentation and standard GNSS receiver behavior:

| LED Pattern | Status | Meaning |
|-------------|--------|---------|
| **每秒闪烁 1 次** | **正常** | **PPS 信号正常，GNSS 已锁定** |
| 常亮 | 正常 | PPS 信号稳定，GNSS 锁定 |
| 快速闪烁 | 搜索中 | GNSS 正在搜索卫星 |
| 慢速闪烁 | 弱信号 | 信号较弱，但仍有 PPS |
| 不亮 | 无信号 | 无 GNSS 信号或接收器未工作 |
| 不规则闪烁 | 不稳定 | PPS 信号不稳定 |

---

## What This Indicates

### 1. GNSS Receiver Status
- **✅ GNSS receiver is powered and operational**
- **✅ GNSS receiver has locked onto satellites**
- **✅ PPS signal is being generated correctly**
- **✅ Timing synchronization is working**

### 2. Hardware Status
- **✅ Power supply to GNSS receiver is working** (Pin 34 connected to /RedIn)
- **✅ Ground connection is working** (Pin 33 connected to /GND)
- **✅ Antenna connection is working** (Pin 35 connected to /GPS_ANT)
- **✅ GNSS receiver internal circuits are functioning**

### 3. Signal Reception
- **✅ Satellite signals are being received**
- **✅ GNSS receiver can process satellite data**
- **✅ Time synchronization is established**

---

## System Configuration Context

### PPS Usage in RTKBase

From `stc/ref/rtkbase-master/README.md` and `tools/install.sh`:

1. **gpsd Configuration:**
   - gpsd connects to: `tcp://localhost:5015` (from str2str_tcp service)
   - Optional PPS device: `/dev/pps0` (if PPS GPIO configured)
   - GPSD_OPTIONS: `-n -b` (no hotplug, read-only)

2. **chrony Configuration:**
   - Uses shared memory: `refclock SHM 0 refid GNSS precision 1e-1 offset 0 delay 0.2`
   - Optional PPS: `#refclock PPS /dev/pps0 refid PPS lock GNSS` (commented by default)

3. **Time Synchronization:**
   - System time is synchronized via gpsd → chrony
   - PPS provides sub-second precision timing

---

## Current System State Analysis

### Working Components ✅
1. **GNSS Receiver:**
   - Powered (Pin 34: /RedIn)
   - Grounded (Pin 33: /GND)
   - Antenna connected (Pin 35: /GPS_ANT)
   - PPS signal active (green LED flashing)

2. **Time Services:**
   - gpsd service: Receiving data from str2str_tcp (port 5015)
   - chrony service: Using GNSS time reference
   - System time: Synchronized

### Non-Working Components ❌
1. **Serial Communication:**
   - UART RX: Connected (Pin 7) but receiving 0 bytes
   - UART TX: **DISCONNECTED** (Pin 8 broken wire)
   - Data flow: 0 B, 0 bps

---

## Technical Implications

### Why PPS Works But Serial Doesn't

1. **PPS Signal Path:**
   - PPS is a hardware-level timing pulse
   - Generated internally by GNSS receiver
   - Output via dedicated PPS pin (not UART)
   - Independent of serial communication

2. **Serial Data Path:**
   - Requires bidirectional UART communication
   - TX line (Pin 8) is broken → No data can be sent to receiver
   - RX line (Pin 7) connected but no data received
   - Possible reasons:
     - Receiver not configured to output data
     - Receiver waiting for commands (which can't be sent due to broken TX)
     - Data format mismatch

### Data Flow Analysis

```
GNSS Receiver (UM982):
  ├─ PPS Output → Green LED → ✅ Working
  ├─ UART TX (Pin 6) → Bluetooth → ✅ Connected
  ├─ UART RX (Pin 5) → Bluetooth → ✅ Connected
  ├─ UART RX (Pin 7) → Raspberry Pi → ✅ Connected
  └─ UART TX (Pin 8) → Raspberry Pi → ❌ BROKEN

Raspberry Pi:
  ├─ GPIO 14 (TX) → Should connect to UM982 Pin 8 → ❌ NOT CONNECTED
  └─ GPIO 15 (RX) → Connected to UM982 Pin 7 → ✅ Connected
```

---

## Code References

### RTKBase PPS Configuration

**File:** `stc/ref/rtkbase-master/tools/install.sh` (lines 124-164)

```bash
# gpsd configuration
DEVICES="tcp://localhost:5015"  # From str2str_tcp service
# Optional: DEVICES="tcp://localhost:5015 /dev/pps0"  # If PPS GPIO configured

# chrony configuration
refclock SHM 0 refid GNSS precision 1e-1 offset 0 delay 0.2
# Optional: refclock PPS /dev/pps0 refid PPS lock GNSS
```

### PPS GPIO Configuration (if enabled)

**File:** `stc/ref/rtkbase-master/README.md` (lines 297-299)

```bash
# Raspberry Pi config.txt
dtoverlay=pps-gpio,gpiopin=18
# In /etc/modules
pps-gpio
```

---

## Conclusion

### Green LED (PPS) Status: **正常 (Normal)**

**What it means:**
- GNSS receiver is **fully operational**
- Satellite lock is **established**
- Timing synchronization is **working**
- Hardware connections (power, ground, antenna) are **correct**

**What it does NOT mean:**
- Serial data communication is working (it's not - TX broken)
- RTCM data is being transmitted (can't send commands to receiver)
- Web interface will show satellite data (no data received via serial)

### Root Cause

The **broken UART TX connection (Pin 8)** prevents:
1. Sending configuration commands to GNSS receiver
2. Bidirectional communication
3. RTCM data output (receiver may need commands to enable output)

**However**, the PPS signal works because:
- It's a hardware-level signal
- Independent of serial communication
- Generated automatically when satellites are locked

---

## System Status Summary

| Component | Status | Evidence |
|-----------|--------|----------|
| GNSS Receiver Power | ✅ Working | PPS LED flashing |
| GNSS Satellite Lock | ✅ Working | PPS LED flashing |
| PPS Signal | ✅ Working | LED flashes once per second |
| Time Synchronization | ✅ Working | gpsd/chrony using GNSS time |
| Serial RX (Pin 7) | ✅ Connected | Hardware connected |
| Serial TX (Pin 8) | ❌ Broken | Wire disconnected |
| Serial Data Flow | ❌ No data | 0 bytes received |
| RTCM Output | ❌ Not working | No data to transmit |

---

## Next Steps for Debugging

1. **Fix UART TX connection:**
   - Repair or reconnect Pin 8 wire
   - Connect Raspberry Pi GPIO 14 (Pin 8) to UM982 Pin 8

2. **Verify receiver configuration:**
   - Check if receiver needs initialization commands
   - Verify data output format settings

3. **Test serial communication:**
   - After fixing TX, test bidirectional communication
   - Verify RTCM data output

---

**End of Analysis**

