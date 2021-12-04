# Plays radio stations and alarms
#
# Normally a radio station, but a default mp3 if the station fails to start


# 18/10/220 - Added restartPlayer so AlarmThread can do easy restarts
# 26/01/2021 - Moved player monitoring to player Thread
# 08/05/2021 - Fixed minor syntax errors. Added mqtt broker
# 10/08/2021 - Moved player monitoring to mediaplayer thread so it works when not playing an alarm 
# 12/09/2021 - Only changes playing station if it a differant URL
# 22/11/2021 - Fixed alarm restart when player sticks
# 23/11/2021 - Move Volume increase for alarms to MediaPlayer.py
# 26/11/2021 - Fixed restart of player re triggering the current alarm

import time
from mplayer import Player
#import Settings
import subprocess
import logging
import threading

# for mplayer testing
import sys
# end of testing bits

# mplayer info
# https://github.com/baudm/mplayer.py
# https://www.mplayerhq.hu/DOCS/tech/slave.txt

log = logging.getLogger('root')

PANIC_ALARM = '/home/pi/Music/BrightSideOfLife.mp3'
PANIC_ALARM = '/home/pi/Music/always look on the bright side.mp3'
FX_DIRECTORY = '/root/sounds/'

class MediaPlayer(threading.Thread):

   def __init__(self, mqttbroker, settings):
      threading.Thread.__init__(self)
      self.settings = settings 
      self.player = False
      self.effect = False
      self.CurrentStation = ""
      self.CurrentStationNo = -1
      self.CurrentURL = ""
      self.stopping = False
      self.message = ""
      self.mqttbroker = mqttbroker
      self.increasingvolume = -1
      self.alarmThread = None
      self.playerrestarting = False

   def playerActive(self):
      # True if playing or mid restart
      return self.player!=False or self.playerrestarting

   def playerPaused(self):
      if self.player:
         return self.player.paused
      else:
         return True # not running actually!

   def playerActiveStation(self):
      if self.player:
          return self.CurrentStation
      else:
          return "None"

   def playerActiveStationNo(self):
      if self.player:
          return self.CurrentStationNo
      else:
          return -1

   def soundAlarm(self, alarmThread, Station = -1, StartVolume = -1):
      # STation = Station Number
      # StartVolume = Increasing volume from this level
      log.info("Playing alarm")
      self.alarmThread = alarmThread
      self.increasingvolume = StartVolume
      if (StartVolume != -1):
         self.settings.setVolume(StartVolume)
      self.playStation(Station)
      log.debug("Alarm process opened")

      # Wait a few seconds and see if the mplayer instance is still running
      time.sleep(self.settings.getInt('radio_delay'))

      if alarmThread.isSnoozing() or alarmThread.getNextAlarm() is None:
         # We've snoozed or cancelled the alarm, so no need to check for player
         log.debug("Media player senses alarm already cancelled/snoozed, so not checking for mplayer instance")
         return

      # Fetch the number of mplayer processes running
      processes = subprocess.Popen('ps aux | grep mplayer | egrep -v "grep" | wc -l',
         stdout=subprocess.PIPE,
         shell=True
      )
      num = int(processes.stdout.read())

      if num < 2 and self.player is not False:
         log.error("Could not find mplayer instance, playing panic alarm")
         self.stopPlayer()
         time.sleep(2)
         self.playMedia(PANIC_ALARM,0)


   def playStation(self,station=-1):
      if station==-1:
         station = self.settings.getInt('station')

      try:
         stationinfo = self.settings.getStationInfo(station)
      except:
         log.debug("invalid station no '%s'", str(station))
         stationinfo = None

      if (stationinfo != None):
         # Only change if its differant URL
         if (self.CurrentURL != stationinfo['url']):
            log.info("Playing station %s", stationinfo['name'])
            log.debug("Playing URL %s", stationinfo['url'])
            self.player = Player() # did have "-cache 2048"
            self.player.loadlist(stationinfo['url'])
            self.player.loop = 0
            self.CurrentStation = stationinfo['name']
            self.CurrentStationNo = station
            self.CurrentURL = stationinfo['url']
         else:
            log.info("Already Playing %s", stationinfo['name'])

         if (self.mqttbroker != None):
            self.mqttbroker.publish("radio/station",self.CurrentStation)
            self.mqttbroker.publish("radio/stationno",str(self.CurrentStationNo))
            self.mqttbroker.publish("radio/state","ON")
            self.mqttbroker.publish("radio/mute","OFF")

   def playStationURL(self,stationName, StationURL, StationNo = -1):

      log.info("Playing station %s", stationName)
      log.debug("Playing URL %s", StationURL)
      self.player = Player("-cache 320") # did have "-cache 2048"
      self.player.loadlist(StationURL)
      self.player.loop = 0
      self.CurrentStation = stationName
      self.CurrentStationNo = StationNo
      self.CurrentURL = StationURL
      if (self.mqttbroker != None):
         self.mqttbroker.publish("radio/station",self.CurrentStation)
         self.mqttbroker.publish("radio/stationno",str(StationNo))
         self.mqttbroker.publish("radio/state","ON")
         self.mqttbroker.publish("radio/mute","OFF")

   def playMedia(self,file,loop=-1):
      log.info("Playing file %s", file)
      self.player = Player()
      self.player.loadfile(file)
      self.player.loop = loop
      self.CurrentStation = file
      self.CurrentStationNo = -1
      self.CurrentURL = file
      if (self.mqttbroker != None):
         self.mqttbroker.publish("radio/station",self.CurrentStation)
         self.mqttbroker.publish("radio/stationno",str(self.CurrentStationNo))
         self.mqttbroker.publish("radio/state","ON")      
         self.mqttbroker.publish("radio/mute","OFF")

   # Play some speech. None-blocking equivalent of playSpeech, which also pays attention to sfx_enabled setting
   def playVoice(self,text):
      if (self.settings.get('sfx_enabled')==0) or (self.settings.getIntOrSet('quiet_reboot') == 1):
         # We've got sound effects disabled, so skip
         log.info("Sound effects disabled, not playing voice")
         return
      path = self.settings.get("tts_path");
      log.info("Playing voice: '%s' through `%s`" % (text,path))
      if path == "pico2wave":
        play = subprocess.Popen('pico2wave -l en-GB -w /tmp/texttosay.wav "%s" && aplay -q /tmp/texttosay.wav' % (text), shell=True)
      else:
        play = subprocess.Popen('echo "%s" | %s 2>/dev/null' % (text,path), shell=True)

   # Play some speech. Warning: Blocks until we're done speaking
   def playSpeech(self,text):
      if (self.settings.get('sfx_enabled')==0) or (self.settings.getIntOrSet('quiet_reboot') == 1):
         # We've got sound effects disabled, so skip
         log.info("Sound effects disabled, not playing voice")
         return
      path = self.settings.get("tts_path");
      log.info("Playing speech: '%s' through `%s`" % (text,path))
      if path == "pico2wave":
          play = subprocess.Popen('pico2wave -l en-GB -w /tmp/texttosay.wav "%s" && aplay -q /tmp/texttosay.wav' % (text), shell=True)
      else:
        play = subprocess.Popen('echo "%s" | %s  2>/dev/null' % (text,path), shell=True)

      play.wait()

   def stopPlayer(self):
      if self.player:
         self.player.quit()
         self.player = False
         self.CurrentURL = ""
         self.CurrentStationNo = -1
         self.CurrentStation = "N/A"
         log.info("Player process terminated")
         if (self.mqttbroker != None):
            self.mqttbroker.publish("radio/station",self.CurrentStation)
            self.mqttbroker.publish("radio/stationno",str(self.CurrentStationNo))
            self.mqttbroker.publish("radio/state","OFF")
            self.mqttbroker.publish("radio/mute","OFF")

   def pausePlayer(self):
      if self.player:
         self.player.pause()
         log.info("Player process paused/unpaused")
         if (self.mqttbroker != None):
            self.mqttbroker.publish("radio/state","ON")
            self.mqttbroker.publish("radio/mute","ON")
         return self.player.paused
      else:
         return True # not running actually!

   def restartPlayer(self):
      self.playerrestarting = True
      CurrentURL = self.CurrentURL
      CurrentStation = self.CurrentStation
      CurrentStationNo = self.CurrentStationNo
      log.info("Player Restarting")
      self.stopPlayer()
      time.sleep(2)
      self.playerrestarting = False
      self.playStationURL(CurrentStation, CurrentURL, CurrentStationNo)

   def publish(self):
        self.mqttbroker.publish("radio/volumepercent", self.settings.getInt("volumepercent"))
        self.mqttbroker.publish("radio/station",self.CurrentStation)
        self.mqttbroker.publish("radio/stationno",str(self.CurrentStationNo))
        if self.player:
            self.mqttbroker.publish("radio/state","ON")  
        else:
            self.mqttbroker.publish("radio/state","OFF")  

   def on_message(self, topic ,payload):
      method = topic[0:topic.find("/")] # before first "/"
      item = topic[topic.rfind("/")+1:]   # after last "/"
      log.debug("radio method='%s', item='%s'", method, item)
      done = False
      try:
         if (method == "radio"):
            if item == "state":
               if (payload.upper() == "ON"):
                  self.playStation(-1)
               elif (payload.upper() == "OFF"):
                  self.stopPlayer()
               else:
                  log.info("Invalid payload state '%s' [ON/OFF]", payload)
               done = True

            elif item == "stationno":
               try:
                  stationno = int(payload)
                  self.playStation(stationno)
               except ValueError:
                  log.warn("Could not decode %s as station no", payload)                        
               done = True

            elif (item == "volumepercent"):
               try:
                  self.settings.setVolume(int(payload))
               except ValueError:
                  log.warn("Could not decode %s as volume percent", payload)    
               done = True

      except Exception as e:
         log.debug("on_message Error: %s" , e)            
      return done

   def run(self):

      self.SleepTime = float(0.1)
      lastplayerpos = 1 # media player position
      NoneCount = 0
      checkmessage = 50
      lastmediatitle = ""

      if (self.mqttbroker != None):
         self.mqttbroker.set_radio(self) 
         self.publish()

      log.info("Player thread started")

      while(not self.stopping):
         time.sleep(self.SleepTime)

         try:

            checkmessage -= 1
            if (checkmessage <= 0):
               checkmessage = 25

               if self.playerActive(): # self.menu.backgroundRadioActive():
                  checkmessage = 10
                  try:
                     currentplayerpos = self.player.stream_pos
                     if (currentplayerpos > lastplayerpos) and (currentplayerpos != None):
                           self.message = ", Radio Playing"
                           NoneCount = 0
                     elif (currentplayerpos == None) or (lastplayerpos == -1):
                           log.info("last %s, current pos %s",lastplayerpos, currentplayerpos) #, self.media.player.stream_length)
                           self.message = ", Radio Buffering"
                           if (lastplayerpos == 0) and (currentplayerpos == None):
                               NoneCount += 1
                     else:
                           self.message = ", Radio Paused"
                           log.info("last %s, current pos %s ",lastplayerpos, currentplayerpos) #, self.media.player.stream_length)
                           if self.playerPaused() == False:
                              NoneCount += 1

                     lastplayerpos = currentplayerpos

                     try:
                        if lastmediatitle != (self.player.media_title):
                           log.info('media_title "%s" was "%s"', self.player.media_title, lastmediatitle)
                           lastmediatitle = str(self.player.media_title)
                     except:
                        #log.info("no media title")
                        lastmediatitle = ""

                     try:
                        metadata = self.player.metadata
                        for item in metadata:
                           log.info("metadata %s", item)
                     except:
                        #log.debug("no metadata, %s", metadata)
                        metadata = ""
                     try:
                        log.info("metadata %s", self.player.metadata[0])
                     except:
                        metadata = ""


                  except Exception as e: # stream not valid I guess
                     log.error("Error: %s" , e)
                     self.message = ", Radio Erroring"
                     NoneCount += 1
                     #~ lastplayerpos = currentplayerpos

                  if (NoneCount > 20): # or (currentplayerpos == None):
                        log.info("Player may be stuck, restarting")
                        NoneCount = 0
                        self.restartPlayer()

                  # DO we need to increase the volume?
                  if (self.increasingvolume != -1):

                     # if we have something to play increase volume
                     if currentplayerpos != None:
                           self.increasingvolume += 2
                           if self.increasingvolume >= self.alarmThread.alarmVolume: #settings.getInt('volume'):
                              #self.settings.setVolume(self.settings.getInt('volume'))
                              self.settings.setVolume(self.alarmThread.alarmVolume)
                              self.increasingvolume = -1 # At required volume
                              log.info("Reached alarm volume level")
                           else:
                              self.settings.setVolume(self.increasingvolume)

                  #try:
                  #   metadata = self.player.metadata or {}
                  #   log.info("Track %s", metadata.get('track', ''))
                  #   log.info("Comment %s", metadata.get('comment', ''))
                  #   log.info("artist %s", metadata.get('artist', ''))
                  #   log.info("album %s", metadata.get('album', ''))

                  #except Exception as e: # stream not valid I guess
                  #   log.error("metadata error: %s" , e)


               else:
                  self.message = ""

         except:
            log.exception("Error in Media loop")
            self.stopping = True
            self.message = ", Errored"


if __name__ == '__main__':
    print ("Showing all current settings")
    media = MediaPlayer(None)
    print ("Playing file %s", PANIC_ALARM)
    player = Player("-cache 1024")
    player.loadfile(PANIC_ALARM)
    player.loop = 0
    # Set default prefix for all Player instances
    player.cmd_prefix = CmdPrefix.PAUSING_KEEP
    time.sleep(2)
    #~ try:

    meta = player.metadata['title']
    print ("title : " + meta)
    #~ except Exception as e:
        #~ e = sys.exc_info()[0]
        #~ print "Error: %s" % e
    time.sleep(2)
    player.stop()

