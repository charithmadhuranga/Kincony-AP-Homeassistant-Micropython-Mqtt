"""
Main application for KC868-AP Control System using Microdot
Refactored to use the Microdot web framework for better reliability
"""

import uasyncio as asyncio
import ujson
import gc
import _thread
import sys
import time
from machine import Pin

# Import our modules
from config import config
from logger import logger
from hardware import get_hardware_manager, HardwareError
from network_manager import get_network_manager, NetworkError
from mqtt_manager import get_mqtt_manager, MQTTUnavailable

class ApplicationError(Exception):
    """Custom exception for application errors"""
    pass

class StateManager:
    """Manages application state with thread safety"""
    
    def __init__(self):
        self.lock = _thread.allocate_lock()
        self.dimmer_levels = {f"PWM{i}": 0 for i in range(16)}
        self.last_non_zero_levels = {f"PWM{i}": 100 for i in range(16)}
        self.relay_states = {"Relay1": False, "Relay2": False}
        self.input_states = {}
        self.last_update = time.ticks_ms()
    
    def get_state(self):
        """Get current application state"""
        with self.lock:
            return {
                "dimmers": self.dimmer_levels.copy(),
                "relays": self.relay_states.copy(),
                "inputs": self.input_states.copy(),
                "timestamp": self.last_update
            }
    
    def update_dimmer(self, channel, level):
        """Update dimmer level"""
        if not (0 <= level <= 100):
            raise ValueError("Dimmer level must be between 0 and 100")
        
        with self.lock:
            self.dimmer_levels[channel] = level
            if level > 0:
                self.last_non_zero_levels[channel] = level
            self.last_update = time.ticks_ms()
    
    def update_relay(self, relay_name, state):
        """Update relay state"""
        if relay_name not in self.relay_states:
            raise ValueError(f"Invalid relay name: {relay_name}")
        
        with self.lock:
            self.relay_states[relay_name] = bool(state)
            self.last_update = time.ticks_ms()
    
    def update_inputs(self, inputs):
        """Update input states"""
        with self.lock:
            self.input_states.update(inputs)
            self.last_update = time.ticks_ms()

class CommandProcessor:
    """Processes commands from WebSocket clients"""
    
    def __init__(self, state_manager, hardware_manager):
        self.state_manager = state_manager
        self.hardware_manager = hardware_manager
    
    async def process_command(self, command):
        """Process a command from WebSocket client"""
        try:
            command_type = command.get('type')
            
            if command_type == 'set_dimmer':
                await self._handle_dimmer_command(command)
            elif command_type == 'toggle_relay':
                await self._handle_relay_command(command)
            elif command_type == 'get_state':
                return self.state_manager.get_state()
            else:
                raise ValueError(f"Unknown command type: {command_type}")
            
            return {"status": "success", "command": command}
            
        except Exception as e:
            logger.error(f"Command processing error: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _handle_dimmer_command(self, command):
        """Handle dimmer control command"""
        channel = command.get('channel')
        value = int(command.get('value', 0))
        
        if not channel or not channel.startswith('PWM'):
            raise ValueError("Invalid dimmer channel")
        
        channel_num = int(channel.replace('PWM', ''))
        if not (0 <= channel_num <= 15):
            raise ValueError("Dimmer channel must be between 0 and 15")
        
        # Update hardware
        self.hardware_manager.pca9685.set_level(channel_num, value)
        
        # Update state
        self.state_manager.update_dimmer(channel, value)
        
        logger.info(f"Set {channel} to {value}%")
    
    async def _handle_relay_command(self, command):
        """Handle relay control command"""
        channel = command.get('channel')
        
        if channel not in self.state_manager.relay_states:
            raise ValueError(f"Invalid relay channel: {channel}")
        
        # Toggle relay
        new_state = self.hardware_manager.relay_controller.toggle_relay(channel)
        
        # Update state
        self.state_manager.update_relay(channel, new_state)
        
        logger.info(f"Toggled {channel} to {'ON' if new_state else 'OFF'}")

class InputScanner:
    """Scans hardware inputs and updates state"""
    
    def __init__(self, state_manager, hardware_manager):
        self.state_manager = state_manager
        self.hardware_manager = hardware_manager
        self.running = False
        self.scan_interval = config.get('system.input_scan_interval', 10)
    
    def start(self):
        """Start input scanning in a separate thread"""
        self.running = True
        _thread.start_new_thread(self._scan_loop, ())
        logger.info("Input scanner started")
    
    def stop(self):
        """Stop input scanning"""
        self.running = False
        logger.info("Input scanner stopped")
    
    def _scan_loop(self):
        """Main scanning loop (runs in separate thread)"""
        prev_inputs = {}
        while self.running:
            try:
                # Get current input states
                current_inputs = self.hardware_manager.get_input_states()

                # Check for changes
                if current_inputs != prev_inputs:
                    # Log significant changes using previous snapshot
                    for input_name, state in current_inputs.items():
                        prev_state = prev_inputs.get(input_name)
                        if prev_state is None or prev_state != state:
                            logger.debug(f"Input {input_name}: {'ON' if state else 'OFF'}")

                    # Update state and snapshot
                    self.state_manager.update_inputs(current_inputs)
                    prev_inputs = current_inputs.copy()

                time.sleep_ms(self.scan_interval)

            except Exception as e:
                logger.error(f"Input scanning error: {e}")
                time.sleep_ms(100)  # Wait before retrying

class KC868Application:
    """Main application class (MQTT-only)"""
    
    def __init__(self):
        self.state_manager = StateManager()
        self.hardware_manager = None
        self.network_manager = None
        self.command_processor = None
        self.input_scanner = None
        self.running = False
        # No web server in MQTT-only mode
        
        # No HTTP routes; MQTT-only
    
    # Web server and websocket removed
    
    async def _broadcast_state(self):
        """Publish current state via MQTT (no web)."""
        try:
            state = self.state_manager.get_state()
            # Publish MQTT state when available
            if self.mqtt and self.mqtt.connected:
                # Dimmers
                for i in range(16):
                    level = state['dimmers'].get(f"PWM{i}")
                    if level is not None:
                        self.mqtt.publish_dimmer_state(i, level)
                # Relays
                for i in range(1, 3):
                    is_on = state['relays'].get(f"Relay{i}")
                    if is_on is not None:
                        self.mqtt.publish_relay_state(i, is_on)
                # Inputs
                for i in range(1, 17):
                    val = state['inputs'].get(f"X{i:02d}")
                    if val is not None:
                        self.mqtt.publish_input_state(i, val)
        except Exception as e:
            logger.error(f"State broadcast error: {e}")
    
    async def _periodic_tasks(self):
        """Run periodic maintenance tasks"""
        gc_interval = config.get('system.gc_interval', 10000)
        last_gc = time.ticks_ms()
        last_discovery = 0
        
        while self.running:
            try:
                current_time = time.ticks_ms()
                
                # Garbage collection
                if time.ticks_diff(current_time, last_gc) > gc_interval:
                    gc.collect()
                    last_gc = current_time
                    logger.debug("Garbage collection performed")
                
                # Broadcast state periodically
                await self._broadcast_state()
                
                # Periodically republish discovery (every 60s)
                if self.mqtt and self.mqtt.connected:
                    if last_discovery == 0 or time.ticks_diff(current_time, last_discovery) > 60000:
                        try:
                            self.mqtt.publish_discovery()
                            last_discovery = current_time
                        except Exception as e:
                            logger.debug(f"Discovery republish failed: {e}")
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Periodic task error: {e}")
                await asyncio.sleep(1)

    async def _mqtt_loop(self):
        """Fast MQTT processing loop to minimize command latency"""
        while self.running:
            try:
                if self.mqtt and self.mqtt.connected:
                    self.mqtt.loop()
                await asyncio.sleep(0.05)  # 50ms
            except Exception as e:
                logger.debug(f"MQTT loop error: {e}")
                await asyncio.sleep(0.2)

    def _on_mqtt_command(self, topic, payload):
        """Handle MQTT command topics"""
        try:
            base = config.get('mqtt.base_topic', 'kc868-ap')
            # Dimmer command: base/dimmer/{idx}/set
            if topic.startswith(f"{base}/dimmer/") and topic.endswith('/set'):
                idx = int(topic.split('/')[2])
                level = None
                if isinstance(payload, dict):
                    # Support schema {state, brightness}
                    if 'brightness' in payload:
                        level = int(payload['brightness'])
                    if 'state' in payload:
                        state_str = str(payload['state']).upper()
                        if state_str == 'OFF':
                            level = 0
                        elif state_str == 'ON' and level is None:
                            # Turn on without brightness -> force 100%
                            level = 100
                else:
                    # Accept plain ON/OFF or numeric brightness
                    if isinstance(payload, str):
                        up = payload.upper()
                        if up == 'OFF':
                            level = 0
                        elif up == 'ON':
                            level = 100
                        else:
                            try:
                                level = int(payload)
                            except Exception:
                                level = 0
                    else:
                        try:
                            level = int(payload)
                        except Exception:
                            level = 0
                if 0 <= idx <= 15:
                    self.hardware_manager.pca9685.set_level(idx, max(0, min(100, int(level))))
                    self.state_manager.update_dimmer(f"PWM{idx}", max(0, min(100, int(level))))
                    if self.mqtt:
                        self.mqtt.publish_dimmer_state(idx, max(0, min(100, int(level))))
            # Relay command: base/relay/{i}/set (ON/OFF)
            elif topic.startswith(f"{base}/relay/") and topic.endswith('/set'):
                idx = int(topic.split('/')[2])
                channel = f"Relay{idx}"
                if channel in self.state_manager.relay_states:
                    desired = None
                    if isinstance(payload, str):
                        desired = (payload.upper() == 'ON')
                    elif isinstance(payload, dict) and 'state' in payload:
                        desired = (str(payload['state']).upper() == 'ON')
                    if desired is None:
                        desired = not self.state_manager.relay_states[channel]
                    self.hardware_manager.relay_controller.set_relay(channel, desired)
                    self.state_manager.update_relay(channel, desired)
                    if self.mqtt:
                        self.mqtt.publish_relay_state(idx, desired)
        except Exception as e:
            logger.debug(f"MQTT command handling error: {e}")
    
    async def initialize(self):
        """Initialize the application"""
        try:
            logger.info("Initializing KC868-AP Application with Microdot")
            
            # Initialize hardware
            logger.info("Initializing hardware...")
            self.hardware_manager = get_hardware_manager()
            
            # Initialize network
            logger.info("Initializing network...")
            self.network_manager = get_network_manager()
            
            if not self.network_manager.is_connected():
                logger.error("Network not connected")
                raise ApplicationError("Network connection required")
            
            # Initialize command processor
            self.command_processor = CommandProcessor(
                self.state_manager, 
                self.hardware_manager
            )
            
            # Initialize input scanner
            self.input_scanner = InputScanner(
                self.state_manager,
                self.hardware_manager
            )

            # Initialize MQTT (optional)
            try:
                self.mqtt = get_mqtt_manager(self._on_mqtt_command)
                if self.mqtt.enabled:
                    self.mqtt.connect()
                    self.mqtt.publish_discovery()
            except MQTTUnavailable as e:
                logger.info(f"MQTT unavailable: {e}")
            except Exception as e:
                logger.warning(f"MQTT init failed: {e}")
            
            logger.info("Application initialization complete")
            return True
            
        except Exception as e:
            logger.critical(f"Application initialization failed: {e}")
            return False
    
    async def run(self):
        """Run the main application"""
        try:
            if not await self.initialize():
                raise ApplicationError("Initialization failed")
            
            self.running = True
            
            # Start input scanner
            self.input_scanner.start()
            
            # Start periodic tasks
            periodic_task = asyncio.create_task(self._periodic_tasks())
            mqtt_task = asyncio.create_task(self._mqtt_loop())

            # Keep the application running (no web server)
            while self.running:
                await asyncio.sleep(1)
            
        except KeyboardInterrupt:
            logger.info("Application stopped by user")
        except Exception as e:
            logger.critical(f"Application error: {e}")
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the application gracefully"""
        logger.info("Shutting down application...")
        
        self.running = False
        
        try:
            # Stop input scanner
            if self.input_scanner:
                self.input_scanner.stop()
            
            # Shutdown hardware
            if self.hardware_manager:
                self.hardware_manager.shutdown()
            
            # Disconnect MQTT
            if self.mqtt and self.mqtt.connected:
                try:
                    self.mqtt.disconnect()
                except Exception:
                    pass
            
            logger.info("Application shutdown complete")
            
        except Exception as e:
            logger.error(f"Shutdown error: {e}")

# Global application instance
app = None

async def main():
    """Main entry point"""
    global app
    
    try:
        # Wait for network connection
        network_manager = get_network_manager()
        if not network_manager.is_connected():
            logger.info("Waiting for network connection...")
            network_manager.connect()
        
        # Create and run application
        app = KC868Application()
        await app.run()
        
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.critical(f"Application failed: {e}")
    finally:
        if app:
            await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
