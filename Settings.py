import sqlite3
import subprocess
#import CalendarCredentials
import logging
# Changes
# 1 Rearranged output of "python Settings.py"

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
      ('alarm_station_0','1'), # Radio station to play
      ('alarm_weekday_1','08:35'), # Tuesday
      ('alarm_station_1','1'), # Radio station to play
      ('alarm_weekday_2','08:35'), # Wednesday
      ('alarm_station_2','1'), # Radio station to play
      ('alarm_weekday_3','08:35'), # Thrusday
      ('alarm_station_3','1'), # Radio station to play
      ('alarm_weekday_4','08:35'), # Friday
      ('alarm_station_4','1'), # Radio station to play
      ('alarm_weekday_5','09:35'), # Saturday
      ('alarm_station_5','0'), # Radio station to play
      ('alarm_weekday_6','09:35'), # Sunday
      ('alarm_station_6','0'), # Radio station to play

      ('alarm_timeout','120'), # If the alarm is still going off after this many minutes, stop it
      ('apipin','123456'),
      ('brightness_timeout','20'), # Time (secs) after which we should revert to auto-brightness
      ('brightness_tweak','0'),
      ('calendar','Calendar@google.local'), # Calendar to gather events from
      ('clock_colour','255,0,0'), # default clock colour
      ('clock_format','4'), # 4 or 6 digit clock
      ('clock_font','dseg7modern'), # default font
      ('default_wake','0815'), # Alarm time for Holidays
      ('holiday_mode','0'), # Is holiday mode (no auto-alarm setting) enabled?
      ('gradual_volume','0'), # Gradual volume increase on Alarm
      ('location_home','Birmingham, UK'), # Location for home
      ('location_work','London Airport'), # Default location for work (if lookup from event fails)
      ('manual_alarm',''), # Manual alarm time (default not set)
      ('max_brightness','100'), # Maximum brightness
      ('menu_font',''), # default font
      ('menu_timeout','20'), # Time (secs) after which an un-touched menu should close
      ('min_brightness','1'), # Minimum brightness
      ('preempt_cancel','600'), # Number of seconds before an alarm that we're allowed to cancel it
      ('quiet_reboot','0'), # no speech when starting up (Only used during reboots or restarts of the clock)
      ('radio_delay','10'), # Delay (secs) to wait for radio to start
      ('sfx_enabled','1'), # Are sound effects enabled?
      ('snooze_length','5'), # Time (mins) to snooze for
      ('station','1'), # Radio station to play
      ('tts_path','/usr/bin/festival --tts'), # The command we pipe our TTS output into
      ('weather_location','Slough'), # The location to load weather for
      ('weather_on_alarm','1'), # Read out the weather on alarm cancel
      ('volume','100'), # Volume
      ('wakeup_time','30'), # Time (mins) before event that alarm should be triggered (excluding travel time) (30 mins pre-shift + 45 mins wakeup)
      ('WUG_KEY',''), # wunderground access key (doesnt work anymore!)
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

      log.info("get %s",key)

   def getInt(self,key):
      try:
         return int(self.get(key))
      except ValueError:
         log.warn("Could not fetch %s as integer, value was [%s], returning 0",key,self.get(key))
         return 0

      log.info("get %s",key)

   def set(self,key,val):
      self.get(key) # So we know if it doesn't exist

      if key=="volume":
         self.setVolume(val)
      lock.acquire()

      self.c.execute('UPDATE '+self.TABLE_NAME+' SET value=? where name=?',(val,key,))
      self.conn.commit()
      lock.release()

   #~ def setdata(self,key,val):
      #~ lock.acquire()

      #~ self.c.execute('UPDATE '+self.TABLE_NAME+' SET value=? where name=?',(sqlite3.Binary(val),key,))
      #~ self.conn.commit()
      #~ lock.release()

   def setVolume(self,val):
      subprocess.Popen("%s %s" % (self.VOL_CMD,val), stdout=subprocess.PIPE, shell=True)
      log.info("Volume adjusted to %s", val)

   def __del__(self):
      self.conn.close()

if __name__ == '__main__':
   print "Showing all current settings"
   settings = Settings()
   for s in settings.DEFAULTS:
      print "%s = %s" % (s[0], settings.get(s[0]))
