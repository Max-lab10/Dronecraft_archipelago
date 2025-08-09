# Clover Swarm ESP-NOW Bridge

## Supported Boards

- **ESP32-C3 Super Mini** (`esp32c3_super_mini_prod`)
- **ESP32-C3 XIAO** (`esp32c3_xiao_prod`) 
- **ESP32 DevKit** (`esp32dev_prod`)
- **Lolin S2 Mini** (`lolin_s2_mini_prod`)

## Flashing the Device

### Prerequisites

1. Install PlatformIO or esptool
2. Connect ESP32 to computer via USB
3. Determine device port (e.g., `/dev/ttyUSB0` on Linux or `COM3` on Windows)

### Flashing Commands

#### Using PlatformIO

##### ESP32-C3 Super Mini
```bash
# Flash firmware
pio run -t upload -e esp32c3_super_mini_prod --upload-port /dev/PORT

# Open monitor
pio run -t monitor -e esp32c3_super_mini_prod --monitor-port /dev/PORT
```

##### ESP32 DevKit
```bash
# Flash firmware
pio run -t upload -e esp32dev_prod --upload-port /dev/PORT

# Open monitor
pio run -t monitor -e esp32dev_prod --monitor-port /dev/PORT
```

##### Lolin S2 Mini
```bash
# Flash firmware
pio run -t upload -e lolin_s2_mini_prod --upload-port /dev/PORT

# Open monitor
pio run -t monitor -e lolin_s2_mini_prod --monitor-port /dev/PORT
```

#### Using esptool (Recommended)

##### ESP32C3 Super Mini
```bash
# 1. Erase flash memory
esptool.py --chip esp32c3 --port /dev/ttyACM0 erase_flash

# 2. Flash complete image (includes bootloader and partition table)
esptool.py --chip esp32c3 --port /dev/ttyACM0 --baud 921600 \
  --before default_reset --after hard_reset write_flash \
  0x0 firmware_esp32c3_super_mini_prod_merged.bin
```

##### Lolin S2 Mini
```bash
# 1. Erase flash memory
esptool.py --chip esp32s2 --port /dev/ttyACM0 erase_flash

# 2. Flash complete image (includes bootloader and partition table)
esptool.py --chip esp32s2 --port /dev/ttyACM0 --baud 921600 \
  --before default_reset --after hard_reset write_flash \
  0x0 firmware_lolin_s2_mini_prod_merged.bin
```

## Log Analysis

### Main Message Types

#### 1. System Information
```
=== CLOVER SWARM ESP-NOW BRIDGE ===
Firmware Version: 1.0.0
Build Date: Dec 15 2024 10:30:45
Free heap: 245 KB
```

#### 2. Component Initialization
```
Watchdog initialized
Initializing UART1...
UART1 basic settings initialized
UART1 flow control enabled: RTS=5, CTS=6
UART1: 921600 baud, RX:3 TX:4 RTS:5 CTS:6
Initializing ESP-NOW...
ESP-NOW initialized: Channel 1, Power 20dBm
```

#### 3. Operation Statistics (every 10 seconds)
```
=== ESP32 BRIDGE STATISTICS ===
Uptime: 45678 ms

--- UART INTERFACE ---
TX: 1234 packets, 5678 bytes
RX: 2345 packets, 6789 bytes, 12 corrupted
UART Rates: TX=45.2 pps, RX=67.8 pps
UART Error Rate: 0.51%

--- ESP-NOW INTERFACE ---
TX: 3456 packets, 7890 bytes
RX: 4567 packets, 8901 bytes, 23 corrupted
ESP-NOW Rates: TX=78.9 pps, RX=89.1 pps
ESP-NOW Error Rate: 0.50%
```

#### 4. System Health (every 5 seconds)
```
HEARTBEAT: Drone 1 - Uptime: 45678 ms, Free heap: 245 KB, WiFi: Disconnected
```

#### 5. Debug Information (every 30 seconds)
```
DEBUG: System running - Free heap: 245 KB, Uptime: 45678 ms
```

### Key Metrics for Analysis

#### Performance
- **PPS (Packets Per Second)** - packets per second
- **Error Rate** - percentage of corrupted packets
- **Free heap** - free memory (should be > 10KB)

#### Network Parameters
- **WiFi Status** - WiFi connection status
- **ESP-NOW Channel** - ESP-NOW channel
- **TX Power** - transmission power

#### UART Parameters
- **Baud Rate** - UART speed (921600)
- **Flow Control** - hardware flow control
- **Buffer Size** - buffer size (4096 bytes)

### Problem Analysis

#### Low Performance
- Check **PPS** - should be stable
- Ensure **Error Rate** < 1%
- Check **Free heap** - should be > 10KB

#### Network Issues
- **WiFi: Disconnected** - normal for ESP-NOW mode
- **ESP-NOW init failed** - initialization problem
- **Failed to send packet** - transmission issues

#### Memory Issues
- **Low memory!** - critically low memory
- **Free heap < 10KB** - reboot required

### Test Mode

In test mode, the device generates random telemetry:

```
*** TEST MODE ENABLED - Random Telemetry Generation ***
TEST: Sent telemetry packet #1234 - Drone:1 Pos(12.34,56.78,90.12) Vel(1.23,4.56,7.89)
TEST: Total test packets sent: 1234
```

## Configuration

### Configuration Files

- `/config.json` - main drone configuration
- `/espnow_config.json` - ESP-NOW settings
- `/wifi_config.json` - WiFi settings for OTA
- `/ota_url.json` - OTA update URL

### ESP-NOW Parameters

- **Channel** - WiFi channel (1-13)
- **TX Power** - transmission power (0-20 dBm)
- **Network ID** - network identifier
- **Encryption** - encryption (enabled/disabled)

## Architecture

### Main Components

1. **ESPNowManager** - ESP-NOW network management
2. **PacketDeserializer** - packet deserialization
3. **Statistics** - statistics collection
4. **ConfigManager** - configuration management
5. **OTAManager** - OTA updates