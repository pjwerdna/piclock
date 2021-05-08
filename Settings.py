import sqlite3
import subprocess
#import CalendarCredentials
import logging
# Changes
# 1 Rearranged output of "python Settings.py"
# 09/08/2020 - Added daily alarm volumes & debug level
# 02/09/2020 - Added minimum volume level
# 02/11/2020 - Added proper volume percentage calls (used by web.py)
#              Added class functions for alarmFromPercent, alarmToPercent and remap
#              Should keep volume and volumepercent in step rounding permitting
# 03/11/2020 - Changed default volume and volumepercent to minimum
# 20/04/2021 - SetVolumePercent nolonger converts its parameter to a percentage as it already should be one
# 27/04/2021 - Got a better remap range to range routine
# 08/05/2021 - Fixed minor syntax errors.

log = logging.getLogger('root')

import threading
lock = threading.Lock()

# Radio stations we can play through mplayer
# http://www.radiofeeds.co.uk/bbcradio1.pls
# http://www.radiofeeds.co.uk/bbcradio2.pls
# From http://www.listenlive.eu/uk.html
# http://www.listenlive.eu/bbcradio2.m3u
# Ones From http://www.suppertime.co.uk/blogmywiki/2015/04/updated-list-of-bbc-network-radio-urls/
# dont work :(
STATIONS = [
   {'name':'BBC Radio 1', 'url':'http://open.live.bbc.co.uk/mediaselector/5/select/version/2.0/mediaset/http-icy-mp3-a/vpid/bbc_radio_one/format/pls.pls'},
   {'name':'BBC Radio 2', 'url':'http://open.live.bbc.co.uk/mediaselector/5/select/version/2.0/mediaset/http-icy-mp3-a/vpid/bbc_radio_two/format/pls.pls'},
   {'name':'BBC Radio London', 'url':'http://www.radiofeeds.co.uk/bbclondon.pls'},
   {'name':'Capital FM', 'url':'http://media-ice.musicradio.com/CapitalMP3.m3u'},
   {'name':'Kerrang Radio', 'url':'http://tx.whatson.com/icecast.php?i=kerrang.mp3.m3u'},
   {'name':'Magic 105.4', 'url':'http://tx.whatson.com/icecast.php?i=magic1054.aac.m3u'},
   {'name':'Radio X', 'url':'http://media-ice.musicradio.com/RadioXUKMP3.m3u'},
   {'name':'Smooth Radio', 'url':'http://media-ice.musicradio.com/SmoothLondonMP3.m3u'},
   {'name':'XFM', 'url':'http://media-ice.musicradio.com/XFM.m3u'},
]

class Settings:
   # Database connection details
   DB_NAME='settings.db'
   TABLE_NAME='settings'

   # Path to executable to modify volume
   VOL_CMD='/usr/local/bin/vol'

   # Our default settings for when we create the table
   DEFAULTS= [
      ('alarm_weekday_0','08:35'), # Monday
      ('alarm_station_0','1'),     # Radio station to play
      ('alarm_volume_0','100'),    # volume to play
      ('alarm_weekday_1','08:35'), # Tuesday
      ('alarm_station_1','1'),     # Radio station to play
      ('alarm_volume_1','100'),    # volume to play
      ('alarm_weekday_2','08:35'), # Wednesday
      ('alarm_station_2','1'),     # Radio station to play
      ('alarm_volume_2','100'),    # volume to play
      ('alarm_weekday_3','08:35'), # Thrusday
      ('alarm_station_3','1'),     # Radio station to play
      ('alarm_volume_3','100'),    # volume to play
      ('alarm_weekday_4','08:35'), # Friday
      ('alarm_station_4','1'),     # Radio station to play
      ('alarm_volume_4','100'),    # volume to play
      ('alarm_weekday_5','09:35'), # Saturday
      ('alarm_station_5','0'),     # Radio station to play
      ('alarm_volume_5','100'),    # volume to play
      ('alarm_weekday_6','09:35'), # Sunday
      ('alarm_station_6','0'),     # Radio station to play
      ('alarm_volume_6','100'),    # volume to play

      ('alarm_timeout','120'),     # If the alarm is still going off after this many minutes, stop it
      ('apipin','123456'),         # pin code for fsapi web interface access
      ('brightness_timeout','20'), # Time (secs) after which we should revert to auto-brightness
      ('brightness_tweak','0'),    # Allow tweaking brightness (0-99, effectively -50 to 50)
      ('calendar','Calendar@google.local'), # Calendar to gather events from
      ('clock_colour','255,0,0'),  # default clock colour
      ('clock_format','4'),        # 4 or 6 digit clock
      ('clock_font','dseg7modern'), # default font
      ('default_wake','0815'),     # Alarm time for Holidays
      ('holiday_mode','0'),        # Is holiday mode (no auto-alarm setting) enabled?
      ('gradual_volume','0'),      # Gradual volume increase on Alarm
      ('location_home','Birmingham, UK'), # Location for home
      ('location_work','London Airport'), # Default location for work (if lookup from event fails)
      ('manual_alarm',''),         # Manual alarm time (default not set)
      ('max_brightness','100'),    # Maximum brightness
      ('menu_font',''),            # default font
      ('menu_timeout','20'),       # Time (secs) after which an un-touched menu should close
      ('min_brightness','1'),      # Minimum brightness
      ('preempt_cancel','600'),    # Number of seconds before an alarm that we're allowed to cancel it
      ('quiet_reboot','0'),        # no speech when starting up (Only used during reboots or restarts of the clock)
      ('radio_delay','10'),        # Delay (secs) to wait for radio to start
      ('sfx_enabled','1'),         # Are sound effects enabled?
      ('snooze_length','5'),       # Time (mins) to snooze for
      ('station','1'),             # Radio station to play
      ('tts_path','/usr/bin/festival --tts'), # The command we pipe our TTS output into
      ('weather_location','London'), # The location to load weather for
      ('weather_on_alarm','1'),    # Read out the weather on alarm cancel
      ('volume','55'),            # Current Volume
      ('wakeup_time','30'),        # Time (mins) before event that alarm should be triggered (excluding travel time) (30 mins pre-shift + 45 mins wakeup)
      ('WUG_KEY',''),              # wunderground access key (doesnt work anymore!)
      ('DEBUGLEVEL','10'),         # default loglevel is debug
      ('minvolume','55'),          # Minimum allowed volume
      ('volumepercent','0'),     # Current volume as a percentage where 0% is minvolume
   ]

   def __init__(self):
      self.conn = sqlite3.connect(self.DB_NAME, check_same_thread=False)
      self.c = self.conn.cursor()

   def setup(self):
      # This method called once from alarmpi main class
      # Check to see if our table exists, if not then create and populate it
      r = self.c.execute('SELECT COUNT(*) FROM sqlite_master WHERE type="table" AND name=?;',(self.TABLE_NAME,))
      if self.c.fetchone()[0]==0:
         self.firstRun()

      # Set the volume on this machine to what we think it should be
      self.setVolume(self.getInt('volume'))

   def firstRun(self):
      log.warn("Running first-time SQLite set-up")
      self.c.execute('CREATE TABLE '+self.TABLE_NAME+' (name text, value text)')
      self.c.executemany('INSERT INTO '+self.TABLE_NAME+' VALUES (?,?)',self.DEFAULTS)
      self.conn.commit()

   def get(self,key):
      lock.acquire()
      #log.info("get %s",key)
      self.c.execute('SELECT * FROM '+self.TABLE_NAME+' WHERE name=?',(key,))
      r = self.c.fetchone()
      lock.release()
      if r is None:
         raise Exception('Could not find setting %s' % (key))
      return r[1]

   def getorset(self,key, default = ""):
      lock.acquire()
      self.c.execute('SELECT * FROM '+self.TABLE_NAME+' WHERE name=?',(key,))
      r = self.c.fetchone()
      if r is None:
        log.warn("Setting value of %s to %s",key,default)
        self.c.execute('INSERT INTO '+self.TABLE_NAME+' VALUES (?,?)',(key,default))
        self.conn.commit()
        lock.release()
        return default
      lock.release()
      return r[1]

   def getcolour(self,key):

      try:
         colour = self.get(key).split(",")
         return (int(colour[0]),int(colour[1]),int(colour[2]))
      except ValueError:
         log.warn("Could not fetch %s as colour, returning white",key)
         return (255,255,255)

   def getIntOrSet(self,key,Default = ""):
      try:
         return int(self.getorset(key, Default))
      except ValueError:
         log.warn("Could not fetch %s as integer, value was [%s], returning 0",key,self.get(key))
         return 0

   def getInt(self,key):
      try:
         return int(self.get(key))
      except ValueError:
         log.warn("Could not fetch %s as integer, value was [%s], returning 0",key,self.get(key))
         return 0

   def set(self,key,val):
      self.get(key) # So we know if it doesn't exist

      try:
          if key=="volume":
              if (int(val)<self.getInt("minvolume")):
                  val = self.getInt("minvolume")

          lock.acquire()
          self.c.execute('UPDATE '+self.TABLE_NAME+' SET value=? where name=?',(val,key,))
          self.conn.commit()
          lock.release()

          if key=="volume": # minvolume% to 100%
              newvol = self.volumeRangeToPercent(int(val))
              self.setVolume(int(val))
              lock.acquire()
              self.c.execute('UPDATE '+self.TABLE_NAME+' SET value=? where name=?',('volumepercent',newvol))
              self.conn.commit()
              lock.release()

          elif key=="volumepercent": # 0 to 100% (mapped as minvolume% to 100%)
              newvol = self.volumePercentToRange(int(val))
              self.setVolume(int(val))
              lock.acquire()
              self.c.execute('UPDATE '+self.TABLE_NAME+' SET value=? where name=?',('volume',newvol))
              self.conn.commit()
              lock.release()


      except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.error("Error: %s" , e)
            log.warn("Failure setting %s as [%s], returning 0",key,val)

   def setVolume(self,val): # 0 to 100% mapped -> minvolume% to 100%
      actualVolume = self.volumePercentToRange(val)
      subprocess.Popen("%s %s" % (self.VOL_CMD,actualVolume), stdout=subprocess.PIPE, shell=True)
      log.info("Volume adjusted to %s, %s%%", val, actualVolume)

   # Convert percentage to usable range
   def volumePercentToRange(self,AlarmValue):
        return self.remap(AlarmValue,0,100,self.getInt("minvolume"),100)

   # Convert usable range to percentage
   def volumeRangeToPercent(self,AlarmValue):
        return self.remap(AlarmValue,self.getInt("minvolume"),100,0,100)

   def badremap(self, x, oMin, oMax, nMin, nMax ):
        # Map x which is in oMin to oMax to the range nMIn to nMax

        try:
            #range check
            if oMin == oMax:
                print ("Warning: remap: Zero input range")
                return x

            if nMin == nMax:
                print ("Warning: remap: Zero output range")
                return x

            #check reversed input range
            reverseInput = False
            oldMin = min( oMin, oMax )
            oldMax = max( oMin, oMax )
            if not oldMin == oMin:
                reverseInput = True

            #check reversed output range
            reverseOutput = False
            newMin = min( nMin, nMax )
            newMax = max( nMin, nMax )
            if not newMin == nMin :
                reverseOutput = True

            portion = (x-oldMin)*(newMax-newMin)/(oldMax-oldMin)
            if reverseInput:
                portion = (oldMax-x)*(newMax-newMin)/(oldMax-oldMin)

            result = portion + newMin
            if reverseOutput:
                result = newMax - portion

        except: # catch *all* exceptions
            e = sys.exc_info()[0]
            log.error("Error: in remap %s" , e)
            result = 0

        return result

   def remap(self, value, leftMin, leftMax, rightMin, rightMax):
      # Figure out how 'wide' each range is
      leftSpan = leftMax - leftMin
      rightSpan = rightMax - rightMin

      # Convert the left range into a 0-1 range (float)
      valueScaled = float(value - leftMin) / float(leftSpan)

      # Convert the 0-1 range into a value in the right range.
      return int(round(rightMin + (valueScaled * rightSpan)))

   def __del__(self):
      self.conn.close()

if __name__ == '__main__':

   print ("Showing all current settings")
   settings = Settings()

   #settings.getorset('minvolume','55')
   #settings.getorset('volumepercent',remap(settings.getInt("volume"),settings.getInt("minvolume"),100,0,100))

   for s in settings.DEFAULTS:
      print ("%s = %s" % (s[0], settings.get(s[0])))
