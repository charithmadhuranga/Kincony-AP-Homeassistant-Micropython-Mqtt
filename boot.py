"""
Boot configuration for KC868-AP Control System
Handles system initialization and network setup
"""

import esp
import gc
import sys
from machine import Pin

# Disable debug output for production
esp.osdebug(None)

# Enable garbage collection
gc.collect()

# Import configuration and logging
try:
    from config import config
    from logger import logger
    from network_manager import get_network_manager
except ImportError as e:
    print(f"Failed to import modules: {e}")
    sys.exit(1)

def initialize_system():
    """Initialize the system with proper error handling"""
    try:
        logger.info("Starting KC868-AP Control System")
        
        # Initialize network
        network_manager = get_network_manager()
        
        # Check if WiFi is configured
        ssid = config.get('wifi.ssid')
        if not ssid:
            logger.error("WiFi not configured. Please set wifi.ssid in config.json")
            return False
        
        # Connect to WiFi
        logger.info("Connecting to WiFi...")
        network_manager.connect()
        
        if network_manager.is_connected():
            logger.info("System initialization complete")
            return True
        else:
            logger.error("Failed to connect to WiFi")
            return False
            
    except Exception as e:
        logger.critical(f"System initialization failed: {e}")
        return False

def main():
    """Main boot sequence"""
    # Initialize system
    if not initialize_system():
        logger.critical("Boot failed - system will not start")
        return
    
    # Initialize status LED
    try:
        led = Pin(2, Pin.OUT)
        led.value(1)  # Turn on LED to indicate successful boot
        logger.info("Status LED initialized")
    except Exception as e:
        logger.warning(f"Could not initialize status LED: {e}")
    
    logger.info("Boot sequence completed successfully")

if __name__ == "__main__":
    main()

