"""
Configuration management for KC868-AP Control System
Handles secure storage and retrieval of configuration parameters
"""

import ujson
import uos
from machine import Pin

class Config:
    """Configuration management class with secure defaults"""
    
    # Default configuration
    DEFAULT_CONFIG = {
        "wifi": {
            "ssid": "",
            "password": "",
            "timeout": 30,
            "retry_attempts": 3
        },
        "server": {
            "host": "0.0.0.0",
            "port": 80,
            "websocket_timeout": 180
        },
        "hardware": {
            "i2c": {
                "sda_pin": 4,
                "scl_pin": 16,
                "frequency": 100000
            },
            "addresses": {
                "inputs_1_8": 0x3A,
                "inputs_9_16": 0x21,
                "pca9685": 0x40
            },
            "relays": {
                "relay1_pin": 13,
                "relay2_pin": 2
            },
            "inputs": {
                "gpio17_pin": 34,
                "gpio18_pin": 35
            }
        },
        "system": {
            "debug": False,
            "log_level": "INFO",
            "gc_interval": 10000,  # milliseconds
            "input_scan_interval": 10  # milliseconds
        },
        "mqtt": {
            "enabled": True,
            "host": "",
            "port": 1883,
            "username": "",
            "password": "",
            "client_id": "kc868-ap",
            "base_topic": "kc868-ap",
            "discovery_prefix": "homeassistant"
        }
    }
    
    CONFIG_FILE = "config.json"
    
    def __init__(self):
        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()
    
    def load_config(self):
        """Load configuration from file or create default"""
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                file_config = ujson.load(f)
                self._merge_config(self.config, file_config)
                print("Configuration loaded successfully")
        except (OSError, ValueError) as e:
            print(f"Could not load config file: {e}")
            print("Using default configuration")
            self.save_config()  # Save default config
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                ujson.dump(self.config, f)
                print("Configuration saved successfully")
        except OSError as e:
            print(f"Could not save config file: {e}")
    
    def _merge_config(self, base, override):
        """Recursively merge configuration dictionaries"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get(self, key_path, default=None):
        """Get configuration value using dot notation (e.g., 'wifi.ssid')"""
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path, value):
        """Set configuration value using dot notation"""
        keys = key_path.split('.')
        config = self.config
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
    
    def validate_wifi_config(self):
        """Validate WiFi configuration"""
        ssid = self.get('wifi.ssid')
        password = self.get('wifi.password')
        
        if not ssid:
            raise ValueError("WiFi SSID is required")
        
        if len(ssid) > 32:
            raise ValueError("WiFi SSID too long (max 32 characters)")
        
        if password and len(password) < 8:
            raise ValueError("WiFi password too short (min 8 characters)")
        
        return True
    
    def get_hardware_pins(self):
        """Get hardware pin configuration as Pin objects"""
        i2c_config = self.get('hardware.i2c')
        relay_config = self.get('hardware.relays')
        input_config = self.get('hardware.inputs')
        
        return {
            'i2c_sda': Pin(i2c_config['sda_pin']),
            'i2c_scl': Pin(i2c_config['scl_pin']),
            'relay1': Pin(relay_config['relay1_pin'], Pin.OUT),
            'relay2': Pin(relay_config['relay2_pin'], Pin.OUT),
            'input_gpio17': Pin(input_config['gpio17_pin'], Pin.IN, Pin.PULL_UP),
            'input_gpio18': Pin(input_config['gpio18_pin'], Pin.IN, Pin.PULL_UP)
        }
    
    def get_i2c_addresses(self):
        """Get I2C device addresses"""
        return self.get('hardware.addresses')
    
    def is_debug_mode(self):
        """Check if debug mode is enabled"""
        return self.get('system.debug', False)
    
    def get_log_level(self):
        """Get logging level"""
        return self.get('system.log_level', 'INFO')

# Global configuration instance
config = Config()
