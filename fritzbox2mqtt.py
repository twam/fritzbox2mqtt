#!/usr/bin/python

import logging
import sys
import daemon
import time
import argparse
import yaml
import threading

import mqtt
import fritzbox

def main(argv=None):
    if argv is None:
        argv = sys.argv

    args = parseArgs(argv)

    if (args.daemon):
        context = daemon.DaemonContext()

        with context:
            run(args)
    else:
        run(args)

def parseArgs(argv):
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True
        )

    parser.add_argument("-c", "--conf_file",
                        help="Specify config file", metavar="FILE", required = True)

    parser.add_argument("-d", "--daemon",
                        help="Run as daemon", action='store_true')

    parser.add_argument("-v", "--verbose",
                        help="Increases log verbosity for each occurence", dest="verbose_count", action="count", default=0)
                            
    args = parser.parse_args()

    return args

def parseConfig(filename):
    try:
        return yaml.load(open(filename, "r"))
    except Exception as e:
        raise
        logging.error("Can't load yaml file %r (%r)" % (filename, e))

def processFritzboxMessages(mqtt, fritzbox, stopEvent):
    while not stopEvent.is_set():
        try:
            msg = fritzbox.getQueue().get()
            if msg is None:
                continue

            logging.debug("Fritzbox message: topic=%s value=%r" % (msg['topic'], msg['value']))

            try:
                mqtt.publish(topic = msg['topic'], value = msg['value'], retain = msg['retain'])
            except Exception as e:
                logging.error('Could not push to MQTT:' + str(e))

            fritzbox.getQueue().task_done()
        except Exception as e:
            logging.error('Error while sending from Fritz!Box to MQTT: ' + str(e))

    logging.debug("Stopping MQTT message thread ...")

def run(args):
    logging.basicConfig(format="%(asctime)s [%(threadName)-15s] %(levelname)-6s %(message)s",
                        #filename=os.path.join('./', "app.out"),
                        level=max(3 - args.verbose_count, 0) * 10)

    try:
        config = parseConfig(args.conf_file)
    except Exception as e:
        logging.error("Failure while reading configuration file '%s': %r" % (args.conf_file, e))
        return

    m = mqtt.Mqtt(config)
    m.connect()

    f = fritzbox.Fritzbox(config)
    f.connect()

    stopEvent = threading.Event()

    t = threading.Thread(target=processFritzboxMessages, args=[m, f, stopEvent], name="processFritzboxMessages")
    t.daemon = True
    t.start()

    try:
        while True:
            stopEvent.wait(60)

    except (SystemExit,KeyboardInterrupt):
        # Normal exit getting a signal from the parent process
        pass
    except:
        # Something unexpected happened?
        logging.exception("Exception")
    finally:
        logging.info("Shutting down ...")

        stopEvent.set()

        t.join()
        f.disconnect()
        m.disconnect()

        logging.shutdown()

if __name__ == "__main__":
    main()
