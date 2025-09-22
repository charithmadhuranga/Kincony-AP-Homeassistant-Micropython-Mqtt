# KC868-AP Control System (MQTT + Home Assistant)

A robust MicroPython application for ESP32 controlling the KC868-AP dimmer/relay hardware with native Home Assistant MQTT discovery. This project is now MQTT-only (no web UI/server).

## Features

- **Home Assistant Autodiscovery**: 16 dimmers (lights), 2 relays (switches), 16 inputs (binary_sensors)
- **MQTT LWT/Availability**: Online/offline state exposed for reliable device presence
- **Low-latency Commands**: Fast MQTT loop for responsive control from HA
- **Secure Configuration**: JSON configuration with validation
- **Hardware Abstraction**: PCA9685 (dimmers), PCF8574 (inputs), relays with retry logic
- **Comprehensive Logging**: Structured logs for debugging

## Hardware Requirements

- ESP32 microcontroller
- KC868-AP control board
- PCF8574 I2C expanders (inputs)
- PCA9685 PWM controller (dimmers)
- 2x Relay outputs
- Wi‑Fi network

## Installation

1. Flash MicroPython to ESP32
2. Upload files to the ESP32 filesystem:
   - `boot.py`
   - `main.py` (MQTT-only application)
   - `config.py` (configuration loader)
   - `config.json` (your settings)
   - `hardware.py` (hardware abstraction)
   - `network_manager.py` (Wi‑Fi connect)
   - `logger.py` (logging)
   - `mqtt_manager.py` (MQTT + HA discovery)
3. Edit `config.json` (Wi‑Fi and MQTT)
4. Reboot the ESP32

## Configuration

Example `config.json`:

```json
{
  "wifi": {
    "ssid": "your_wifi_network",
    "password": "your_wifi_password",
    "timeout": 30,
    "retry_attempts": 3
  },
  "hardware": {
    "i2c": { "sda_pin": 4, "scl_pin": 16, "frequency": 100000 },
    "addresses": { "inputs_1_8": 58, "inputs_9_16": 33, "pca9685": 64 },
    "relays": { "relay1_pin": 13, "relay2_pin": 2 },
    "inputs": { "gpio17_pin": 34, "gpio18_pin": 35 }
  },
  "system": {
    "debug": false,
    "log_level": "INFO",
    "gc_interval": 10000,
    "input_scan_interval": 10
  },
  "mqtt": {
    "enabled": true,
    "host": "192.168.1.10",
    "port": 1883,
    "username": "kc868",
    "password": "your_password",
    "client_id": "kc868-ap-esp32",
    "base_topic": "kc868-ap",
    "discovery_prefix": "homeassistant"
  }
}
```

Notes:
- Use a dedicated MQTT user (not the internal `homeassistant` user).
- The discovery prefix must match HA (default `homeassistant`).

## Home Assistant

- Ensure the MQTT integration is installed and connected to your broker.
- On boot, the device publishes discovery for:
  - Lights: `homeassistant/light/kc868-ap_dimmer_{0..15}/config`
  - Switches: `homeassistant/switch/kc868-ap_relay_{1..2}/config`
  - Binary sensors: `homeassistant/binary_sensor/kc868-ap_input_{01..16}/config`
- Availability (retained): `kc868-ap/availability` → `online`/`offline`

### Entity Behavior

- Lights (dimmers):
  - ON sets 100% brightness
  - OFF sets 0%
  - Brightness slider uses 0–100 scale
- Switches (relays): ON/OFF
- Inputs: ON when active, OFF when inactive

## Architecture

- `main.py`: App lifecycle, Wi‑Fi, input scanner, fast MQTT loop, command handling
- `mqtt_manager.py`: MQTT connect/subscribe/publish, HA discovery + availability
- `hardware.py`: PCA9685 dimmers, PCF8574 inputs, relay control
- `config.py`: Load/validate config; provide Pin objects and I2C addresses
- `network_manager.py`: Reliable Wi‑Fi connect with retries
- `logger.py`: Structured logging

## MQTT Topics (base_topic: `kc868-ap`)

- Availability (retained): `kc868-ap/availability` → `online`/`offline`
- Commands:
  - Dimmer: `kc868-ap/dimmer/{index}/set`
    - JSON: `{ "state": "ON"|"OFF", "brightness": 0..100 }`
    - Or plain: `ON` / `OFF` / `0..100`
  - Relay: `kc868-ap/relay/{index}/set` (`ON`/`OFF`)
- State (retained):
  - Dimmer: `kc868-ap/dimmer/{index}/state` → `{ "state": "ON"|"OFF", "brightness": 0..100 }`
  - Relay: `kc868-ap/relay/{index}/state` → `ON`/`OFF`
  - Input: `kc868-ap/input/{index}/state` → `ON`/`OFF`

## Troubleshooting

- No devices appear in HA:
  - Verify HA MQTT integration is connected to the same broker
  - Listen to `homeassistant/#` in HA MQTT panel and reboot the device; discovery JSON must appear (retained)
  - Ensure `mqtt.discovery_prefix` matches HA
  - Avoid using username `homeassistant` for devices
- Commands are delayed:
  - A dedicated fast MQTT loop runs every 50 ms; verify Wi‑Fi signal and broker load
- Dimmer ON toggles OFF immediately:
  - Behavior now forces ON → 100%, OFF → 0%. Confirm the command payloads in HA MQTT “Listen”

## Logging

Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Enable debug in `config.json` → `system.debug: true`, `system.log_level: "DEBUG"`

## License

Open source. See the license file.

## Changelog

- Switched to MQTT-only architecture; removed web server/UI
- Added HA MQTT autodiscovery, availability, and fast command loop
- Standardized light behavior (ON=100%, OFF=0%)
