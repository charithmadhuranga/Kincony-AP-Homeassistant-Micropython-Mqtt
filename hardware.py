"""
Hardware abstraction layer for KC868-AP Control System
Provides robust interfaces for I2C devices with error handling and recovery
"""

import time
import math
from machine import I2C, Pin
from logger import logger
from config import config

class HardwareError(Exception):
    """Custom exception for hardware-related errors"""
    pass

class I2CDevice:
    """Base class for I2C devices with error handling"""
    
    def __init__(self, i2c_bus, address, name="I2CDevice"):
        self.i2c = i2c_bus
        self.address = address
        self.name = name
        self.is_valid = False
        self.retry_count = 3
        self.retry_delay = 0.01  # 10ms
        
        self._initialize()
    
    def _initialize(self):
        """Initialize the device and verify connection"""
        try:
            # Scan I2C bus to check if device is present
            devices = self.i2c.scan()
            if self.address not in devices:
                logger.warning(f"{self.name} not found at address 0x{self.address:02X}")
                return
            
            self.is_valid = True
            logger.info(f"{self.name} initialized at address 0x{self.address:02X}")
            
        except Exception as e:
            logger.error(f"Failed to initialize {self.name}: {e}")
            self.is_valid = False
    
    def _retry_operation(self, operation, *args, **kwargs):
        """Retry an operation with exponential backoff"""
        last_exception = None
        
        for attempt in range(self.retry_count):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                    logger.debug(f"{self.name} operation failed, retrying... (attempt {attempt + 1})")
                else:
                    logger.error(f"{self.name} operation failed after {self.retry_count} attempts: {e}")
        
        raise HardwareError(f"{self.name} operation failed: {last_exception}")

class PCF8574(I2CDevice):
    """PCF8574 I/O expander for digital inputs"""
    
    def __init__(self, i2c_bus, address, name="PCF8574"):
        super().__init__(i2c_bus, address, name)
    
    def read_all(self):
        """Read all 8 input pins"""
        if not self.is_valid:
            return None
        
        def _read():
            return self.i2c.readfrom(self.address, 1)[0]
        
        try:
            return self._retry_operation(_read)
        except HardwareError:
            return None
    
    def read_pin(self, pin_number):
        """Read a specific pin (0-7)"""
        if not (0 <= pin_number <= 7):
            raise ValueError("Pin number must be between 0 and 7")
        
        all_pins = self.read_all()
        if all_pins is None:
            return None
        
        return bool(all_pins & (1 << pin_number))

class PCA9685(I2CDevice):
    """PCA9685 PWM controller for dimmer outputs"""
    
    # Register addresses
    MODE1 = 0x00
    MODE2 = 0x01
    PRESCALE = 0xFE
    LED0_ON_L = 0x06
    LED0_ON_H = 0x07
    LED0_OFF_L = 0x08
    LED0_OFF_H = 0x09
    
    def __init__(self, i2c_bus, address, freq=500, name="PCA9685"):
        super().__init__(i2c_bus, address, name)
        self.frequency = freq
        
        if self.is_valid:
            self._setup()
    
    def _setup(self):
        """Setup PCA9685 for operation"""
        try:
            self.reset()
            self.set_frequency(self.frequency)
            logger.info(f"{self.name} setup complete, frequency: {self.frequency}Hz")
        except Exception as e:
            logger.error(f"Failed to setup {self.name}: {e}")
            self.is_valid = False
    
    def _write(self, reg, value):
        """Write to a register"""
        if not self.is_valid:
            return
        
        def _write_operation():
            self.i2c.writeto(self.address, bytes([reg, value]))
        
        self._retry_operation(_write_operation)
    
    def _read(self, reg):
        """Read from a register"""
        if not self.is_valid:
            return None
        
        def _read_operation():
            return self.i2c.readfrom_mem(self.address, reg, 1)[0]
        
        try:
            return self._retry_operation(_read_operation)
        except HardwareError:
            return None
    
    def reset(self):
        """Reset the PCA9685"""
        self._write(self.MODE1, 0x00)  # Normal mode
        time.sleep(0.01)
    
    def set_frequency(self, freq_hz):
        """Set PWM frequency"""
        if not (24 <= freq_hz <= 1526):
            raise ValueError("Frequency must be between 24Hz and 1526Hz")
        
        # Calculate prescale value
        prescaleval = 25000000.0  # 25MHz
        prescaleval /= 4096.0     # 12-bit
        prescaleval /= float(freq_hz)
        prescaleval -= 1.0
        prescale = int(math.floor(prescaleval + 0.5))
        
        # Update frequency
        oldmode = self._read(self.MODE1)
        newmode = (oldmode & 0x7F) | 0x10  # Sleep mode
        self._write(self.MODE1, newmode)
        self._write(self.PRESCALE, prescale)
        self._write(self.MODE1, oldmode)
        time.sleep(0.005)
        self._write(self.MODE1, oldmode | 0xa1)  # Restart and auto-increment
        
        self.frequency = freq_hz
    
    def set_pwm(self, channel, on, off):
        """Set PWM values for a channel"""
        if not (0 <= channel <= 15):
            raise ValueError("Channel must be between 0 and 15")
        
        if not (0 <= on <= 4095) or not (0 <= off <= 4095):
            raise ValueError("PWM values must be between 0 and 4095")
        
        base_reg = self.LED0_ON_L + 4 * channel
        
        self._write(base_reg, on & 0xFF)
        self._write(base_reg + 1, on >> 8)
        self._write(base_reg + 2, off & 0xFF)
        self._write(base_reg + 3, off >> 8)
    
    def set_level(self, channel, level_percent):
        """Set dimmer level as percentage (0-100)"""
        if not (0 <= channel <= 15):
            raise ValueError("Channel must be between 0 and 15")
        
        level_percent = max(0, min(100, level_percent))
        pulse = int(level_percent * 4095 / 100)
        self.set_pwm(channel, 0, pulse)
        
        logger.debug(f"Set channel {channel} to {level_percent}%")
    
    def all_off(self):
        """Turn off all channels"""
        for channel in range(16):
            self.set_level(channel, 0)
        logger.info("All PCA9685 channels turned off")

class RelayController:
    """Controller for relay outputs"""
    
    def __init__(self, relay1_pin, relay2_pin):
        self.relay1 = relay1_pin
        self.relay2 = relay2_pin
        self.states = {"Relay1": False, "Relay2": False}
        
        # Initialize relays to OFF
        self.relay1.value(0)
        self.relay2.value(0)
        
        logger.info("Relay controller initialized")
    
    def set_relay(self, relay_name, state):
        """Set relay state (True=ON, False=OFF)"""
        if relay_name not in self.states:
            raise ValueError(f"Invalid relay name: {relay_name}")
        
        if relay_name == "Relay1":
            self.relay1.value(1 if state else 0)
        elif relay_name == "Relay2":
            self.relay2.value(1 if state else 0)
        
        self.states[relay_name] = state
        logger.debug(f"Set {relay_name} to {'ON' if state else 'OFF'}")
    
    def toggle_relay(self, relay_name):
        """Toggle relay state"""
        if relay_name not in self.states:
            raise ValueError(f"Invalid relay name: {relay_name}")
        
        new_state = not self.states[relay_name]
        self.set_relay(relay_name, new_state)
        return new_state
    
    def get_state(self, relay_name):
        """Get current relay state"""
        if relay_name not in self.states:
            raise ValueError(f"Invalid relay name: {relay_name}")
        
        return self.states[relay_name]
    
    def all_off(self):
        """Turn off all relays"""
        self.set_relay("Relay1", False)
        self.set_relay("Relay2", False)
        logger.info("All relays turned off")

class HardwareManager:
    """Central hardware management class"""
    
    def __init__(self):
        self.config = config
        self.pins = config.get_hardware_pins()
        self.addresses = config.get_i2c_addresses()
        
        # Initialize I2C bus
        try:
            self.i2c = I2C(0, sda=self.pins['i2c_sda'], scl=self.pins['i2c_scl'])
            logger.info("I2C bus initialized")
        except Exception as e:
            logger.error(f"Failed to initialize I2C bus: {e}")
            raise HardwareError("I2C initialization failed")
        
        # Initialize hardware devices
        self._initialize_devices()
    
    def _initialize_devices(self):
        """Initialize all hardware devices"""
        try:
            # Initialize PCF8574 input expanders
            self.pcf_inputs_1_8 = PCF8574(
                self.i2c, 
                self.addresses['inputs_1_8'], 
                "PCF8574_Inputs_1_8"
            )
            
            self.pcf_inputs_9_16 = PCF8574(
                self.i2c, 
                self.addresses['inputs_9_16'], 
                "PCF8574_Inputs_9_16"
            )
            
            # Initialize PCA9685 PWM controller
            self.pca9685 = PCA9685(
                self.i2c, 
                self.addresses['pca9685'],
                freq=500,
                name="PCA9685_Dimmers"
            )
            
            # Initialize relay controller
            self.relay_controller = RelayController(
                self.pins['relay1'],
                self.pins['relay2']
            )
            
            logger.info("All hardware devices initialized successfully")
            
        except Exception as e:
            logger.error(f"Hardware initialization failed: {e}")
            raise HardwareError("Hardware initialization failed")
    
    def get_input_states(self):
        """Get current state of all inputs"""
        states = {}
        
        # Read PCF8574 inputs 1-8
        if self.pcf_inputs_1_8.is_valid:
            pcf1_data = self.pcf_inputs_1_8.read_all()
            if pcf1_data is not None:
                for i in range(8):
                    states[f"X{i+1:02d}"] = not bool(pcf1_data & (1 << i))
        
        # Read PCF8574 inputs 9-16
        if self.pcf_inputs_9_16.is_valid:
            pcf2_data = self.pcf_inputs_9_16.read_all()
            if pcf2_data is not None:
                for i in range(8):
                    states[f"X{i+9:02d}"] = not bool(pcf2_data & (1 << i))
        
        return states
    
    def get_relay_states(self):
        """Get current relay states"""
        return {
            "Relay1": self.relay_controller.get_state("Relay1"),
            "Relay2": self.relay_controller.get_state("Relay2")
        }
    
    def shutdown(self):
        """Safely shutdown all hardware"""
        logger.info("Shutting down hardware...")
        
        try:
            # Turn off all dimmers
            if self.pca9685.is_valid:
                self.pca9685.all_off()
            
            # Turn off all relays
            self.relay_controller.all_off()
            
            logger.info("Hardware shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during hardware shutdown: {e}")

# Global hardware manager instance
hardware_manager = None

def get_hardware_manager():
    """Get the global hardware manager instance"""
    global hardware_manager
    if hardware_manager is None:
        hardware_manager = HardwareManager()
    return hardware_manager
