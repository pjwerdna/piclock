#!/usr/bin/python

# Main Entry point
# Starts all other threads
#
# Version 2.9
# 26/01/2021 - Media player is now a thread and will montiroe itself (used to be in AlarmThread!)
# 08/05/2021 - Added mqtt broker 
# 12/07/2021 - Added stdout & stderror redirection. This removes the need for piclockweb.log
#              Changed to piclockerror.log instead as only errors should end up there
# 07/10/2021 - fixed mqtt calls

import logging
import logging.handlers
import sys
import argparse
import shutil
#from http.server import BaseHTTPRequestHandler, HTTPServer
from oauth2client import tools
#import pytz
import os
import time
import datetime
from subprocess import Popen

# IP Adddresses we are listening on
iplist = []

userid = os.getuid()
if userid != 0:
    print("Please run script as root")
    sys.exit()

# Decode arguments
parser = argparse.ArgumentParser(parents=[tools.argparser])
parser.add_argument('--log', help='Log Level', choices=["DEBUG","INFO","WARNING","ERROR","CRITICAL"])
parser.add_argument('--nolancheck', action="store_true", help='Dont check for a network before starting')
args = parser.parse_args()
loglevel = args.log
nolancheck = args.nolancheck
authflags = args

LOGFILENAME="piclock.log"

log = logging.getLogger('root')
log.setLevel(logging.DEBUG)

log_format = '[%(asctime)s] %(levelname)8s %(module)15s: %(message)s'

if (loglevel != None):
    # specify --log=DEBUG or --log=debug
    numeric_level = getattr(logging, loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % loglevel)
    # set level, format and output to file (FYI Now use rotatingfilehandler)
    #~ shutil.copy2("piclock.log","piclock-old.log")
    #~ logging.basicConfig(level=numeric_level, filename=LOGFILENAME, format=log_format)

    loghandler = logging.handlers.RotatingFileHandler(LOGFILENAME,maxBytes=100000,backupCount=5)
    loghandler.setFormatter(logging.Formatter(log_format))

    log.addHandler(loghandler)
    log.setLevel(numeric_level)

else: # Default output to caller
    stream = logging.StreamHandler(sys.stdout)
    stream.setLevel(logging.DEBUG)

    stream.setFormatter(logging.Formatter(log_format))

    log.addHandler(stream)

# Added stdout & stderror redirection
# From Solution 4 in https://stackoverflow.com/questions/19425736/how-to-redirect-stdout-and-stderr-to-logger-in-python/51612402
class LoggerWriter:
    def __init__(self, logfct):
        self.logfct = logfct
        self.buf = []

    def write(self, msg):
        if msg.endswith('\n'):
            self.buf.append(msg[:-1])
            self.logfct(''.join(self.buf))
            self.buf = []
        else:
            self.buf.append(msg)

    def flush(self):
        pass
#
# To access the original stdout/stderr, use sys.__stdout__/sys.__stderr__
sys.stdout = LoggerWriter(log.debug)
sys.stderr = LoggerWriter(log.info)

# Start support daemon
pigpiostate = os.popen('ps -ef|grep pigpiod').read()
if (pigpiostate.find("/usr/bin/pigpiod") == -1):
    print ("starting pigpio")
    pid = Popen(["/usr/bin/pigpiod", "-l"]).pid
    time.sleep(3)

import pygame
from pygame.locals import *
#import pytz
import threading
import signal

import Settings
#~ import clockthread
import tftthread
import brightnessthread
import MediaPlayer
#import AlarmGatherer
import AlarmThread
#import WebServer    # doesnt work!
from Web import WebApplication
from Web import WebApplicationHTTP
from Weather import WeatherFetcher
import mqtt
import subprocess

import colours

class AlarmPi:
   def __init__(self):
      self.stopping = False
      self.rebootnow = False
      self.shutdownnow = False
      self.rebootAction = -1


   def stop(self, doreboot = 0):
      self.stopping = True
      self.alarm.stopping = True
      self.Menus.ExitAllMenus = True

      self.rebootAction = doreboot
      if (doreboot == 1): # reboot
          self.rebootnow = True
          self.lcd.setMessage("Rebooting",True)
          #~ print "Rebooting"
          self.settings.set("quiet_reboot","1")

      elif (doreboot == 2) or (doreboot == True): # Shutdown
          self.shutdownnow = True
          self.lcd.setMessage("Shutting Down",True)
          #~ print "Shutting down"
          self.settings.set("quiet_reboot","0")

      elif (doreboot == 3): # restart app
          self.lcd.setMessage("Restarting Clock",True)
          self.settings.set("quiet_reboot","1")
          subprocess.Popen('/etc/init.d/piclock restart', shell=True)



   def GetIPForNetwork(self, Network): # find the IP of the given network
        ipv4 = os.popen('ip addr show ' + Network).read()
        ipv4lines = ipv4.split(chr(10))

        for ipline in ipv4lines:
            if ipline.find("inet ") > 0:
                ipinfo = ipline.strip().split(" ")
                ipaddress = ipinfo[1]

                return ipaddress.split("/")[0]

        return ""


   def setBrightness(self, level):
        self.bright.setBrightness(level)

   def XsetBrightnessTweak(self, level):
       if level > 98:
           level = 98
       elif level < 0:
           level = 0
       self.bright.BrightnessTweak = level
       self.settings.set('brightness_tweak',level)

   def XgetBrightnessTweak(self):
       return self.bright.BrightnessTweak

   def pauseclock(self, ClockState):
       #~ self.clock.paused(ClockState)
       self.lcd.paused(ClockState)

   def clockMessage(self, NewMessage):
       #~ self.clock.SetExtraMessage(NewMessage)
       self.lcd.SetExtraMessage(NewMessage)

   def AutoSetAlarm(self): # If there's a manual alarm time set in the database, then load it or an automatic one

      manual = self.settings.getInt('manual_alarm')
      if manual==0 or manual is None:
         self.alarm.autoSetAlarm()
      else:
         alarmTime = datetime.datetime.fromtimestamp(manual) # , pytz.timezone('Europe/London')
         log.info("Loaded previously set manual alarm time of %s",alarmTime)
         self.alarm.manualSetAlarm(alarmTime)


   def execute(self):
      #~ global lancheck
      global iplist
      log.info("Starting up PiClock")
      #log.info("cwd=%s", os.getcwd())

      iplist = []
      NetworksIP = self.GetIPForNetwork("eth0")
      if (NetworksIP != ""):
        log.debug("Have LAN Connection %s" , NetworksIP)
        iplist.append(NetworksIP)

      self.GetIPForNetwork("wlan0")
      if (NetworksIP != ""):
        log.debug("Have Wifi Connection %s" , NetworksIP)
        iplist.append(NetworksIP)
        # have lan and wifi
        #~ if (nolancheck == False):
            #~ log.info("add '--nolancheck' to the command line to run with two networks connected")
            #~ sys.exit()

      log.info("Loading settings")
      self.settings = Settings.Settings()
      self.settings.setup()

      # Set Log level from settings
      log.setLevel(self.settings.getInt('DEBUGLEVEL'))

      log.info("Starting mqtt application")
      self.mqttbroker = mqtt.MQTTThread(self.settings)
      self.mqttbroker.setDaemon(True)
      self.mqttbroker.start()
      self.settings.setmqttbroker(self.mqttbroker)

      log.info("Loading brightness control")
      self.bright = brightnessthread.BrightnessThread(self.settings, self.mqttbroker)
      self.bright.setDaemon(True)
      # bright.registerControlObject(clock.segment.disp)
      # bright.registerControlObject(self.lcd)
      self.bright.start()

      log.info("Loading TFT") # its started later
      self.lcd = tftthread.TFTThread(self, self.settings)
      self.lcd.setDaemon(True)

      log.info("Loading weather")
      weather = WeatherFetcher()

      log.info("Loading media")
      self.media = MediaPlayer.MediaPlayer(self.mqttbroker, self.settings)
      self.media.setDaemon(True)
      self.media.start()

      log.info("Loading alarm control")
      self.alarm = AlarmThread.AlarmThread(weather, self.media, self.settings, self.mqttbroker)
      self.alarm.setDaemon(True)

      log.info("Starting TFT")
      #self.lcd = tftthread.TFTThread(alarm, self,  self.media, weather)
      # tel lcd thread what we didnt know when we loaded it
      self.lcd.SetConfig(self.alarm, self.media, weather, self.bright, self.mqttbroker)
      #self.lcd.setDaemon(True)
      # and start lcdthread
      self.lcd.start()
      
      # new trial of webserver class
      #self.webserver = WebServer.WebServer(self.mqttbroker, self.alarm, self.media, self.bright, self.lcd, self.settings)
      # which failed

      # Tell mqtt broker about things setup after it was
      #self.mqttbroker.set_radio(self.media)  
      #self.mqttbroker.set_alarm(self.alarm)  
      #self.mqttbroker.set_display(self.lcd) 

      self.Menus = self.lcd.menu

      #~ this is done in the tftthread where its required

      log.info("Starting alarm control")
      self.alarm.start()

      # Start webserver thread
      #self.webserver.setDaemon(True)
      #self.webserver.start() # fails

      log.info("Starting HTTP web application")
      webhttp = WebApplicationHTTP(self.alarm, self.settings, self.media, self, self.bright, self.lcd, self.mqttbroker)
      webhttp.setDaemon(True)
      webhttp.start()

      log.info("Starting HTTPS web application")
      web = WebApplication(self.alarm, self.settings, self.media, self, self.bright, self.mqttbroker)
      web.setDaemon(True)
      web.start()

      loopcount = 0
      self.clockMessage(self.alarm.getMenuLine())

      # Main loop where we just spin until we receive a shutdown request
      try:
         lastpos = (-1,-1)
         dragstart = -1
         newvolume = -1
         oldvolume = -1
         log.info("Running")

         # If we crash or have power loss restart quietly
         self.settings.set("quiet_reboot","1")
         lastclocktemp = 0

         while(self.stopping == False):
            time.sleep(5) #0.1)
            clocktemp = int(open('/sys/class/thermal/thermal_zone0/temp').read()) / 1e3
            if clocktemp != lastclocktemp:
                self.mqttbroker.publish("Temperature",str(clocktemp))
                lastclocktemp = clocktemp


      except (KeyboardInterrupt, SystemExit):
         log.warn("Interrupted, shutting down")

      self.pauseclock  (True)


      if self.rebootAction == 2: #self.shutdownnow == True:
        self.lcd.setMessage("Shutting Down",True)
        self.media.playSpeech('Shutting down.')
        log.warn("Shutting down")
      elif self.rebootAction == 1: #self.rebootnow == True:
        self.lcd.setMessage("Rebooting now",True)
        # Lets do it quietly
        #~ self.media.playSpeech('Rebooting now.')
        log.warn("Rebooting now")
      else:
        self.lcd.setMessage("Stopping now",True)
        self.media.playSpeech('Stopping now.')
        log.warn("Stopping now")

      #~ time.sleep(1)

      log.info("Stopping all services")
      #self.webserver.stop()
      web.stop()
      webhttp.stop()
      
      self.lcd.stop()
      self.bright.stop()
      self.media.stopPlayer()
      if self.Menus.isActive():
          self.Menus.exitMenu()

      log.info("Shutdown complete, now exiting")

      time.sleep(2) # To give threads time to shut down

      if self.rebootnow == True:
          subprocess.Popen("sudo /sbin/reboot now", stdout=subprocess.PIPE, shell=True)
      elif self.shutdownnow == True:
          subprocess.Popen("sudo /sbin/shutdown now", stdout=subprocess.PIPE, shell=True)


      #~ pygame.display.quit()
      #~ pygame.quit()

def signal_handler(signal, frame):
   log.info("ctrl+C pressed")
   pialarm.settings.set("quiet_reboot","1")
   pialarm.stop()

signal.signal(signal.SIGINT, signal_handler)

pialarm = AlarmPi()
pialarm.execute()


