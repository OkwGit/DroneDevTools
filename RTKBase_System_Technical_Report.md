# RTKBase System Technical Report

**Generated:** 2026-01-24  
**System:** Raspberry Pi Model A Rev 2 (Revision: 0008)  
**Purpose:** RTK GNSS Base Station

---

## 1. Hardware Information

### 1.1 Raspberry Pi Specifications
- **Model:** Raspberry Pi Model A Rev 2
- **Revision Code:** 0008
- **GPIO Header:** 26-pin
- **Memory:** 256MB
- **CPU:** BCM2835 (ARMv6)

### 1.2 Network Interface
- **WiFi Adapter:** Realtek RTL8188FTV 802.11b/g/n 1T1R 2.4G WLAN Adapter
- **USB ID:** 0bda:f179
- **Interface:** wlan0
- **Current IP:** 192.168.137.16/24
- **SSID:** XTRTK
- **Signal Quality:** 99/100
- **Link Quality:** 99/100

### 1.3 USB Devices
```
Bus 001 Device 004: ID 0bda:f179 Realtek Semiconductor Corp. RTL8188FTV 802.11b/g/n 1T1R 2.4G WLAN Adapter
Bus 001 Device 003: ID 04a9:0088 Holtek Semiconductor, Inc.
Bus 001 Device 002: ID 1a40:0101 Terminus Technology Inc. Hub
Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub
```

---

## 2. Operating System

### 2.1 OS Information
- **Distribution:** Raspbian GNU/Linux 11
- **Kernel:** Linux (version from device tree)
- **Hostname:** basegnss
- **User:** basegnss
- **User Password:** basegnss!
- **User Groups:** gnssuser, sudo

### 2.2 Boot Configuration
- **Boot Files Location:** /boot/
- **Config File:** /boot/config.txt
- **Cmdline:** /boot/cmdline.txt
- **Root Partition UUID:** 1244eef9-02
- **Root Filesystem:** ext4
- **Console:** tty1

---

## 3. Serial Port Configuration

### 3.1 UART Settings
- **Device:** /dev/ttyAMA0
- **Baudrate:** 115200
- **Data Bits:** 8
- **Stop Bits:** 1
- **Parity:** None (n)
- **Format:** 115200:8:n:1
- **GPIO TX:** Pin 8 (GPIO 14)
- **GPIO RX:** Pin 10 (GPIO 15)
- **Permissions:** crw-rw---- (root:dialout, 204, 64)

### 3.2 UART Configuration in config.txt
```
dtoverlay=disable-bt
enable_uart=1
dtoverlay=pi3-miniuart-bt
```

### 3.3 System UART Status
- **Hardware:** PL011 rev2 at MMIO 0x20201000
- **IRQ:** 81
- **Base Baud:** 0
- **DMA:** No DMA platform data

---

## 4. Network Configuration

### 4.1 Network Interfaces
```
Interface: lo
  Type: Loopback
  State: UP
  IP: 127.0.0.1/8
  IPv6: ::1/128

Interface: wlan0
  Type: Wireless
  State: UP
  MAC: 00:2e:2a:43:0f:59
  IP: 192.168.137.16/24
  Broadcast: 192.168.137.255
  IPv6: fe80::722e:2aff:fe43:f59/64
  SSID: XTRTK
  Frequency: 2.412 GHz
  Bit Rate: 72.2 Mb/s
  Access Point: 46:A3:BB:09:AA:DD
```

### 4.2 Network Services
- **Avahi Daemon:** Enabled (systemctl restart avahi-daemon)
- **RF Kill:** Unblocked (rfkill unblock all)

---

## 5. RTKBase Software Configuration

### 5.1 Installation Path
- **Base Directory:** /home/basegnss/rtkbase/
- **Tools Directory:** /home/basegnss/rtkbase/tools/
- **Web App:** /home/basegnss/rtkbase/web_app/
- **Data Directory:** /home/basegnss/rtkbase/data/
- **Logs Directory:** /home/basegnss/rtkbase/logs/
- **Config File:** /home/basegnss/rtkbase/settings.conf

### 5.2 RTKBase Services

#### 5.2.1 Web Server Service
- **Service Name:** rtkbase_web.service
- **Status:** active (running)
- **Started:** 2026-01-16 02:18:32 CST
- **Uptime:** 1 week 1 day
- **PID:** 499
- **Command:** /usr/bin/python3 /home/basegnss/rtkbase/web_app/server.py
- **Port:** 80
- **URL:** http://192.168.137.16

#### 5.2.2 TCP Stream Service
- **Service Name:** str2str_tcp.service
- **Status:** active (running)
- **Started:** 2026-01-16 02:18:37 CST
- **Uptime:** 1 week 1 day
- **PID:** 561
- **Command:** /usr/local/bin/str2str -in serial:///ttyAMA0:115200:8:n:1#rtcm3 -out tcpsvr://:5015 -b 1 -t 0 -fl /home/basegnss/rtkbase/logs/str2str_tcp.log
- **Input:** serial:///ttyAMA0:115200:8:n:1#rtcm3
- **Output:** tcpsvr://:5015
- **Log File:** /home/basegnss/rtkbase/logs/str2str_tcp.log
- **Current Status:** Waiting for data (0 B, 0 bps)

### 5.3 RTKBase Configuration (settings.conf)
- **Receiver Format:** rtcm3
- **Com Port:** ttyAMA0
- **Com Port Settings:** 115200:8:n:1
- **TCP Port:** 5015
- **Local NTRIP Port:** 2101
- **Local NTRIP User:** XTRTK
- **Local NTRIP Password:** 123456
- **Mount Point:** RTCM4

---

## 6. GPIO Pin Configuration

### 6.1 Active GPIO Pins
| Pin | GPIO | Function | Configuration |
|-----|------|-----------|--------------|
| 8 | GPIO 14 | UART TX | Serial transmit |
| 10 | GPIO 15 | UART RX | Serial receive |
| 18 | GPIO 24 | LED Control | dtoverlay=act-led,gpio=24 |

### 6.2 Power Pins
| Pin | Function | Connected To |
|-----|----------|--------------|
| 4 | 5V | SW_MODE1 (Base/Rover switch) |
| 6 | GND | Multiple GND connections |
| 20 | GND | Multiple GND connections |

---

## 7. Circuit Connections (from KiCad schematic)

### 7.1 Serial Communication Path
```
Raspberry Pi J1 Pin 8 (GPIO14/TX) → J_PWR1 Pin 1 (unused) → [NOT CONNECTED TO J_UM982]
Raspberry Pi J1 Pin 10 (GPIO15/RX) → J_PWR1 Pin 2 (unused) → J_UM982 Pin 7
```

### 7.2 Power Connections
```
/RedIn Network:
  - J_DC1 Pin 1 (DC_IN external USB power)
  - J_HC-04 Pin 5 (Bluetooth module power)
  - J_LED1 Pin 2 (LED power)
  - J_TypeC1 Pin 1 (Type-C power)
  - J_UM982 Pin 34 (GNSS receiver power)
  - SW_MODE1 Pin 1 (Base/Rover switch)

/GND Network:
  - J1 Pin 6, Pin 20 (Raspberry Pi GND)
  - J_DC1 Pin 2
  - J_HC-04 Pin 4
  - J_LED1 Pin 1, Pin 5, Pin 7
  - J_TypeC1 Pin 4
  - J_UM982 Pin 33
```

### 7.3 LED Connections
```
/LED_CTRL: J1 Pin 18 (GPIO24) → J_LED1 Pin 8
/LED(broken): J_LED1 Pin 4 → J_UM982 Pin 14
/black wire LED: J_LED1 Pin 3 → J_UM982 Pin 27
/16_LED: J_HC-04 Pin 6 → J_LED1 Pin 6
```

### 7.4 Bluetooth Module (HC-04) Connections
```
/RXD: J_HC-04 Pin 2 → J_UM982 Pin 5
/TXD: J_HC-04 Pin 3 → J_UM982 Pin 6
/RedIn: J_HC-04 Pin 5 → Power network
/GND: J_HC-04 Pin 4 → GND network
/16_LED: J_HC-04 Pin 6 → J_LED1 Pin 6
/state(no): J_HC-04 Pin 1 → Unconnected
```

### 7.5 GNSS Receiver (J_UM982) Connections
```
Pin 5: /RXD (from HC-04)
Pin 6: /TXD (to HC-04)
Pin 7: /UART_RX (from Raspberry Pi Pin 10)
Pin 8: /broken wire (seems) - UNCONNECTED
Pin 9: /typec (Type-C data)
Pin 10: /typec (Type-C data)
Pin 14: /LED(broken) (from J_LED1 Pin 4)
Pin 27: /black wire LED (from J_LED1 Pin 3)
Pin 33: /GND
Pin 34: /RedIn (power)
Pin 35: /GPS_ANT (antenna)
```

### 7.6 Known Issues from Schematic
- **J_UM982 Pin 8:** Marked as "/broken wire (seems)" - physically disconnected, only header present
- **UART_TX:** Raspberry Pi Pin 8 connects to J_PWR1 Pin 1 but NOT to J_UM982
- **J_PWR1:** JST-XH 2.54mm connector with UART_TX and UART_RX, not connected to any device (dead end)

---

## 8. Service Logs

### 8.1 str2str_tcp Service Log
```
2026/01/24 06:05:22 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
2026/01/24 06:06:22 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
2026/01/24 06:06:27 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
2026/01/24 06:06:32 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
2026/01/24 06:07:22 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
2026/01/24 06:07:27 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
2026/01/24 06:07:32 [CW--] 0 B 0 bps (0) /dev/ttyAMA0 (1) waiting...
```

### 8.2 System Messages
- **Suppressed Messages:** 10 messages from str2str_tcp.service (systemd-journald)
- **Python Warning:** Setuptools replacing distutils (non-critical)

---

## 9. File System Paths

### 9.1 Boot Files
- `/boot/config.txt`
- `/boot/cmdline.txt`
- `/boot/issue.txt` (Raspberry Pi reference 2023-02-28, pi-gen RTKbase)

### 9.2 RTKBase Files
- `/home/basegnss/rtkbase/settings.conf`
- `/home/basegnss/rtkbase/settings.conf.default`
- `/home/basegnss/rtkbase/data/` (GNSS data storage)
- `/home/basegnss/rtkbase/logs/` (Service logs)

### 9.3 System Files
- `/etc/systemd/system/rtkbase_web.service`
- `/etc/systemd/system/str2str_tcp.service`
- `/dev/ttyAMA0` (Serial port device)

---

## 10. Network Ports

### 10.1 Listening Ports
- **Port 80:** RTKBase Web Server (HTTP)
- **Port 5015:** str2str TCP stream (RTCM data)
- **Port 2101:** Local NTRIP Caster (if enabled)

### 10.2 Service Ports
- **Port 5014:** NMEA port (raw2nmea service)
- **Port 5016:** RTCM server port (if enabled)
- **Port 9090:** GNSS receiver web proxy port

---

## 11. Device Tree Overlays

### 11.1 Active Overlays
```
dtoverlay=disable-bt          # Disable Bluetooth
dtoverlay=pi3-miniuart-bt     # Use mini UART for Bluetooth
dtoverlay=act-led,gpio=24     # Activity LED on GPIO 24
dtoverlay=vc4-kms-v3d         # DRM VC4 V3D driver
dtparam=audio=on              # Enable audio
```

### 11.2 Disabled Overlays (commented)
```
#dtparam=i2c_arm=on
#dtparam=i2s=on
#dtparam=spi=on
#dtoverlay=gpio-ir,gpio_pin=17
#dtoverlay=gpio-ir-tx,gpio_pin=18
```

---

## 12. Cloud-init Configuration

### 12.1 User Configuration
- **Username:** basegnss
- **Password:** basegnss!
- **Groups:** gnssuser, sudo
- **Sudo:** NOPASSWD:ALL

### 12.2 Initialization Commands
```yaml
runcmd:
  - systemctl restart avahi-daemon
  - rfkill unblock all
  - cd /home/basegnss/rtkbase/tools && sudo ./install.sh --user basegnss --unit-files --detect-usb-gnss --configure-gnss --start-services
```

---

## 13. Current System State

### 13.1 Service Status
- **rtkbase_web:** active (running)
- **str2str_tcp:** active (running), waiting for serial data
- **Network:** Connected to XTRTK WiFi hotspot
- **Serial Port:** Configured but receiving 0 bytes

### 13.2 Web Interface
- **Status:** Accessible at http://192.168.137.16
- **Positioning Status Page:** Loads but shows no satellite data
- **Graph:** Empty (no signal data)
- **Coordinates Displayed:** -79.45960835°, 43.70594983°, 142.80m (cached/previous)

### 13.3 Serial Communication
- **Device:** /dev/ttyAMA0 exists and is configured
- **Baudrate:** 115200
- **Data Flow:** 0 bytes received
- **Status:** Service waiting for data

---

## 14. Hardware Connection Summary

### 14.1 Physical Connections Observed
- **Interface 1:** Pin 4 (5V), Pin 6 (GND) - Power
- **Interface 2:** Pin 8 (GPIO14/TX), Pin 10 (GPIO15/RX) - Serial
- **Interface 3:** Pin 18 (GPIO24/LED), Pin 20 (GND) - LED control

### 14.2 Circuit Board Connections
- **J_UM982:** 35-pin connector (GNSS receiver carrier board)
- **J_PWR1:** 2-pin JST-XH 2.54mm connector (unused, dead end)
- **J_HC-04:** 10-pin connector (Bluetooth module)
- **J_LED1:** 8-pin connector (LED indicators)
- **J_TypeC1:** 4-pin connector (Type-C interface)
- **J_DC1:** 2-pin connector (DC power input)
- **SW_MODE1:** 2-pin switch (Base/Rover mode selection)

---

## 15. Software Versions

### 15.1 RTKBase
- **Source:** pi-gen RTKbase (commit: 87188044995020df362c164bf859e35c897e9230)
- **Image Date:** 2023-02-28
- **Stage:** stage4

### 15.2 Python
- **Version:** Python 3.9
- **Packages:** Setuptools, distutils (replacement warning)

### 15.3 RTKLIB
- **Path:** /usr/local/bin/str2str
- **Version:** (from RTKLIB-EX b34j branch)

---

## 16. Diagnostic Commands Output

### 16.1 Serial Port Test
```bash
$ sudo cat /dev/ttyAMA0
# Result: No output (Ctrl+C to exit)

$ sudo hexdump -C /dev/ttyAMA0 | head -20
# Result: No output
```

### 16.2 Serial Port Configuration
```bash
$ stty -F /dev/ttyAMA0 -a
speed 115200 baud; line = 0;
min = 0; time = 0;
-brkint -icrnl -imaxbel
-opost -onlcr
-isig -icanon -iexten -echo -echoe -echok -echocl -echoke
```

### 16.3 System Information
```bash
$ cat /proc/device-tree/model
Raspberry Pi Model A Rev 2

$ cat /proc/cpuinfo | grep Revision
Revision : 0008
```

---

## End of Report

