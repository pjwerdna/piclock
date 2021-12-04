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
# Changes
# 08/08/2020 - Added separate volumes for each daily alarm
# 13/08/2020 - Added debug logging for alarm volumes
# 12/10/2020 - Finally fixed the alarm time change during holidays being missed
# 14/10/2020 - Fixed multiple speach output when calling manualSetAlarm(...)
# 18/10/2020 - Better way of restarting the player when the station fails
# 02/11/2020 - Made alarm volumes use the volumepercent routines
# 22/12/2020 - Minor change to restarting the player when the station fails
# 31/12/2020 - Fix for alarms failing to be set when there are no events
# 24/01/2021 - Actually call media.restartPlayer
# 26/01/2021 - Moved player monitoring to player Thread
# 08/05/2021 - Fixed minor syntax errors.
# 10/08/2021 - Moved player monitoring to mediaplayer thread so it works when not playing an alarm 
# 23/11/2021 - Move Volume increase for alarms to MediaPlayer.py

log = logging.getLogger('root')

def suffix(d):
   return 'th' if 11<=d<=13 else {1:'st',2:'nd',3:'rd'}.get(d%10, 'th')

# Take a number or string, and put spaces between each character, replacing 0 for the word zero
def splitNumber(num):
   split = ' '.join("%s" % num)
   return split.replace("0","zero")

class AlarmThread(threading.Thread):

   def __init__(self, weatherFetcher, Mediaplayer, Settings, mqttbroker):
      threading.Thread.__init__(self)
      self.stopping=False
      self.nextAlarm=None
      self.nextAlarmStation = -1
      self.nextAlarmDayNo = -1
      self.alarmTimeout=None
      self.snoozing = False
      self.message = ""

      self.increasingvolume = -1 # no volume increase
      self.alarmVolume = 50 # random default volume for next alarm

      self.settings = Settings #Settings.Settings()
      self.media = Mediaplayer #MediaPlayer.MediaPlayer()
      self.alarmGatherer = AlarmGatherer.AlarmGatherer(Mediaplayer)
      self.weather = weatherFetcher
      self.mqttbroker = mqttbroker

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
         #self.settings.setVolume(30)
         #self.increasingvolume = 40 # anything lower is inaudiable
         self.media.soundAlarm(self, self.nextAlarmStation, 30)
      else:
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

      # Find next alarm starting with "Now"
      # If todays next alarm if after NOW use that
      # otherwise use tomorrows alarm

      nextAlarm = datetime.datetime.now() #pytz.timezone('Europe/London'))

      # find 1 minute past midnight
      #event = event.replace(hour=int(alarmtime[0]))
      #event = event.replace(minute=int(alarmtime[1]))
      #event = event.replace(second=0)

      # Weekday of the next event and alarm time
      weekday = datetime.datetime.weekday(nextAlarm)
      # Time for Alarm
      alarmtime = self.settings.get("alarm_weekday_" + str(weekday)).split(":")

      # put alarm time into event
      nextAlarm = nextAlarm.replace(hour=int(alarmtime[0]))
      nextAlarm = nextAlarm.replace(minute=int(alarmtime[1]))

      # if nextalarm is still today, use tomorrows date
      if nextAlarm < datetime.datetime.now(): #pytz.timezone('Europe/London')):
        nextAlarm += datetime.timedelta(days=1)

        # Weekday of the next event and alarm time
        weekday = datetime.datetime.weekday(nextAlarm)
        # TIme for Alarm
        alarmtime = self.settings.get("alarm_weekday_" + str(weekday)).split(":")

        # put alarm time into event
        nextAlarm = nextAlarm.replace(hour=int(alarmtime[0]))
        nextAlarm = nextAlarm.replace(minute=int(alarmtime[1]))

        # Next event from Calendar thats not today
        nexteventInfo = self.alarmGatherer.getNextEventDetails(False)
      else:
        # Next event from Calendar that might be today
        nexteventInfo = self.alarmGatherer.getNextEventDetails()


      # Modify alarm if its on a holiday
      HolidayCommingUp = False
      HolidayModeCommingUp = False


      # Work out if next event is a Holiday or maybe setting Holday Mode
      try:

         if (nexteventInfo == None):
             log.debug("no Events Listed")
             eventTime = datetime.datetime.now() + datetime.timedelta(days=1)

         else:
             # The time of the next Holiday on our calendar.
             eventTime = dateutil.parser.parse(nexteventInfo['start'].get('dateTime', nexteventInfo['start'].get('date')))
             eventTimeEnd = dateutil.parser.parse(nexteventInfo['end'].get('dateTime', nexteventInfo['end'].get('date')))
             log.debug("next event %s",eventTime)

             # The summary of the next Holiday on our calendar.
             eventsummary = nexteventInfo["summary"]
             log.debug("next event is %s",eventsummary)

             # if next event summary is holiday
             if (eventsummary.lower() == "holiday"):
                 log.info("Holiday Time alarm")
                 HolidayCommingUp = True
             if (eventsummary.lower() == "holiday mode"):
                 log.info("Holiday Mode alarm")
                 HolidayModeCommingUp = True
                 HolidayCommingUp = True

      except Exception as e:
         log.exception("Could not obtain Holiday information")
         # default to an unknown alarm tomorrow
         eventsummary = "Unknown"
         eventTime = datetime.datetime.now() + datetime.timedelta(days=1)

      try:

         default = self.alarmGatherer.getDefaultAlarmTime()

         log.debug("alarm start point %s",nextAlarm)
         log.debug("Alarm date %s", nextAlarm.date())
         log.debug("Event date %s", eventTime.date())

         weekday = datetime.datetime.weekday(nextAlarm)

         # Handle Alarm being within the next Holiday
         if (HolidayCommingUp == True) and ( nextAlarm.date() >= eventTime.date() ) and ( nextAlarm.date() <= eventTimeEnd.date() ):
             if (HolidayModeCommingUp == True):
                log.info("Holiday mode enabled, won't auto-set alarm as requested")
                return
             log.debug("Holiday comming up, using default wake time")
             default_wake =self.settings.get("default_wake")
             alarmtime = [default_wake[:2], default_wake[2:]]
         else:
             alarmtime = self.settings.get("alarm_weekday_" + str(weekday)).split(":")

         # Set station for alarm
         #self.nextAlarmStation = self.settings.get("alarm_station_" + str(weekday))
         #self.alarmVolume =self.settings.getInt("alarm_volume_" + str(weekday))
         # Now done later

         # put alarm time into event
         nextAlarm = nextAlarm.replace(hour=int(alarmtime[0]))
         nextAlarm = nextAlarm.replace(minute=int(alarmtime[1]))
         nextAlarm = nextAlarm.replace(second=0)

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

         self.setAlarmTime(nextAlarm, self.settings.getInt('alarm_station_' + str(weekday)), self.settings.getInt("alarm_volume_" + str(weekday)), weekday)
         self.settings.set('manual_alarm','') # We've just auto-set an alarm, so clear any manual ones

         # Tell MQTT broker abou the alarm
         if self.mqttbroker != None:
            self.mqttbroker.publish("alarm/time",nextAlarm.strftime("%H:%M"))
            self.mqttbroker.publish("alarm/date",nextAlarm.strftime("%d/%m/%Y"))
            self.mqttbroker.publish("alarm/datetime",nextAlarm.strftime("%Y-%m-%dT%H:%M"))
            # 2021-08-02T22:00:00
            self.mqttbroker.publish("alarm/stationno",str(self.settings.getInt('alarm_station_' + str(weekday))))
            self.mqttbroker.publish("alarm/stationname",self.settings.getStationName(self.settings.getInt('alarm_station_' + str(weekday))))
            self.mqttbroker.publish("alarm/volume",str(self.settings.getInt("alarm_volume_" + str(weekday))))

         # Read out the time we've just set
         hour = nextAlarm.strftime("%I").lstrip("0")
         readTime = "%s %s %s" % (hour, nextAlarm.strftime("%M"), splitNumber(nextAlarm.strftime("%p")))
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
      if alarmTime != None:
          self.settings.set('manual_alarm',calendar.timegm(alarmTime.utctimetuple()))
          self.setAlarmTime(alarmTime, AlarmStation)
          if AlarmStation != -1:
                self.media.playVoice('Manual alarm and Station has been set')
          else:
                self.media.playVoice('Manual alarm has been set')

   def setAlarmTime(self,alarmTime, AlarmStation = -1, AlarmVolume= -1, DayNo = -1):
      self.nextAlarm = alarmTime
      self.nextAlarmStation = AlarmStation
      self.nextAlarmDayNo = DayNo
      if (AlarmVolume == -1):
          self.alarmVolume = self.settings.getInt("minvolume")
      else:
          self.alarmVolume = AlarmVolume

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

   def publish(self):
      for dayno in range(0,7):
         self.mqttbroker.publish("alarms/%s/time" %(dayno), self.settings.get('alarm_weekday_' + str(dayno)))
         self.mqttbroker.publish("alarms/%s/stationno" %(dayno), self.settings.get('alarm_station_' + str(dayno)))
         self.mqttbroker.publish("alarms/%s/volume" %(dayno), self.settings.get('alarm_volume_' + str(dayno)))


   def on_message(self, topic, payload):
      try:
         method = topic[0:topic.find("/")] # before first "/"
         item = topic[topic.rfind("/")+1:]   # after last "/"
         log.debug("method='%s', item='%s'", method, item)
         done = False
         if method == "alarms":
            dayno = int(topic[topic.find("/")+1])
            if (dayno >= 0) & (dayno <= 7):
               if (item == "volume"):
                  if (int(payload) <= 100) & (int(payload) >= 0):
                     log.info("Setting volume for day %d to %s%%", dayno, int(payload))
                     self.settings.set('alarm_volume_' + str(dayno), int(payload))
                  else:
                     log.info("volume out of range (0-100) , %s", payload)
               elif (item == "stationno"):
                  if (int(payload) < self.settings.stationCount) & (int(payload) >= 0):
                     log.info("Setting Station No for day %d to %s", dayno, int(payload))
                     self.settings.set('alarm_station_' + str(dayno), int(payload))
                  else:
                     log.info("station out of range (0-%s) , %s", self.settings.stationCount, payload)

               if self.nextAlarmDayNo == dayno: # If the alarm day values changed we need to recalculate it
                  self.autoSetAlarm(True)
            else:
               log.debug("dayno out of range (0-6) , %s" , dayno)
            done = True

      except Exception as e:
         log.debug("on_message Error: %s" , e)
      
      return done

   def run(self):

      self.autoSetAlarm(self.settings.getIntOrSet('quiet_reboot') == 1)
      LastTime = datetime.datetime.now() #pytz.timezone('Europe/London'))

      #NoneCount = 0 # number of times player position is None for stall detection

      SleepTime = 1 #0.3

      lastPlayerPos = 0
      currentplayerpos = 0
      lastalarmremaining = 0

      if (self.mqttbroker != None):
         self.mqttbroker.set_alarm(self)  

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
               self.nextAlarm = None

         if(self.alarmTimeout is not None):
            alarmremaining = int((self.alarmTimeout - now).total_seconds()/60.0)
            if (alarmremaining != lastalarmremaining) :
               self.mqttbroker.publish("alarm/remaining",str(alarmremaining))
               lastalarmremaining = alarmremaining
            if (self.alarmTimeout < now):
               log.info("Alarm timeout reached, stopping alarm")
               self.stopAlarm()

         # Get what we have to play (if anything)

         #if self.media.playerActive() and (self.nextAlarm is not None):
         if self.media.playerActive() and (self.alarmTimeout is not None):
            self.message = ", Wakey Wakey!"

            try:
               currentplayerpos = self.media.player.stream_pos

               # Check if Player stuck or disconnected
               #if (currentplayerpos == None) or (currentplayerpos == lastPlayerPos):
               #    NoneCount += 1
               #    log.debug("nonecount=%d", NoneCount)
               #    #log.info("currentplayerpos=%d", currentplayerpos)
               #    if (NoneCount > 20): # or (currentplayerpos == None):
               #        log.info("Player may be stuck, restarting")
               #        #~ self.snoozefor()
               #        #self.silenceAlarm()

               #        #time.sleep(5)

               #        #~ self.media.soundAlarm(self, self.nextAlarmStation)
               #        # self.media.playStationURL(self.media.CurrentStation, self.media.CurrentURL, self.media.CurrentStationNo)
               #        self.media.restartPlayer()
               #        NoneCount = 0
               #else:
               #    NoneCount = 0

            except Exception as e:
               log.exception("Error: %s" , e)
               currentplayerpos = None

            lastPlayerPos = currentplayerpos
         else:
            # Stopped playing but still waiting for alarm to end
            if (self.media.playerActive() == False) and (self.alarmTimeout is not None):
               alarmremaining = 0
               self.mqttbroker.publish("alarm/remaining",str(alarmremaining))
               lastalarmremaining = alarmremaining
               self.stopAlarm()
            else:
               currentplayerpos = None
               self.message = ""

         if (self.alarmGatherer.getNextEventTimeout == None) or (self.alarmGatherer.eventCache == None) or (LastTime > self.alarmGatherer.getNextEventTimeout):
            nexteventInfo = self.alarmGatherer.getNextEventDetails()
            self.autoSetAlarm(True)

         LastTime = now
         time.sleep(SleepTime)
