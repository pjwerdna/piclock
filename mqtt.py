# See
# https://www.eclipse.org/paho/clients/python/docs/
#
import threading
import logging

import paho.mqtt.client as mqtt
import datetime
import time
import sys
import os

log = logging.getLogger('root')

# MQTT values are as follows
# piclock_out
#   alarm/date              - date of next alarm at
#   alarm/time              - time of next alarm at
#   alarm/datetime          - date and time of next alarm at
#   alarm/remaining         - minutes of alarm remaining
#   alarm/stationname       - name of next radio station to play
#   alarm/stationno         - number of next radio station to play
#   alarm/volume            - volume to play next alarm at
#
#   alarms/0/stationno      - station no for alarm 0
#   alarms/0/time           - time for alarm 0
#   alarms/0/volume         - volume for alarm 0
#   alarms/x/stationno      - station no for alarm x
#   alarms/x/time           - time for alarm x
#   alarms/x/volume         - volume for alarm x
#
#   radio/state             - ON or Off. State of the radio
#   radio/station           - Name of currently playing radio station
#   radio/stationno         - Currently playing station number
#   radio/volumepercent     - current volume as a percentage
#
#   stations/station_list   - Comma separated list if all station names
#   stations/station_name_0 - Name of station 0
#   stations/station_url_0  - URL of station 0
#   stations/station_name_x - Name of station x
#   stations/station_url_x  - URL of station x
#
# piclock_in
#   radio/volumepercent     - sets currently play volume
#   radio/state             - ON or Off to turn on or off
#   radio/stationno         - New station number to play 


class MQTTThread(threading.Thread):

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self,client, userdata, flags, rc):
        log.debug("mqtt connected with result code "+str(rc))

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        self.client.subscribe("piclock_in/#")

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self,client, userdata, msg):
    #    if msg.topic.find("/255/") == -1:
        log.debug("mqtt " + msg.topic + " = " + msg.payload)
        if str(msg.topic)[0:11] == "piclock_in/":
            insetting = str(msg.topic)[11:]
            log.info("topic='%s', payload='%s'", insetting, msg.payload)

            done = False
            if (self.radio != None):
                done = self.radio.on_message(insetting,msg.payload)
            if (self.alarm != None) and (done == False):
                done = self.alarm.on_message(insetting,msg.payload)
            if (self.settings != None) and (done == False):
                done = self.settings.on_message(insetting,msg.payload)
            if (self.display != None) and (done == False):
                done = self.display.on_message(insetting,msg.payload)

    def set_radio(self,newradio):
        self.radio = newradio

    def set_alarm(self,newalarm):
        self.alarm = newalarm

    def set_display(self,display):
        self.display = display

    def __init__(self,settings):
        threading.Thread.__init__(self)

        #self.volume = volume
        self.settings = settings
        self.SleepTime = 0.1
        self.stopping = False
        self.radio = None
        self.alarm = None
        self.display = None

        self.mqttbroker = self.settings.getorset("mqttbroker","")
        if (self.mqttbroker != ""):
            self.client = mqtt.Client(client_id="piclock", clean_session=False)
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.username_pw_set(username=settings.get('mqttbrokeruser'), password=settings.get('mqttbrokerpass'))

            self.client.connect(self.mqttbroker, 1883, 60)
        else:
            self.client = None

        #client.publish("mysensors-in/3/1/0/0/2", payload=self.settings.getInt("volume"), qos=0, retain=False)

    def stop(self):
      self.stopping=True

    def publish(self,itemname, itemvalue):
        if (self.client != None):
            self.client.publish("piclock_out/" + itemname, payload=itemvalue, qos=0, retain=True)


    def run(self):
        if (self.radio != None):
            self.radio.publish()

        # publish daily Alarm info
        if (self.alarm != None):
            self.alarm.publish()

        if (self.settings != None):
            self.settings.publish()

        # Blocking call that processes network traffic, dispatches callbacks and
        # handles reconnecting.
        # Other loop*() functions are available that give a threaded interface and a
        # manual interface.
        if (self.client != None):
            self.client.loop_forever()

        # self.menu.start()
        while(not self.stopping):
            time.sleep(self.SleepTime)
            #self.client.loop()

