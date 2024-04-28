import fritzconnection
import logging
import threading
import time
import queue
import re
import json
import copy

class Fritzbox:
    address = '169.254.1.1'
    port = 49000
    username = 'dslf-config'
    password = ""
    services = {}

    _connection = None
    _threads = []
    _queue = queue.Queue()
    _stopEvent = threading.Event()

    def __init__(self, config):
        if (config == None):
            raise "No configuration given."

        # Load Fritz!Box settings
        fritzboxConfig = config.get("fritzbox", None)

        if (fritzboxConfig == None):
                raise "No configuration section for Fritz!Box"

        self.username = fritzboxConfig.get("username", self.username)
        self.password = fritzboxConfig.get("password", self.password)
        self.address = fritzboxConfig.get("address", self.address)
        self.port = fritzboxConfig.get("port", self.port)
        self.defaultPeriod = fritzboxConfig.get("defaultPeriod", 5)

        self._parseServiceConfig(fritzboxConfig.get("services", []))

    def connect(self):
        logging.info("Connecting to Fritz!Box " + self.address + ":" + str(self.port) + " ...")
        self._connection = fritzconnection.FritzConnection(address = self.address, port = self.port, user = self.username, password = self.password)

        fritzboxLoopThread = threading.Thread(target=self._fritzboxLoop, name="fritzboxLoop")
        fritzboxLoopThread.start()
        self._threads.append(fritzboxLoopThread)

    def disconnect(self):
        logging.info("Disconnecting from Fritz!Box ...")
        self._queue.put(None)
        self._stopEvent.set()
        for t in self._threads:
            t.join()

    def getQueue(self):
        return self._queue

    def _parseServiceConfig(self, serviceConfig):
        for serviceRawName, serviceData in serviceConfig.items():
            matches = re.match('^(?P<name>[-_A-Za-z0-9]+)(:\[?(?P<id>[\-0-9,]+)\]?)?$', serviceRawName)
            if not matches:
                logging.error("Invalid service name in config: '%s'" % (serviceRawName))
                continue

            services = []
            if matches['id'] == None:
                services.append({'name': matches['name']})
            else:
                matches2 = re.split(',', matches['id'])
                for match2 in matches2:
                    matches3 = re.match('^(?P<from>[0-9])+-(?P<to>[0-9])+$', match2)
                    if not matches3:
                        # Single number
                        services.append({'name': matches['name'], 'id': int(match2)})
                    else:
                        # Range
                        for i in range(int(matches3['from']), int(matches3['to'])+1):
                            services.append({'name': matches['name'], 'id': i})

            for service in services:
                if 'id' not in service:
                    fullName = service['name']
                else:
                    fullName = '%s:%i' % (service['name'], service['id'])

                self.services.update({fullName: copy.deepcopy(serviceData)})

                if 'id' in service:
                    self.services[fullName]['id'] = service['id']

        for serviceName, serviceData in self.services.items():

            if 'prefix' not in serviceData:
                serviceData['prefix'] = ""

            if (serviceData['prefix'] != "") and (serviceData['prefix'] != '/'):
                serviceData['prefix'] = serviceData['prefix'] + '/'

            for actionName, actionData in serviceData['actions'].items():
                if 'period' not in actionData:
                    actionData['period'] = self.defaultPeriod 

        logging.debug("Service configuration: \n" + json.dumps(self.services, sort_keys=True, indent=4, separators=(',', ': ')))

    def _fritzboxLoop(self):
        logging.debug("Starting Fritz!Box loop ...")

        while not self._stopEvent.is_set():
            for serviceName, serviceData in self.services.items():
                for actionName, actionData in serviceData['actions'].items():
                    try:
                        # Skip if period is not reached yet
                        if (('lastRun' in actionData) and ((time.time() - actionData['lastRun']) < actionData['period'])):
                            continue

                        logging.debug("Querying data for service: %s action %s ..." % (serviceName, actionName))
                        res = self._connection.call_action(serviceName, actionName)
                        for key, value in res.items():
                            # Skip keys not needed
                            if key not in actionData['values']:
                                continue

                            topic = serviceData['prefix']+key
                            if (key in actionData['values']) and ('topic' in actionData['values'][key]):
                                topic = (serviceData['prefix'] + actionData['values'][key]['topic']).format(
                                    id = serviceData['id'] if ('id' in serviceData) else ""
                                    )

                            if ('type' in actionData['values'][key]):
                                if (actionData['values'][key]['type'] == 'int'):
                                    value = int(value)
                                elif (actionData['values'][key]['type'] == 'float'):
                                    value = float(value)
                                elif (actionData['values'][key]['type'] == 'bool'):
                                    value = bool(value)
                                else:
                                    value = str(value)

                            if (('retain' in actionData['values'][key]) and (actionData['values'][key]['retain'] == 'true')):
                                retain = True
                            else:
                                retain = False                         

                            logging.debug('%s/%s/%s to %s: %r' % (serviceName, actionName, key, topic, value))

                            self._queue.put({'topic': topic, 'value': value, 'retain': retain})

                        actionData['lastRun'] = time.time()

                    except fritzconnection.fritzconnection.ServiceError as e:
                        logging.error("ServiceError: %r" % (e))
                        logging.info("Reconnecting to Fritz!Box " + self.address + ":" + str(self.port) + " ...")
                        self._connection = fritzconnection.FritzConnection(address = self.address, port = self.port, user = self.username, password = self.password)

                    except Exception as e:
                        logging.error("Exception: %r" % (e))

            self._stopEvent.wait(1)
