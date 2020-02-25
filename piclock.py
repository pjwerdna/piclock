#!/usr/bin/python

# Main Entry point
# Starts all other threads
#
# Version 2.7

import logging
import logging.handlers
import sys
import argparse
import shutil
from oauth2client import tools
import pytz
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
parser.add_argument('--log', help='log help')
parser.add_argument('--nolancheck', action="store_true", help='nolancheck help')
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


# Start support daemon
pigpiostate = os.popen('ps -ef|grep pigpiod').read()
if (pigpiostate.find("/usr/bin/pigpiod") == -1):
    print "starting pigpio"
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
import MenuControl
import MediaPlayer
#import AlarmGatherer
import AlarmThread
from Web import WebApplication
from Web import WebApplicationHTTP
from Weather import WeatherFetcher
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
         alarmTime = datetime.datetime.fromtimestamp(manual, pytz.timezone('Europe/London'))
         log.info("Loaded previously set manual alarm time of %s",alarmTime)
         self.alarm.manualSetAlarm(alarmTime)


   def execute(self):
      #~ global lancheck
      global iplist
      log.info("Starting up AlarmPi")
      log.info("cwd=%s", os.getcwd())

      iplist = []
      NetworksIP = self.GetIPForNetwork("eth0")
      if (NetworksIP != ""):
        log.info("Have LAN Connection %s" , NetworksIP)
        iplist.append(NetworksIP)

      self.GetIPForNetwork("wlan0")
      if (NetworksIP != ""):
        log.info("Have Wifi Connection %s" , NetworksIP)
        iplist.append(NetworksIP)
        # have lan and wifi
        #~ if (nolancheck == False):
            #~ log.info("add '--nolancheck' to the command line to run with two networks connected")
            #~ sys.exit()

      log.info("Loading settings")
      self.settings = Settings.Settings()
      self.settings.setup()

      log.info("Loading brightness control")
      self.bright = brightnessthread.BrightnessThread(self.settings)
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
      media = MediaPlayer.MediaPlayer()
      #media.playVoice('Starting up')

      log.info("Loading alarm control")
      self.alarm = AlarmThread.AlarmThread(weather, media, self.settings)
      self.alarm.setDaemon(True)


      log.info("Starting TFT")
      #self.lcd = tftthread.TFTThread(alarm, self,  media, weather)
      # tel lcd thread what we didnt know when we loaded it
      self.lcd.SetConfig(self.alarm, media, weather, self.bright)
      #self.lcd.setDaemon(True)
      # and start lcdthread
      self.lcd.start()

      #~ log.debug("Loading clock")
      #~ self.clock = clockthread.ClockThread(self.lcd, self.settings, self.alarm)
      #~ self.clock.setDaemon(True)

      #~ log.debug("Starting clock")
      #~ self.clock.start()

      self.Menus = self.lcd.menu

      #~ log.debug("Loading Menus")
      #~ self.Menus = MenuControl.MenuControl(self.lcd, clock, media, self, weather)
      #~ self.Menus.setDaemon(True)

      log.info("Starting alarm control")
      self.alarm.start()

      log.info("Starting HTTP web application")
      webhttp = WebApplicationHTTP(self.alarm, self.settings, media, self, self.bright, self.lcd)
      webhttp.setDaemon(True)
      webhttp.start()

      log.info("Starting HTTPS web application")
      web = WebApplication(self.alarm, self.settings, media, self, self.bright)
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

         while(self.stopping == False):
            time.sleep(10) #0.1)



      except (KeyboardInterrupt, SystemExit):
         log.warn("Interrupted, shutting down")

      self.pauseclock  (True)


      if self.rebootAction == 2: #self.shutdownnow == True:
        self.lcd.setMessage("Shutting Down",True)
        media.playSpeech('Shutting down.')
        log.warn("Shutting down")
      elif self.rebootAction == 1: #self.rebootnow == True:
        self.lcd.setMessage("Rebooting now",True)
        # Lets do it quietly
        #~ media.playSpeech('Rebooting now.')
        log.warn("Rebooting now")
      else:
        self.lcd.setMessage("Stopping now",True)
        media.playSpeech('Stopping now.')
        log.warn("Stopping now")

      #~ time.sleep(1)

      log.info("Stopping all services")
      web.stop()
      webhttp.stop()
      # alarm.stop()
      self.lcd.stop()
      self.bright.stop()
      media.stopPlayer()
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


