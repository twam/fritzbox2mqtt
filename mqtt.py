import paho.mqtt.client as mqtt
import logging
import threading
import queue

class Mqtt:
    username = ""
    password = ""
    address = "localhost"
    port = 1883
    prefix = ""

    _client = None
    _threads = []
    _queue = None

    def __init__(self, config):
        if (config == None):
            raise "No configuration given."

        # Load MQTT settings
        mqttConfig = config.get("mqtt", None)

        if (mqttConfig == None):
                raise "No configuration section for MQTT"

        self.username = mqttConfig.get("username", "")
        self.password = mqttConfig.get("password", "")
        self.address = mqttConfig.get("address", "localhost")
        self.port = mqttConfig.get("port", 1883)
        self._queue = queue.Queue()
        self.prefix = mqttConfig.get("prefix")

        if (self.prefix == None):
            self.prefix = ""
        if (self.prefix != "") and (self.prefix[-1] != '/'):
            self.prefix = self.prefix+'/'

    def connect(self):
        logging.info("Connecting to MQTT server " + self.address + ":" + str(self.port) + " ...")

        self._client = mqtt.Client()

        if (self.username != "" and self.password != ""):
            self._client.username_pw_set(self.username, self.password)

        self._client.on_message = self._mqtt_on_message
        self._client.on_connect = self._mqtt_on_connect
        self._client.on_disconnect = self._mqtt_on_disconnect
        self._client.on_log = self._mqtt_on_log
        self._client.connect(self.address, self.port, 60)

        mqttLoopThread = threading.Thread(target=self._mqttLoop, name="mqttLoop")
        mqttLoopThread.start()
        self._threads.append(mqttLoopThread)

    def disconnect(self):
        logging.info("Disconnecting from MQTT server ...")
        self._client.disconnect()
        self._queue.put(None)

    def getQueue(self):
        return self._queue

    def subscribe(self, topic):
        logging.info("Subscribing to " + topic + ".")
        self._client.subscribe(topic)

    def publish(self, topic, value, retain):
        fullTopic = self.prefix + topic

        logging.debug("Publishing to '%s': %r" % (fullTopic, value))
        self._client.publish(topic=fullTopic, payload=value, qos=0, retain=retain)

    def _mqttLoop(self):
        logging.debug("Starting MQTT loop ...")
        self._client.loop_forever()

    def _mqtt_on_connect(self, client, userdata, flags, rc):
        logging.info("Connected to MQTT server " + self.address + ":" + str(self.port) + ".")

    def _mqtt_on_disconnect(self, client, userdata, rc):
        logging.info("Disconnected from MQTT server.")

    def _mqtt_on_message(self, client, userdata, msg):
        logging.debug("Message: "+msg.topic +" "+msg.payload.decode('utf-8'))
        self._queue.put(msg)

    def _mqtt_on_log(self, client, userdata, level, buf):
        if (level == mqtt.MQTT_LOG_ERR):
            logging.error("MQTT: " + buf)
        elif (level == mqtt.MQTT_LOG_WARNING):
            logging.warning("MQTT: " + buf)
        elif ((level == mqtt.MQTT_LOG_INFO) or (level == mqtt.MQTT_LOG_NOTICE)):
            logging.info("MQTT: " + buf)
        else:
            logging.debug("MQTT: " + buf)
