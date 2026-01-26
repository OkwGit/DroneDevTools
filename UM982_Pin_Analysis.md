# UM982 Carrier Board Pin Function Analysis

**Based on:** KiCad schematic connection analysis  
**Total Pins:** 35  
**Date:** 2026-01-24

---

## Pin Function Table

| Pin | Network Name | Connected To | Inferred Function | Confidence |
|-----|--------------|--------------|-------------------|------------|
| **1** | unconnected | - | **Reserved/NC** | Low |
| **2** | unconnected | - | **Reserved/NC** | Low |
| **3** | unconnected | - | **Reserved/NC** | Low |
| **4** | unconnected | - | **Reserved/NC** | Low |
| **5** | /RXD | HC-04 Pin 2 (Bluetooth RXD) | **UART RX (Bluetooth)** - Receives data from Bluetooth module | High |
| **6** | /TXD | HC-04 Pin 3 (Bluetooth TXD) | **UART TX (Bluetooth)** - Sends data to Bluetooth module | High |
| **7** | /UART_RX (GPIO15) | Raspberry Pi Pin 10 | **UART RX (Main)** - Receives data from Raspberry Pi | High |
| **8** | /broken wire (seems) | **DISCONNECTED** | **UART TX (Main)** - Should send data to Raspberry Pi (currently broken) | High |
| **9** | /typec | Type-C Pin 2 | **USB D+ (Type-C)** - USB data positive | High |
| **10** | /typec | Type-C Pin 3 | **USB D- (Type-C)** - USB data negative | High |
| **11** | unconnected | - | **UART TX (Alternative)** - Possible alternative UART TX or reserved | Medium |
| **12** | unconnected | - | **Reserved/NC** | Low |
| **13** | unconnected | - | **Reserved/NC** | Low |
| **14** | /LED(broken) | J_LED1 Pin 4 | **LED Control (Broken)** - LED indicator control (wire broken) | High |
| **15** | unconnected | - | **Reserved/NC** | Low |
| **16** | unconnected | - | **Reserved/NC** | Low |
| **17** | unconnected | - | **Reserved/NC** | Low |
| **18** | unconnected | - | **Reserved/NC** | Low |
| **19** | unconnected | - | **Reserved/NC** | Low |
| **20** | unconnected | - | **Reserved/NC** | Low |
| **21** | unconnected | - | **Reserved/NC** | Low |
| **22** | unconnected | - | **Reserved/NC** | Low |
| **23** | unconnected | - | **Reserved/NC** | Low |
| **24** | unconnected | - | **Reserved/NC** | Low |
| **25** | unconnected | - | **Reserved/NC** | Low |
| **26** | unconnected | - | **Reserved/NC** | Low |
| **27** | /black wire LED | J_LED1 Pin 3 | **LED Control** - LED indicator control (active) | High |
| **28** | unconnected | - | **Reserved/NC** | Low |
| **29** | unconnected | - | **Reserved/NC** | Low |
| **30** | unconnected | - | **Reserved/NC** | Low |
| **31** | unconnected | - | **Reserved/NC** | Low |
| **32** | unconnected | - | **Reserved/NC** | Low |
| **33** | /GND | Multiple GND sources | **Ground (GND)** - Power ground | High |
| **34** | /RedIn | Power network (DC_IN, Type-C, etc.) | **Power Input (VCC)** - Power supply positive (5V) | High |
| **35** | /GPS_ANT | Antenna (AE1) | **Antenna Input** - GNSS antenna connection (SMA) | High |

---

## Functional Group Analysis

### 1. Power Supply (2 pins)
- **Pin 33:** GND (Ground)
- **Pin 34:** VCC (Power Input, 5V from /RedIn network)

### 2. Main UART Communication (2 pins)
- **Pin 7:** UART RX (from Raspberry Pi GPIO15)
- **Pin 8:** UART TX (to Raspberry Pi GPIO14) - **BROKEN/DISCONNECTED**

### 3. Bluetooth UART Communication (2 pins)
- **Pin 5:** UART RX (from HC-04 Bluetooth module)
- **Pin 6:** UART TX (to HC-04 Bluetooth module)

### 4. USB/Type-C Interface (2 pins)
- **Pin 9:** USB D+ (Type-C data positive)
- **Pin 10:** USB D- (Type-C data negative)

### 5. Antenna (1 pin)
- **Pin 35:** GNSS Antenna Input (SMA connector)

### 6. LED Indicators (2 pins)
- **Pin 14:** LED Control (broken wire)
- **Pin 27:** LED Control (active, "black wire LED")

### 7. Reserved/Unused (25 pins)
- **Pins 1-4, 11-13, 15-26, 28-32:** Not connected, function unknown

---

## Connection Details

### Serial Communication Paths

#### Path 1: Raspberry Pi → UM982 (Main UART)
```
Raspberry Pi Pin 8 (GPIO14/TX) → [NOT CONNECTED] → UM982 Pin 8 (should be RX) ❌
Raspberry Pi Pin 10 (GPIO15/RX) → J_PWR1 Pin 2 → UM982 Pin 7 (TX) ✓
```

#### Path 2: Bluetooth → UM982 (Bluetooth UART)
```
HC-04 Pin 2 (RXD) → UM982 Pin 5 (RX) ✓
HC-04 Pin 3 (TXD) → UM982 Pin 6 (TX) ✓
```

### Power Distribution
```
Power Sources:
  - J_DC1 Pin 1 (DC_IN external USB power)
  - J_TypeC1 Pin 1 (Type-C power)
  - SW_MODE1 Pin 1 (Base/Rover switch)
  
All connected to: UM982 Pin 34 (/RedIn)
```

### Ground Distribution
```
GND Sources:
  - Raspberry Pi Pin 6, Pin 20
  - J_DC1 Pin 2
  - J_HC-04 Pin 4
  - J_TypeC1 Pin 4
  - Multiple LED GND pins
  
All connected to: UM982 Pin 33 (/GND)
```

---

## Critical Issues Identified

### Issue 1: UART TX Disconnection
- **Pin 8:** Should connect Raspberry Pi TX to UM982 RX
- **Status:** Physically disconnected (broken wire, only header present)
- **Impact:** No data transmission from Raspberry Pi to UM982
- **Evidence:** 
  - Net "/UART_TX (GPIO14)" connects J1 Pin 8 to J_PWR1 Pin 1 only
  - No connection to J_UM982 Pin 8
  - Pin 8 marked as "/broken wire (seems)"

### Issue 2: LED Control Wire Broken
- **Pin 14:** LED control signal
- **Status:** Wire broken (marked as "/LED(broken)")
- **Impact:** One LED indicator may not function

---

## Pin Function Inference Logic

### High Confidence (Directly Connected)
1. **Pin 5, 6:** Connected to Bluetooth module UART → UART communication
2. **Pin 7:** Connected to Raspberry Pi RX → UART RX
3. **Pin 8:** Marked as broken wire, should be UART TX
4. **Pin 9, 10:** Connected to Type-C data lines → USB interface
5. **Pin 14, 27:** Connected to LED connector → LED control
6. **Pin 33:** Connected to GND network → Ground
7. **Pin 34:** Connected to power network → VCC
8. **Pin 35:** Connected to antenna → Antenna input

### Medium Confidence (Pattern Analysis)
1. **Pin 11:** Unconnected but positioned near UART pins → Possible alternative UART TX or reserved

### Low Confidence (No Connection)
1. **Pins 1-4, 12-13, 15-26, 28-32:** No connections, function unknown
   - Could be: Reserved, alternative interfaces, test points, or future expansion

---

## Communication Interface Summary

### Active Interfaces
1. **Main UART (Raspberry Pi):**
   - RX: Pin 7 ✓
   - TX: Pin 8 ❌ (broken)

2. **Bluetooth UART:**
   - RX: Pin 5 ✓
   - TX: Pin 6 ✓

3. **USB/Type-C:**
   - D+: Pin 9 ✓
   - D-: Pin 10 ✓

### Inactive/Reserved Interfaces
- 25 pins unconnected (possibly reserved for future use or alternative configurations)

---

## Recommendations for Debugging

### Priority 1: Fix UART TX Connection
- **Action:** Connect Raspberry Pi Pin 8 (GPIO14/TX) to UM982 Pin 8
- **Expected Result:** Enable bidirectional communication between Raspberry Pi and UM982

### Priority 2: Verify Pin 8 Function
- **Action:** Check UM982 datasheet or carrier board documentation for Pin 8 function
- **Expected Result:** Confirm Pin 8 is indeed UART RX input

### Priority 3: Test Alternative Pin
- **Action:** If Pin 8 cannot be fixed, test if Pin 11 functions as alternative UART TX
- **Expected Result:** Determine if Pin 11 can serve as backup UART interface

---

## Notes

- All inferences based on schematic connections and standard GNSS receiver interface patterns
- Actual pin functions may vary based on UM982 carrier board design
- Recommend consulting UM982 datasheet or carrier board documentation for definitive pin functions
- Pin numbering follows schematic (J_UM982 connector, 35-pin single row)

---

**End of Analysis**

