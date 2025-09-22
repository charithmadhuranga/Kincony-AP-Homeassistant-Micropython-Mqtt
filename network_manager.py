"""
Network management for KC868-AP Control System
Handles WiFi connection with retry logic and error recovery
"""

import time
import network
from logger import logger
from config import config

class NetworkError(Exception):
    """Custom exception for network-related errors"""
    pass

class NetworkManager:
    """Manages WiFi connection with robust error handling"""
    
    def __init__(self):
        self.wlan = network.WLAN(network.STA_IF)
        self.connected = False
        self.connection_attempts = 0
        self.max_retries = config.get('wifi.retry_attempts', 3)
        self.timeout = config.get('wifi.timeout', 30)
        
    def connect(self):
        """Connect to WiFi with retry logic"""
        ssid = config.get('wifi.ssid')
        password = config.get('wifi.password')
        
        if not ssid:
            raise NetworkError("WiFi SSID not configured")
        
        logger.info(f"Connecting to WiFi: {ssid}")
        
        # Validate configuration
        try:
            config.validate_wifi_config()
        except ValueError as e:
            raise NetworkError(f"Invalid WiFi configuration: {e}")
        
        # Activate station mode
        if not self.wlan.active():
            self.wlan.active(True)
            time.sleep(1)
        
        # Disconnect if already connected
        if self.wlan.isconnected():
            self.wlan.disconnect()
            time.sleep(1)
        
        # Attempt connection with retries
        for attempt in range(self.max_retries):
            try:
                self.connection_attempts = attempt + 1
                logger.info(f"Connection attempt {self.connection_attempts}/{self.max_retries}")
                
                # Connect to network
                self.wlan.connect(ssid, password)
                
                # Wait for connection with timeout
                start_time = time.ticks_ms()
                while not self.wlan.isconnected():
                    if time.ticks_diff(time.ticks_ms(), start_time) > (self.timeout * 1000):
                        raise NetworkError("Connection timeout")
                    time.sleep(0.1)
                
                # Verify connection
                if self.wlan.isconnected():
                    self.connected = True
                    config_info = self.wlan.ifconfig()
                    logger.info(f"WiFi connected successfully!")
                    logger.info(f"IP: {config_info[0]}")
                    logger.info(f"Subnet: {config_info[1]}")
                    logger.info(f"Gateway: {config_info[2]}")
                    logger.info(f"DNS: {config_info[3]}")
                    return True
                
            except Exception as e:
                logger.warning(f"Connection attempt {self.connection_attempts} failed: {e}")
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"All connection attempts failed")
                    raise NetworkError(f"Failed to connect after {self.max_retries} attempts: {e}")
        
        return False
    
    def disconnect(self):
        """Disconnect from WiFi"""
        if self.wlan.isconnected():
            self.wlan.disconnect()
            self.connected = False
            logger.info("WiFi disconnected")
    
    def is_connected(self):
        """Check if WiFi is connected"""
        return self.wlan.isconnected() and self.connected
    
    def get_config(self):
        """Get current network configuration"""
        if self.is_connected():
            return self.wlan.ifconfig()
        return None
    
    def get_status(self):
        """Get detailed connection status"""
        status = {
            'connected': self.is_connected(),
            'ssid': config.get('wifi.ssid', 'Not configured'),
            'attempts': self.connection_attempts,
            'max_retries': self.max_retries
        }
        
        if self.is_connected():
            config_info = self.get_config()
            status.update({
                'ip': config_info[0],
                'subnet': config_info[1],
                'gateway': config_info[2],
                'dns': config_info[3]
            })
        
        return status
    
    def reconnect(self):
        """Force reconnection"""
        logger.info("Forcing WiFi reconnection...")
        self.disconnect()
        time.sleep(2)
        return self.connect()

# Global network manager instance
network_manager = None

def get_network_manager():
    """Get the global network manager instance"""
    global network_manager
    if network_manager is None:
        network_manager = NetworkManager()
    return network_manager

def wait_for_connection():
    """Wait for network connection to be established"""
    nm = get_network_manager()
    
    if not nm.is_connected():
        logger.info("Waiting for network connection...")
        try:
            nm.connect()
        except NetworkError as e:
            logger.error(f"Network connection failed: {e}")
            raise
    
    return nm.get_config()
