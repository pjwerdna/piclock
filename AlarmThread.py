#!/usr/bin/python

import time
import datetime
import pytz
import calendar
import threading
#~ import Settings
import AlarmGatherer
#~ import MediaPlayer
import dateutil.parser
import logging
import urllib2
#from TravelCalculator import TravelCalculator

log = logging.getLogger('root')

def suffix(d):
   return 'th' if 11<=d<=13 else {1:'st',2:'nd',3:'rd'}.get(d%10, 'th')

# Take a number or string, and put spaces between each character, replacing 0 for the word zero
def splitNumber(num):
   split = ' '.join("%s" % num)
   return split.replace("0","zero")

class AlarmThread(threading.Thread):

   def __init__(self, weatherFetcher, Mediaplayer, Settings):
      threading.Thread.__init__(self)
      self.stopping=False
      self.nextAlarm=None
      self.nextAlarmStation = -1
      self.alarmTimeout=None
      self.snoozing = False

      self.currentvolume = -1 # no volume increase

      self.settings = Settings #Settings.Settings()
      self.media = Mediaplayer #MediaPlayer.MediaPlayer()
      self.alarmGatherer = AlarmGatherer.AlarmGatherer(Mediaplayer)
      self.weather = weatherFetcher

      self.fromEvent = False # False if auto or manual, True if from an event

      #~ self.travel = TravelCalculator(self.settings.get('location_home'))
      #~ self.travelTime = 0 # The travel time we last fetched
      #~ self.travelCalculated = False # Have we re-calculated travel for this alarm cycle?

   def stop(self):
      log.info("Stopping alarm thread")
      self.stopping=True
      if(self.media.playerActive()):
         self.stopAlarm()

   def isAlarmSounding(self):
      return (self.media.playerActive() and self.nextAlarm is not None and self.nextAlarm < datetime.datetime.now()) #pytz.timezone('Europe/London')))

   def isSnoozing(self):
      return self.snoozing

   def getNextAlarm(self):
      return self.nextAlarm

   def snoozefor(self, Snoozetime = 1):
      log.info("Snoozing alarm for %s minutes", Snoozetime)

      alarmTime = datetime.datetime.now() #pytz.timezone('Europe/London'))
      alarmTime += datetime.timedelta(minutes=Snoozetime)
      self.setAlarmTime(alarmTime, self.nextAlarmStation)
      self.snoozing = True
      self.alarmTimeout = None
      self.fromEvent = False

      self.silenceAlarm() # Only silence after we've re-set the alarm to avoid a race condition

   def snooze(self):
      log.info("Snoozing alarm for %s minutes", self.settings.getInt('snooze_length'))

      alarmTime = datetime.datetime.now() #pytz.timezone('Europe/London'))
      alarmTime += datetime.timedelta(minutes=self.settings.getInt('snooze_length'))
      self.setAlarmTime(alarmTime, self.nextAlarmStation)
      self.snoozing = True
      self.alarmTimeout = None
      self.fromEvent = False

      self.silenceAlarm() # Only silence after we've re-set the alarm to avoid a race condition

   def soundAlarm(self):
      log.info("Alarm triggered")
      if (self.settings.getInt('gradual_volume') == 1):
          # Should do this when actually outputting sound really!
          self.settings.setVolume(30)
          self.currentvolume = 40 # anything lower is inaudiable
      self.media.soundAlarm(self, self.nextAlarmStation)
      timeout = datetime.datetime.now() #pytz.timezone('Europe/London'))
      timeout += datetime.timedelta(minutes=self.settings.getInt('alarm_timeout'))
      self.alarmTimeout = timeout

   # External Alarm Stop
   def stopAlarmTrigger(self):
       self.alarmTimeout = datetime.datetime.now() #pytz.timezone('Europe/London'))
       # This thread should now call stopalarm

   # Only to be called if we're stopping this alarm cycle - see silenceAlarm() for shutting off the player
   def stopAlarm(self):
      log.info("Stopping alarm")
      self.silenceAlarm()

      self.clearAlarm()

      if (self.settings.getInt('weather_on_alarm')==1) and (self.stopping==False):
         log.debug("Playing weather information")

         now = datetime.datetime.now() #pytz.timezone('Europe/London'))

         weather = ""
         try:
            weather = self.weather.getWeather().speech()
         except Exception:
            log.exception("Failed to get weather information")

         day = now.strftime("%d").lstrip("0")
         day += suffix(now.day)

         hour = now.strftime("%I").lstrip("0")

         salutation = "morning" if now.strftime("%p")=="AM" else "afternoon" if int(hour) < 18 else "evening"

         # Today is Monday 31st of October, the time is 9 56 AM
         speech = "Good %s Dave. Today is %s %s %s, the time is %s %s %s. " % (salutation, now.strftime("%A"), day, now.strftime("%B"), hour, now.strftime("%M"), now.strftime("%p"))
         speech += weather

         self.media.playSpeech(speech)

      # Send a notification to HomeControl (OpenHAB) that we're now awake
      #~ try:
         #~ log.debug("Sending wake notification to HomeControl")
         #~ urllib2.urlopen("http://homecontrol:9090/CMD?isSleeping=OFF").read()
      #~ except Exception:
         #~ log.exception("Failed to send wake state to HomeControl")


      # Automatically set up our next alarm.
      self.autoSetAlarm()

   # Stop whatever is playing
   def silenceAlarm(self):
      log.info("Silencing alarm")
      self.media.stopPlayer()

   def autoSetAlarm(self, quiet = False):

      if self.settings.getInt('holiday_mode')==1:
         log.info("Holiday mode enabled, won't auto-set alarm as requested")
         return

      log.info("Automatically setting next alarm")

      event = datetime.datetime.now() #pytz.timezone('Europe/London'))

      HolidayCommingUp = False
      HolidayModeCommingUp = False


      try:
         # Next event from Calendar
         nexteventInfo = self.alarmGatherer.getNextEventDetails()
         # The time of the next Holiday on our calendar.
         eventTime = dateutil.parser.parse(nexteventInfo['start'].get('dateTime', nexteventInfo['start'].get('date')))
         log.debug("next event %s",eventTime)

         # The summary of the next Holiday on our calendar.
         eventsummary = nexteventInfo["summary"]
         log.debug("next event is %s",eventsummary)

         # if next event summary is holiday
         if (eventsummary.lower() == "holiday"):
             HolidayCommingUp = True
         if (eventsummary.lower() == "holiday mode"):
             HolidayModeCommingUp = True
             HolidayCommingUp = True

      except Exception as e:
         log.exception("Could not obtain Holiday information")
         eventsummary = "Unknown"

      try:

         default = self.alarmGatherer.getDefaultAlarmTime()

         log.debug("alarm start point %s",event)

         weekday = datetime.datetime.weekday(event)

         if (HolidayCommingUp == True) and (eventTime.date() == event.date()):
             if (HolidayModeCommingUp == True):
                log.info("Holiday mode enabled, won't auto-set alarm as requested")
                return
             log.debug("Holiday comming up, using default wake time")
             default_wake =self.settings.get("default_wake")
             alarmtime = [default_wake[:2], default_wake[2:]]
         else:
             alarmtime = self.settings.get("alarm_weekday_" + str(weekday)).split(":")

         self.nextAlarmStation = self.settings.get("alarm_station_" + str(weekday))

         event = event.replace(hour=int(alarmtime[0]))
         event = event.replace(minute=int(alarmtime[1]))
         event = event.replace(second=0)

         if event < datetime.datetime.now(): #pytz.timezone('Europe/London')):
            event += datetime.timedelta(days=1)
            if (HolidayCommingUp == True) and (eventTime.date() == event.date()):
                log.info("Holiday comming up, using default wake time")
                default_wake = self.settings.get("default_wake")
                alarmtime = [default_wake[:2], default_wake[2:]]
            else:
                weekday = datetime.datetime.weekday(event)
                alarmtime = self.settings.get("alarm_weekday_" + str(weekday)).split(":")

            event = event.replace(hour=int(alarmtime[0]))
            event = event.replace(minute=int(alarmtime[1]))


         #~ log.debug("next alarm %s", event)

         #diff = datetime.timedelta(minutes=self.settings.getInt('wakeup_time')) # How long before event do we want alarm
         #event -= diff

         # Adjust for travel time
         #self.travelTime = self.fetchTravelTime()
         #travelDelta = datetime.timedelta(minutes=self.travelTime)
         #event -= travelDelta

         #~ if event > default: # Is the event time calculated greater than our default wake time
            #~ log.debug("Calculated wake time of %s is after our default of %s, reverting to default",event,default)
            #~ event = default
            #~ self.fromEvent = False
         #~ else:
         self.fromEvent = True

         self.setAlarmTime(event, self.settings.getInt('alarm_station_' + str(weekday)))
         self.settings.set('manual_alarm','') # We've just auto-set an alarm, so clear any manual ones

         # Read out the time we've just set
         hour = event.strftime("%I").lstrip("0")
         readTime = "%s %s %s" % (hour, event.strftime("%M"), splitNumber(event.strftime("%p")))
         if quiet == False:
            self.media.playVoice('An automatic alarm has been set for %s' % (readTime))

      except Exception as e:
         log.exception("Could not automatically set alarm")
         if quiet == False:
            self.media.playVoice('Error setting alarm')
         self.nextAlarm = None

      self.settings.set("quiet_reboot","0")

   # Find out where our next event is, and then calculate travel time to there
   #~ def fetchTravelTime(self, update=False):
      #~ destination = self.alarmGatherer.getNextEventLocation(includeToday=update)
      #~ if(destination is None):
         #~ destination = self.settings.get('location_work')
      #~ travelTime = self.travel.getTravelTime(destination)

      #~ return travelTime

   #~ def travelAdjustAlarm(self):
      #~ log.info("Adjusting alarm for current travel time")
      #~ newTravelTime = self.fetchTravelTime(update=True)
      #~ travelDiff = newTravelTime - self.travelTime
      #~ log.debug("Old travel time: %s, new travel time: %s, diff: %s" % (self.travelTime, newTravelTime, travelDiff))

      #~ adjustDelta = datetime.timedelta(minutes=travelDiff)
      #~ newTime = self.nextAlarm - adjustDelta
      #~ self.setAlarmTime(newTime)
      #~ self.travelCalculated = True

   def manualSetAlarm(self,alarmTime, AlarmStation = -1):
      log.info("Manually setting next alarm to %s",alarmTime)
      self.fromEvent = False
      if alarmTime <> None:
          self.settings.set('manual_alarm',calendar.timegm(alarmTime.utctimetuple()))
          self.setAlarmTime(alarmTime)
          self.media.playVoice('Manual alarm has been set')
      if AlarmStation <> -1:
        self.nextAlarmStation = AlarmStation
        self.media.playVoice('Default Alarm Station has Been changed')

   def setAlarmTime(self,alarmTime, AlarmStation = -1):
      self.nextAlarm = alarmTime
      self.nextAlarmStation = AlarmStation
      log.info("Alarm set for %s", alarmTime)

   def clearAlarm(self):
      self.snoozing = False
      self.nextAlarm = None
      self.alarmTimeout = None
      self.settings.set('manual_alarm','') # If we've just stopped an alarm, we can't have a manual one set yet
      self.travelTime = 0
      self.travelCalculated = False
      self.fromEvent = False

   # Number of seconds until alarm is triggered
   def alarmInSeconds(self):
      #now = datetime.datetime.now(pytz.timezone('Europe/London'))
      if self.nextAlarm is None:
         return -1

      if self.isSnoozing() or self.isAlarmSounding():
         return 0

      diff = self.nextAlarm - datetime.datetime.now() #pytz.timezone('Europe/London')) #now
      return diff.seconds

   # Return a line of text describing the alarm state
   def getMenuLine(self):
      #now = datetime.datetime.now(pytz.timezone('Europe/London'))
      message = ""

      if self.nextAlarm is not None:
         nextAlarmCopy = self.nextAlarm
         #now = datetime.datetime.now(pytz.timezone('Europe/London'))
         diff = nextAlarmCopy - datetime.datetime.now() #pytz.timezone('Europe/London')) #now
         if diff.days < 1:
            if self.snoozing:
               message+="Snoozing"
            else:
               message+="Alarm"

            if diff.seconds < (2 * 60 * 60): # 2 hours
               if self.snoozing:
                  message+=" for "
               else:
                  message+=" in "
               message+="%s min" % ((diff.seconds//60)+1)
               if diff.seconds//60 != 0:
                  message+="s"
            else:
               if self.snoozing:
                  message+=" until "
               else:
                  message+=" at "
               message+=nextAlarmCopy.strftime("%H:%M")
      else:
          #No Alarm Set. A space ensures any old message gets removed
          message+=" "

      return message

   def run(self):

      self.autoSetAlarm(self.settings.getIntOrSet('quiet_reboot') == 1)
      LastTime = datetime.datetime.now() #pytz.timezone('Europe/London'))

      NoneCount = 0

      SleepTime = 1 #0.3

      lastPlayerPos = 0
      currentplayerpos = 0

      while(not self.stopping):
          now = datetime.datetime.now() #pytz.timezone('Europe/London'))

          #~ if(self.nextAlarm is not None and self.fromEvent and self.alarmInSeconds() < 3600 and not self.travelCalculated):
             #~ # We're inside 1hr of an event alarm being triggered, and we've not taken into account the current traffic situation
             #~ self.travelAdjustAlarm()

          if(self.nextAlarm is not None and self.nextAlarm < now and not self.media.playerActive()):
                diff = now - LastTime
                # if the time hasnt changed much since the last check sound the alarm
                # If it has changed then the clock was probably set.
                if diff <= datetime.timedelta(minutes=30):
                    self.soundAlarm()

          if(self.alarmTimeout is not None and self.alarmTimeout < now):
             log.info("Alarm timeout reached, stopping alarm")
             self.stopAlarm()

          # Get what we have to play (if anything)
          if self.media.playerActive() and (self.nextAlarm is not None):
                try:
                    currentplayerpos = self.media.player.stream_pos

                    if (currentplayerpos == None) or (currentplayerpos == lastPlayerPos):
                        NoneCount += 1
                        log.info("nonecount=%d", NoneCount)
                        if NoneCount > 20:
                            log.info("Player may be stuck, restarting")
                            #~ self.snoozefor()
                            self.silenceAlarm()

                            time.sleep(5)
                            log.info("Player Restarting")
                            #~ self.media.soundAlarm(self, self.nextAlarmStation)
                            self.media.playStationURL(self.media.CurrentStation, self.media.CurrentURL)
                            NoneCount = 0
                    else:
                        NoneCount = 0

                except:
                    currentplayerpos = None

                lastPlayerPos = currentplayerpos
          else:
                currentplayerpos = None

          # DO we need to increase the volume?
          if (self.currentvolume != -1):

              # if we have something to play increase volume
              if currentplayerpos != None:
                  self.currentvolume += 2
                  if self.currentvolume >= self.settings.getInt('volume'):
                      self.settings.setVolume(self.settings.getInt('volume'))
                      self.currentvolume = -1 # At required volume
                  else:
                      self.settings.setVolume(self.currentvolume)

          if (self.alarmGatherer.getNextEventTimeout == None) or (self.alarmGatherer.eventCache == None) or (LastTime > self.alarmGatherer.getNextEventTimeout):
            nexteventInfo = self.alarmGatherer.getNextEventDetails()

          LastTime = now
          time.sleep(SleepTime)
