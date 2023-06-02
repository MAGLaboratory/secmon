#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import traceback, os, logging, time, atexit
from dataclasses import dataclass
from dataclasses_json import dataclass_json
from enum import Enum
from typing import * 
from confirmation_threshold import confirmation_threshold
from threading import Event
from Xlib import display
from Xlib.ext import dpms

class SECMON(mqtt.Client):

  version = '2023'
  @dataclass_json
  @dataclass
  class config:
    name: str
    description: str
    mqtt_broker: str
    mqtt_port: int
    mqtt_timeout: int
    loglevel: Optional[str] = None


  # overloaded MQTT functions from (mqtt.Client)
  def on_log(self, client, userdata, level, buff):
    if level == mqtt.MQTT_LOG_DEBUG:
      logging.debug("PAHO MQTT DEBUG: " + buff)
    elif level == mqtt.MQTT_LOG_INFO:
      logging.info("PAHO MQTT INFO: " + buff)
    elif level == mqtt.MQTT_LOG_NOTICE:
      logging.info("PAHO MQTT NOTICE: " + buff)
    elif level == mqtt.MQTT_LOG_WARNING:
      logging.warning("PAHO MQTT WARN: " + buff)
    else:
      logging.error("PAHO MQTT ERROR: " + buff)

  def on_connect(self, client, userdata, flags, rc):
    logging.info("Connected: " + str(rc))
    self.subscribe("reporter/checkup_req")
    self.subscribe(self.config.name + "/CMD_DisplayOn")

  def on_message(self, client, userdata, message):
    if (message.topic == "reporter/checkup_req"):
      logging.info("Checkup received.")
      self.checkup()
    elif (message.topic == self.config.name + "/CMD_DisplayOn"):
      decoded = message.payload.decode('utf-8')
      logging.info("Display Commanded: " + decoded)
      if (decoded.lower() == "false" or decoded == "0"):
        self.disp.dpms_force_level(dpms.DPMSModeOff)
        self.disp.sync()
      elif (decoded.lower() == "true" or decoded == "1"):
        self.disp.dpms_force_level(dpms.DPMSModeOn)
        self.disp.sync()

  def on_disconnect(self, client, userdata, rc):
    logging.warning("Disconnected: " + str(rc))
    if rc != 0:
        logging.error("Unexpected disconnection.  Attempting reconnection.")
        reconnect_count = 0
        while (reconnect_count < 10):
            try:
                reconnect_count += 1
                self.reconnect()
                break
            except OSError:
                logging.error("Connection error while trying to reconnect.")
                logging.error(traceback.format_exc())
                logging.error("Waiting to restart.")
                self.tEvent.wait(30)
        if reconnect_count >= 10:
            logging.critical("Too many reconnect tries.  Exiting.")
            os._exit(1)

  # Security monitor functions
  def checkup():
    # idk, lol.
    return

  def run(self):
    self.tEvent = Event()
    self.running = True
    startup_count = 0
    self.io_check_count = 0
    self.loop_count = 0
    # logging
    try:
      if type(logging.getLevelName(self.config.loglevel.upper())) is int:
        logging.basicConfig(level=self.config.loglevel.upper())
      else:
        logging.warning("Log level not configured.  Defaulting to WARNING.")
    except (KeyError, AttributeError) as e:
      logging.warning("Log level not configured.  Defaulting to WARNING.  Caught: " + str(e))

    # X display
    self.disp = display.Display()
    capable = self.disp.dpms_capable()
    assert capable, "DPMS is not supported!"

    self.disp.dpms_enable()
    self.disp.sync()

    while startup_count < 10:
      try:
        startup_count += 1
        # check loglevel
        self.connect(self.config.mqtt_broker, self.config.mqtt_port, self.config.mqtt_timeout)
        atexit.register(self.disconnect)
        break
      except OSError:
        if startup_count >= 10:
            logging.critical("Too many startup tries.  Exiting.")
            os._exit(1)
        logging.error("Error connecting on bootup.")
        logging.error(traceback.format_exc())
        logging.error("Waiting to reconnect...")
        self.tEvent.wait(30)
        

    logging.info("Startup success.")
    self.reconnect_me = False
    self.inner_reconnect_try = 0
    while self.running and (self.inner_reconnect_try < 10):
      if self.loop_count >= 65535:
        self.loop_count = 0
      else:
        self.loop_count += 1
      try:
        if self.reconnect_me == True:
          self.reconnect()
          self.reconnect_me = False
        
        self.loop()
        self.inner_reconnect_try = 0
      except SystemExit:
        break
      except (socket.timeout, TimeoutError, ConnectionError):
        self.inner_reconnect_try += 1
        self.reconnect_me = True
        logging.error("MQTT loop error.  Attempting to reconnect: " + inner_reconnect_try + "/10")
      except:
        logging.critical("Exception in MQTT loop.")
        logging.critical(traceback.format_exc())
        logging.critical("Exiting.")
        exit(2)
    if self.inner_reconnect_try >= 10:
      exit(1)
    exit(0)

if __name__ == "__main__":
    secmon = SECMON()
    my_path = os.path.dirname(os.path.abspath(__file__))
    with open(my_path + "/secmon_config.json", "r") as configFile:
        secmon.config = SECMON.config.from_json(configFile.read())
    secmon.run()
