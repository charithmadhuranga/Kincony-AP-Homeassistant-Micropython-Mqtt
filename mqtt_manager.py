"""
MQTT manager with Home Assistant autodiscovery for KC868-AP
"""

import ujson
import time
from logger import logger
from config import config

try:
    from umqtt.simple import MQTTClient
except Exception as e:
    MQTTClient = None


class MQTTUnavailable(Exception):
    pass


class MQTTManager:
    def __init__(self, on_command_callback):
        self.enabled = bool(config.get('mqtt.enabled', False))
        self.client = None
        self.on_command = on_command_callback
        self.client_id = config.get('mqtt.client_id', 'kc868-ap')
        self.base_topic = config.get('mqtt.base_topic', 'kc868-ap')
        self.discovery_prefix = config.get('mqtt.discovery_prefix', 'homeassistant')
        self.connected = False
        self.availability_topic = f"{self.base_topic}/availability"

    def _ensure_supported(self):
        if not self.enabled:
            raise MQTTUnavailable('MQTT disabled')
        if MQTTClient is None:
            raise MQTTUnavailable('umqtt is not available')

    def connect(self):
        self._ensure_supported()
        host = config.get('mqtt.host')
        port = int(config.get('mqtt.port', 1883))
        user = config.get('mqtt.username') or None
        password = config.get('mqtt.password') or None
        self.client = MQTTClient(self.client_id, host, port, user, password)
        self.client.set_callback(self._on_message)
        # Set LWT (offline)
        try:
            self.client.set_last_will(self.availability_topic, b"offline", retain=True, qos=0)
        except Exception:
            pass
        self.client.connect()
        self.connected = True
        logger.info('MQTT connected')
        # Publish online availability
        try:
            self.publish(self.availability_topic, b"online", retain=True)
        except Exception:
            pass
        # Listen for HA birth to republish discovery
        try:
            self.subscribe("homeassistant/status")
        except Exception:
            pass

    def disconnect(self):
        try:
            if self.client:
                # Proactively publish offline
                try:
                    self.publish(self.availability_topic, b"offline", retain=True)
                except Exception:
                    pass
                self.client.disconnect()
        except Exception:
            pass
        self.connected = False

    def loop(self):
        if self.connected and self.client:
            try:
                self.client.check_msg()
            except Exception as e:
                logger.warning(f"MQTT check_msg failed: {e}")

    def publish(self, topic, payload, retain=False):
        try:
            if not isinstance(payload, (bytes, bytearray)):
                payload = ujson.dumps(payload).encode('utf-8') if isinstance(payload, (dict, list)) else str(payload).encode('utf-8')
            self.client.publish(topic, payload, retain=retain)
        except Exception as e:
            logger.debug(f"MQTT publish failed: {e}")

    def subscribe(self, topic):
        try:
            self.client.subscribe(topic)
        except Exception as e:
            logger.debug(f"MQTT subscribe failed: {e}")

    def _on_message(self, topic, msg):
        try:
            topic = topic.decode() if isinstance(topic, (bytes, bytearray)) else topic
            data = None
            try:
                data = ujson.loads(msg)
            except Exception:
                data = msg.decode() if isinstance(msg, (bytes, bytearray)) else str(msg)
            # If HA announces online, republish discovery
            if topic == "homeassistant/status" and isinstance(data, str) and data.lower() == "online":
                logger.info('HA status online received, republishing discovery')
                try:
                    self.publish_discovery()
                except Exception as e:
                    logger.debug(f"Republish discovery failed: {e}")
                return
            self.on_command(topic, data)
        except Exception as e:
            logger.debug(f"MQTT on_message error: {e}")

    # Home Assistant autodiscovery
    def _disc_topic(self, component, object_id):
        return f"{self.discovery_prefix}/{component}/{self.client_id}_{object_id}/config"

    def publish_discovery(self):
        if not self.connected:
            return
        logger.info('Publishing Home Assistant discovery...')
        # 16 dimmers (light with brightness)
        for i in range(16):
            obj = f"dimmer_{i}"
            name = f"KC868 Light {i+1}"
            command_topic = f"{self.base_topic}/dimmer/{i}/set"
            state_topic = f"{self.base_topic}/dimmer/{i}/state"
            payload = {
                "name": name,
                "unique_id": f"{self.client_id}_{obj}",
                "command_topic": command_topic,
                "state_topic": state_topic,
                "schema": "json",
                "brightness": True,
                "brightness_scale": 100,
                "availability_topic": self.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": {"identifiers": [self.client_id], "name": "KC868-AP", "manufacturer": "KC", "model": "KC868-AP"}
            }
            self.publish(self._disc_topic('light', obj), payload, retain=True)
            logger.info(f"Published discovery: light {i} -> {self._disc_topic('light', obj)}")
            self.subscribe(command_topic)
        # 2 relays (switch)
        for i in range(1, 3):
            obj = f"relay_{i}"
            name = f"KC868 Relay {i}"
            command_topic = f"{self.base_topic}/relay/{i}/set"
            state_topic = f"{self.base_topic}/relay/{i}/state"
            payload = {
                "name": name,
                "unique_id": f"{self.client_id}_{obj}",
                "command_topic": command_topic,
                "state_topic": state_topic,
                "payload_on": "ON",
                "payload_off": "OFF",
                "availability_topic": self.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": {"identifiers": [self.client_id], "name": "KC868-AP", "manufacturer": "KC", "model": "KC868-AP"}
            }
            self.publish(self._disc_topic('switch', obj), payload, retain=True)
            logger.info(f"Published discovery: relay {i} -> {self._disc_topic('switch', obj)}")
            self.subscribe(command_topic)
        # 16 inputs (binary_sensor)
        for i in range(1, 17):
            obj = f"input_{i}"
            name = f"KC868 Input X{i:02d}"
            state_topic = f"{self.base_topic}/input/{i}/state"
            payload = {
                "name": name,
                "unique_id": f"{self.client_id}_{obj}",
                "state_topic": state_topic,
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "power",
                "availability_topic": self.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": {"identifiers": [self.client_id], "name": "KC868-AP", "manufacturer": "KC", "model": "KC868-AP"}
            }
            self.publish(self._disc_topic('binary_sensor', obj), payload, retain=True)
            logger.info(f"Published discovery: input X{i:02d} -> {self._disc_topic('binary_sensor', obj)}")

    # State publishers
    def publish_dimmer_state(self, channel_index, percent):
        topic = f"{self.base_topic}/dimmer/{channel_index}/state"
        payload = {"state": "ON" if percent > 0 else "OFF", "brightness": int(percent)}
        self.publish(topic, payload, retain=True)

    def publish_relay_state(self, relay_index, is_on):
        topic = f"{self.base_topic}/relay/{relay_index}/state"
        payload = "ON" if is_on else "OFF"
        self.publish(topic, payload, retain=True)

    def publish_input_state(self, input_index, is_on):
        topic = f"{self.base_topic}/input/{input_index}/state"
        payload = "ON" if is_on else "OFF"
        self.publish(topic, payload, retain=True)


# Global accessor
mqtt_manager = None


def get_mqtt_manager(on_command_callback):
    global mqtt_manager
    if mqtt_manager is None:
        mqtt_manager = MQTTManager(on_command_callback)
    return mqtt_manager


