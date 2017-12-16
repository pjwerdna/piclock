import web
from web import form
from web.wsgiserver import CherryPyWSGIServer
import time
import datetime
import pytz
import threading
import logging
import Settings
import random
from hashlib import sha1
import os
import pickle
from wsgilog import WsgiLog
import json

urls = (
    '/','error',
    '/home', 'player',
    '/alarms', 'alarms',
    '/settings', 'set',
    '/reset', 'reset',
    '/logout', 'logout',
    '/signin', 'signin',
    '/api', 'api',
    '/api/(.+)', 'api',
    '/player','player',
    '/static/','error',
    #~ '/(images|js)/(.+)', 'static',
)

#~ global session
global users
global alarm, brightnessthread
global settings
global session

# Player status as text
PlayerStatus = {0:"Stopped", 1:"Playing", 2:"Paused" }


# Creates the use the first time the web login is used.
# The first login will fail, but the  username and password will be valid
# on the next attempt
users = {}
alarm = None

log = logging.getLogger('root')

app = web.application(urls, globals())
#~ app.run(WebLog)

if web.config.get('_session') is None:
    log.debug("reading session from disk")
    session = web.session.Session(app, web.session.DiskStore('sessions'),
                      initializer={'user': ''})
    web.config._session = session
else:
    session = web.config._session

webcredential_path = None
home_dir = os.path.expanduser('~')
#~ log.info("home_dir = %s", home_dir)
credential_dir = os.path.join(home_dir, '.credentials')
if not os.path.exists(credential_dir):
    os.makedirs(credential_dir)
webcredential_path = os.path.join(credential_dir, 'Websusers')

# A simple user object that doesn't store passwords in plain text
# see http://en.wikipedia.org/wiki/Salt_(cryptography)
class PasswordHash(object):
    def __init__(self, password_):
        self.salt = "".join(chr(random.randint(33,127)) for x in xrange(64))
        self.saltedpw = sha1(password_ + self.salt).hexdigest()
    def check_password(self, password_):
        """checks if the password is correct"""
        return self.saltedpw == sha1(password_ + self.salt).hexdigest()


render = web.template.render('web/', cache=False, base='layout')
render_nomenu = web.template.render('web/', cache=False, base='layout_nomenu')
render_json = web.template.render('web/', cache=False)

#~ settings = Settings.Settings()

# default reply randomisation
global replyno
replyno = 0
#~ session = None

global StationList
StationList = []
for stationname in Settings.STATIONS:
    StationList.append(stationname['name'])

global iplist
iplist = []


def GetIPForNetwork(Network): # find the IP of the given network
    ipv4 = os.popen('ip addr show ' + Network).read()
    ipv4lines = ipv4.split(chr(10))

    for ipline in ipv4lines:
        if ipline.find("inet ") > 0:
            ipinfo = ipline.strip().split(" ")
            ipaddress = ipinfo[1]

            return ipaddress.split("/")[0]

    return ""

def Gethoursselector(requiredID,requiredSelection):
    #~ log.info("match '%s'", requiredSelection)
    hoursselector = '<select id="' + requiredID + '" name="' + requiredID + '">'
    for hour in range(0 , 24):
        if hour == requiredSelection:
            hoursselector += '<option selected value="' + str(100+hour)[-2:] +'">' + str(100+hour)[-2:] +'</option>\n'
        else:
            hoursselector += '<option value="' + str(100+hour)[-2:] +'">' + str(100+hour)[-2:] +'</option>\n'
    hoursselector += '<option value="XX">XX</option>\n'
    hoursselector += '</select>'
    return hoursselector


def Getminsselector(requiredID,requiredSelection):
    minsselector = '<select id="' + requiredID + '" name="' + requiredID + '">'
    for minute in range(0 , 60):
        if minute == requiredSelection:
            minsselector += '<option selected value="' + str(100+minute)[-2:] +'">' + str(100+minute)[-2:] +'</option>\n'
        else:
            minsselector += '<option value="' + str(100+minute)[-2:] +'">' + str(100+minute)[-2:]+'</option>\n'
    minsselector += '<option value="XX">XX</option>\n'
    minsselector += '</select>'
    return minsselector


def Getradioselector(requiredID,requiredSelection):
    radioselector = '<select id=' + requiredID + ' name="' + requiredID + '">'
    for stationname in Settings.STATIONS:
        if stationname['name'] == requiredSelection:
            radioselector += '<option selected value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'
        else:
            radioselector += '<option value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'
    #~ log.info("requiredSelection '%s'", requiredSelection)
    if (requiredSelection == "None") or (requiredSelection == ""):
        radioselector += '<option selected value="None">None</option>\n'
    else:
        radioselector += '<option value="None">None</option>\n'
    radioselector += '</select>'
    return radioselector

def userLoggedout(sessioninfo):
    try:
        temp = sessioninfo.user
        #~ log.debug("user=%s", temp)
        if temp == "":
            return True
        return False
    except:
        return True

def GetUser(sessioninfo):
    try:
        temp = sessioninfo.user
        #~ log.debug("user=%s", temp)
        return temp
    except:
        return ""

class static:
    def GET(self, media, file):
      global home_dir
      if userLoggedout(session):
        #~ raise web.seeother('/error')
        global replyno
        replies = {
            0: "+++Mr. Jelly! Mr. Jelly!+++",
            1: "+++Error At Address: 14, Treacle Mine Road, Ankh-Morpork+++",
            2: "+++MELON MELON MELON+++",
            3: "+++Divide By Cucumber Error. Please Reinstall Universe And Reboot +++",
            4: "+++Whoops! Here Comes The Cheese! +++",
            5: "+++Oneoneoneoneoneoneone+++",
        }
        replyno += 1
        if replyno == 6:
            replyno  = 0
        raise web.Unauthorized(replies.get(replyno, "+++Out of Cheese Error++"))
      else:
        try:
            file = file.replace("../","")
            f = open('/home/pi/static/'+file, 'r')
            return f.read()
        except Exception:
            log.exception("Failed open file %s", '/home/pi/static/'+file)
            return web.Unauthorized("+++Out of Cheese Error++") # you can send an 404 error here if you want

class error:
   def GET(self):
        global replyno
        replies = {
            0: "+++Mr. Jelly! Mr. Jelly!+++",
            1: "+++Error At Address: 14, Treacle Mine Road, Ankh-Morpork+++",
            2: "+++MELON MELON MELON+++",
            3: "+++Divide By Cucumber Error. Please Reinstall Universe And Reboot +++",
            4: "+++Whoops! Here Comes The Cheese! +++",
            5: "+++Oneoneoneoneoneoneone+++",
        }
        replyno += 1
        if replyno == 6:
            replyno  = 0
        raise web.Unauthorized(replies.get(replyno, "+++Out of Cheese Error++"))

        #~ render_nomenu.error()
        #~ +++Mr. Jelly! Mr. Jelly!+++
        #~ +++Error At Address: 14, Treacle Mine Road, Ankh-Morpork+++
        #~ +++MELON MELON MELON+++
        #~ +++Divide By Cucumber Error. Please Reinstall Universe And Reboot +++
        #~ +++Whoops! Here Comes The Cheese! +++
        #~ +++Oneoneoneoneoneoneone+++

   def POST(self):
      return "+++Divide By Cucumber Error. Please Reinstall Universe And Reboot +++"


class index:
   def getAlarmForm(self):
      global alarm, StationList

      nextAlarm = alarm.getNextAlarm()
      alarmTime = ""

      if nextAlarm is not None:
         alarmTime = nextAlarm.strftime("%H%M")

      #~ StationList = []
      #~ for stationname in Settings.STATIONS:
            #~ StationList.append(stationname['name'])

      return form.Form(
         form.Textbox("time",
            form.notnull,
            form.regexp('[0-2][0-9][0-5][0-9]', 'Must be a 24hr time'),
            description="Set alarm time",
            value = alarmTime,
         ),
         form.Dropdown('station', args = StationList, description="Station", value = StationList[int(settings.getIntOrSet('default_station',0))]),
      )

   def GET(self):
      if userLoggedout(session):
        raise web.seeother('/signin')
      else:
        form = self.getAlarmForm()()
        return render.index(form,alarm, session)

   def POST(self):
      global alarm, StationList
      form = self.getAlarmForm()()
      if not form.validates():
         return render.index(form,alarm, session)

      nextAlarm = alarm.getNextAlarm()
      alarmTime = ""

      if nextAlarm is not None:
         alarmTime = nextAlarm.strftime("%H%M")

      NewDefaultStation = StationList.index(form['station'].value)
      log.info("default station %s", StationList[NewDefaultStation])
      settings.set('default_station', NewDefaultStation)

      if form['time'].value <> alarmTime:
          alarmHour = int(form['time'].value[:2])
          alarmMin = int(form['time'].value[2:])
          time = datetime.datetime.now(pytz.timezone('Europe/London'))

          # So we don't set an alarm in the past
          if alarmHour < time.hour:
             time = time + datetime.timedelta(days=1)

          time = time.replace(hour=alarmHour, minute=alarmMin, microsecond=0, second=0)
          alarm.manualSetAlarm(time, NewDefaultStation)
      else:
          time = nextAlarm
      #~ StationList = []
      #~ for stationname in Settings.STATIONS:
            #~ StationList.append(stationname['name'])



      return render.confirmation("Setting alarm to %s at %s" % (StationList[NewDefaultStation], time) )

class reset:
   def GET(self):
      global alarm
      if userLoggedout(session):
        raise web.seeother('/signin')
      else:
          log.debug("Web request to reset alarm")
          alarm.autoSetAlarm()

          nextAlarm = alarm.getNextAlarm()
          alarmTime = "none"
          if nextAlarm is not None:
             alarmTime = nextAlarm.strftime("%c")

          return render.confirmation("Alarm has been auto-set to %s" % (alarmTime))

class set:
   def getForm(self):
      #~ global session

      return form.Form(
         form.Password("oldpassword",
            description="Existing Password",
            value="",
            size=10,
         ),
         form.Password("newpassword",
            description="New Password",
            value="",
            size=10,
         ),
         #~ form.Textbox("home",
            #~ form.notnull,
            #~ description="Home location",
            #~ value=settings.get('location_home'),
         #~ ),
         #~ form.Textbox("work",
            #~ form.notnull,
            #~ description="Work location",
            #~ value=settings.get('location_work'),
         #~ ),
         form.Textbox("weatherloc",
            form.notnull,
            description="Weather location",
            value=settings.get('weather_location'),
            size=10,
         ),
         form.Textbox("snooze",
            form.notnull,
            form.regexp('\d+', 'Must be a digit'),
            description="Snooze Length (minutes)",
            value=settings.getInt('snooze_length'),
            maxlength=10,
            size=10,
         ),
         form.Textbox("timeout",
            form.notnull,
            form.regexp('\d+', 'Must be a digit'),
            description="Alarm Timeout (mins)",
            value=settings.getInt('alarm_timeout'),
            maxlength=10,
            size=10,
         ),
         form.Textbox("menu_timeout",
            form.notnull,
            form.regexp('\d+', 'Must be a digit'),
            description="Menu Timeout (secs)",
            value=settings.getInt('menu_timeout'),
            maxlength=10,
            size=10,
         ),
         form.Textbox("precancel",
            form.notnull,
            form.regexp('\d+', 'Must be a digit'),
            description="Pre-empt cancel alarm allowed (secs)",
            value=settings.get('preempt_cancel'),
            maxlength=10,
            size=10,
         ),
         form.Textbox("waketime",
            form.notnull,
            form.regexp('[0-2][0-9][0-5][0-9]', 'Must be a 24hr time'),
            description="Holiday wakeup time",
            value=settings.get('default_wake'),
            maxlength=10,
            size=10,
         ),
         form.Checkbox("holidaymode",
            description="Away mode enabled",
            checked=(settings.getInt('holiday_mode')==1),
            value="holiday",
         ),
         form.Checkbox("weatheronalarm",
            description="Play weather after alarm",
            checked=(settings.getInt('weather_on_alarm')==1),
            value="weatheronalarm",
         ),
         form.Checkbox("sfx",
            description="SFX enabled",
            checked=(settings.getInt('sfx_enabled')==1),
             value="sfx",
         ),
         form.Checkbox("gradual_volume",
            description="Gradual Alarm Volume Increase",
            checked=(settings.getIntOrSet('gradual_volume','0')==1),
             value="gradual_volume",
         ),
         form.Textbox("ttspath",
            description="TTS path",
            value=settings.get('tts_path'),
            size=10,
         ),
      )

   def GET(self):
      #~ global session
      if userLoggedout(session):
        raise web.seeother('/signin')
      else:
          form = self.getForm()()
          return render.settings(form)

   def POST(self):
      global alarm, webcredential_path
      form = self.getForm()()
      if not form.validates():
         return render.settings(form)

      changes = []
      log.debug("Processing web request for settings changes")

      #if (PasswordHash(form['oldpassword'].value) == users[session.user]) and (form['newpassword'].value != ""):
      if (users[session.user].check_password(form['oldpassword'].value)) and (form['newpassword'].value != ""):
         changes.append("Changed user password")
         users[session.user] = PasswordHash(form['newpassword'].value)
         try:
            pickle.dump(users, open(webcredential_path, "wb" ) )
         except:
            log.debug("couldnt save user details")

      #~ if form['home'].value != settings.get('location_home'):
         #~ changes.append("Set Home location to %s" % (form['home'].value))
         #~ settings.set('location_home', form['home'].value)

      #~ if form['work'].value != settings.get('location_work'):
         #~ changes.append("Set Work location to %s" % (form['work'].value))
         #~ settings.set('location_work', form['work'].value)

      if form['weatherloc'].value != settings.get('weather_location'):
         changes.append("Set weather location to %s" % (form['weatherloc'].value))
         settings.set('weather_location', form['weatherloc'].value)

      if int(form['snooze'].value) != settings.getInt('snooze_length'):
         changes.append("Set snooze length to %s" % (form['snooze'].value))
         settings.set('snooze_length', form['snooze'].value)

      if int(form['menu_timeout'].value) != settings.getInt('menu_timeout'):
         changes.append("Set Menu Timeout to %s seconds" % (form['menu_timeout'].value))
         settings.set('menu_timeout', form['menu_timeout'].value)

      if int(form['timeout'].value) != settings.getInt('alarm_timeout'):
         changes.append("Set Alarm Timeout to %s minutes" % (form['timeout'].value))
         settings.set('alarm_timeout', form['timeout'].value)

      if int(form['precancel'].value) != settings.getInt('preempt_cancel'):
         changes.append("Set pre-emptive cancel time to %s seconds" % (form['precancel'].value))
         settings.set('preempt_cancel', form['precancel'].value)

      if form['waketime'].value != settings.get('default_wake'):
         changes.append("Set Holiday wake time to %s" % (form['waketime'].value))
         settings.set('default_wake', form['waketime'].value)

      if form['holidaymode'].checked != (settings.getInt('holiday_mode') == 1):
         changes.append("Setting Away mode to %s" % (form['holidaymode'].checked))
         settings.set('holiday_mode', 1 if form['holidaymode'].checked else 0)
         if(settings.getInt('holiday_mode')==1):
            # Just enabled holiday mode, so clear any alarms
            log.debug("Enabling holiday mode, clearing alarms")
            alarm.clearAlarm()
         else:
            # Just disabled holiday mode, so do an auto-setup
            log.debug("Disabling holiday mode, auto-setting alarm")
            alarm.autoSetAlarm()

      if form['weatheronalarm'].checked != (settings.getInt('weather_on_alarm') == 1):
         changes.append("Setting weather on alarm to %s" % (form['weatheronalarm'].checked))
         settings.set('weather_on_alarm', 1 if form['weatheronalarm'].checked else 0)

      if form['sfx'].checked != (settings.getInt('sfx_enabled') == 1):
         changes.append("Setting SFX to %s" % (form['sfx'].checked))
         settings.set('sfx_enabled', 1 if form['sfx'].checked else 0)

      if form['gradual_volume'].checked != (settings.getInt('gradual_volume') == 1):
         changes.append("Setting Gradual Alarm Volume Increase to %s" % (form['gradual_volume'].checked))
         settings.set('gradual_volume', 1 if form['gradual_volume'].checked else 0)

      if form['ttspath'].value != settings.get('tts_path'):
         changes.append("Setting TTS path to %s" % (form['ttspath'].value))
         if form['ttspath'].value == "":
            settings.set('tts_path', "/usr/bin/festival --tts")
         else:
            settings.set('tts_path', form['ttspath'].value)

      text = "Configuring settings:<p><ul><li>%s</li></ul>" % ("</li><li>".join(changes))
      # For debugging purposes
      for c in changes:
         log.debug(c)

      return render.confirmation(text)


class alarms:
   def getForm(self):
      global StationList

      #~ StationList = []
      #~ for stationname in Settings.STATIONS:
            #~ StationList.append(stationname['name'])

      #~ dopost = []
      #~ for dayno in range(0,7):
        #~ #  '</td>\n<td><label for="xalarm_station_' + str(dayno) + '"></label></td><td>' +
        #~ dopost.append(form.Dropdown('newalarm_station_' + str(dayno), args = StationList, value = StationList[int(settings.get('alarm_station_' + str(dayno)))]).render())

        #~ log.info(dopost[dayno])

      return form.Form(
        #~ Expliots HTML rendering and "feature" of Web.py forms to display text box and dropdown
        #~ on same table row by commenting out the end-of-row + beginning-of-next-row.

        form.Textbox('alarm_weekday_0', description="Monday", post=" <!-- " ,  value=settings.get('alarm_weekday_0'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_0', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_0'))]),

        form.Textbox('alarm_weekday_1', description="Tuesday", post=" <!-- " , value=settings.get('alarm_weekday_1'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_1', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_1'))]),

        form.Textbox('alarm_weekday_2', description="Wednesday", post=" <!-- ", value=settings.get('alarm_weekday_2'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_2', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_2'))]),

        form.Textbox('alarm_weekday_3', description="Thursday", post=" <!-- ", value=settings.get('alarm_weekday_3'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_3', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_3'))]),

        form.Textbox('alarm_weekday_4', description="Friday", post=" <!-- ", value=settings.get('alarm_weekday_4'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_4', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_4'))]),

        form.Textbox('alarm_weekday_5', description="Saturday", post=" <!-- ", value=settings.get('alarm_weekday_5'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_5', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_5'))]),

        form.Textbox('alarm_weekday_6', description="Sunday", post=" <!-- ", value=settings.get('alarm_weekday_6'), size="5", maxlength="5"),
        form.Dropdown('alarm_station_6', args = StationList, pre = " -->", description="", value = StationList[int(settings.get('alarm_station_6'))]),
      )

   def DailyAlamInfo(self,Dayno):
        AlarmTime = settings.get('alarm_weekday_' + Dayno)
        AlarmStation = int(settings.get('alarm_station_' + Dayno))
        AlarmHours = Gethoursselector('alarm_weekday_hours_' + Dayno, int(AlarmTime[:2]))
        AlarmMins  = Getminsselector('alarm_weekday_mins_' + Dayno , int(AlarmTime[3:]))
        AlarmStation = Getradioselector('alarm_station_'+ Dayno, StationList[int(settings.get('alarm_station_' + Dayno))])

        return AlarmHours, AlarmMins, AlarmStation


   def GET(self):
      #~ global session
      if userLoggedout(session):
        raise web.seeother('/signin')
      else:
          #~ form = self.getForm()()

          alarm_weekday_0 = self.DailyAlamInfo("0")
          alarm_weekday_1 = self.DailyAlamInfo("1")
          alarm_weekday_2 = self.DailyAlamInfo("2")
          alarm_weekday_3 = self.DailyAlamInfo("3")
          alarm_weekday_4 = self.DailyAlamInfo("4")
          alarm_weekday_5 = self.DailyAlamInfo("5")
          alarm_weekday_6 = self.DailyAlamInfo("6")

          return render.alarms(alarm_weekday_0,alarm_weekday_1,alarm_weekday_2,alarm_weekday_3,alarm_weekday_4,alarm_weekday_5,alarm_weekday_6,"")

   def POST(self):
      #~ global session, users
      global StationList
      form = self.getForm()()
      if not form.validates():
         alarm_weekday_0 = self.DailyAlamInfo("0")
         alarm_weekday_1 = self.DailyAlamInfo("1")
         alarm_weekday_2 = self.DailyAlamInfo("2")
         alarm_weekday_3 = self.DailyAlamInfo("3")
         alarm_weekday_4 = self.DailyAlamInfo("4")
         alarm_weekday_5 = self.DailyAlamInfo("5")
         alarm_weekday_6 = self.DailyAlamInfo("6")
         return render.alarms(alarm_weekday_0,alarm_weekday_1,alarm_weekday_2,alarm_weekday_3,alarm_weekday_4,alarm_weekday_5,alarm_weekday_6,"")

      changes = []
      log.debug("Processing web request for settings changes")

      #~ if form['home'].value != settings.get('location_home'):
         #~ changes.append("Set Home location to %s" % (form['home'].value))
         #~ settings.set('location_home', form['home'].value)

      #~ inputs = form.__dict__.get('inputs')
      #~ for x in inputs:
            #~ log.info("%s = %s", x.name, x.value)

      user_data = web.input()
      for x in user_data:
            log.info("%s = %s", x, user_data[x])

      #~ StationList = []
      #~ for stationname in Settings.STATIONS:
            #~ StationList.append(stationname['name'])


      daynames = [ "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
      for dayno in range(0,7):
          if user_data['alarm_weekday_hours_' + str(dayno)] + ":" + user_data['alarm_weekday_mins_' + str(dayno)] != settings.get('alarm_weekday_' + str(dayno)):
            newtime = user_data['alarm_weekday_hours_' + str(dayno)] + ":" + user_data['alarm_weekday_mins_' + str(dayno)]
            if (newtime[2]==":") and (len(newtime) == 5) and (newtime[:1].isdecimal()) and (newtime[3:].isdecimal()):
                changes.append("%s Alarm set to %s" % (daynames[dayno], newtime))
                settings.set('alarm_weekday_' + str(dayno), newtime)
          if StationList.index(user_data['alarm_station_' + str(dayno)]) != settings.getInt('alarm_station_' + str(dayno)):
            settings.set('alarm_station_' + str(dayno), user_data['alarm_station_' + str(dayno)])
            newstation = StationList[StationList.index(settings.getInt('alarm_station_' + str(dayno)))]
            changes.append("%s Station Set to %s" % (daynames[dayno], newstation))

      #~ daynames = [ "Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
      #~ for dayno in range(0,7):
          #~ if form['alarm_weekday_' + str(dayno)].value != settings.get('alarm_weekday_' + str(dayno)):
            #~ newtime = form['alarm_weekday_' + str(dayno)].value
            #~ if (newtime[2]==":") and (len(newtime) == 5) and (newtime[:1].isdecimal()) and (newtime[3:].isdecimal()):
                #~ changes.append("%s Alarm set to %s" % (daynames[dayno], newtime))
                #~ settings.set('alarm_weekday_' + str(dayno), newtime)
          #~ if StationList.index(form['alarm_station_' + str(dayno)].value) != settings.getInt('alarm_station_' + str(dayno)):
            #~ settings.set('alarm_station_' + str(dayno), form['alarm_station_' + str(dayno)].value)
            #~ newstation = StationList[StationList.index(settings.getInt('alarm_station_' + str(dayno)))]
            #~ changes.append("%s Station Set to %s" % (daynames[dayno], newstation))

      text = "Configuring alarms:<p><ul><li>%s</li></ul>" % ("</li><li>".join(changes))
      # For debugging purposes
      #~ for c in changes:
         #~ log.debug(c)

      alarm_weekday_0 = self.DailyAlamInfo("0")
      alarm_weekday_1 = self.DailyAlamInfo("1")
      alarm_weekday_2 = self.DailyAlamInfo("2")
      alarm_weekday_3 = self.DailyAlamInfo("3")
      alarm_weekday_4 = self.DailyAlamInfo("4")
      alarm_weekday_5 = self.DailyAlamInfo("5")
      alarm_weekday_6 = self.DailyAlamInfo("6")
      return render.alarms(alarm_weekday_0,alarm_weekday_1,alarm_weekday_2,alarm_weekday_3,alarm_weekday_4,alarm_weekday_5,alarm_weekday_6, text)
      #~ return render.confirmation(text)


class player:
   def getForm(self):
      #~ global session

      #~ StationList = []
      #~ for stationname in Settings.STATIONS:
            #~ StationList.append(stationname['name'])

      #~ if media.playerActive():
            #~ Status = "Playing"
      #~ else:
            #~ Status = "Silent"

      #~ playingStation = media.playerActiveStation()
      diyform = "<!-- -->"
      #~ diyform += '<TR><TD>Status</TD><TD>Station</TD></TR>\n'
      #~ diyform += '<TR><TD><span id="PlayerStatus">' + Status + '</span></TD>'
      #~ diyform += '<TD><span id="PlayerStation">' + playingStation + '</span></TD></TR>\n'
      #~ diyform += '<TR><TD colspan=2 align=center>New Station</TD></TR>\n'
      #~ diyform += '<TR><TD colspan=2 align=center>'
      #~ selector = '<select id="alarm_station" name="alarm_station">'
      #~ diyform += "</TD></TR>"
      #~ diyform += "<TR><TD>"

      #~ for stationname in Settings.STATIONS:
          #~ if stationname['name'] == playingStation:
            #~ selector += '<option selected value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'
          #~ else:
            #~ selector += '<option value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'

      #~ selector += '</select><P>'
      #~ diyform += '</TD></TR>\n'
      #~ diyform += '</table>\n'


      return diyform
      #~ form.Form(
        #~ Expliots HTML rendering and "feature" of Web.py forms to display text box and dropdown
        #~ on same table row by commenting out the end-of-row + beginning-of-next-row.

        #~ value=settings.get('alarm_weekday_0'),

        #~ form.Textbox('Status', description="Status", post="Unknown" ,  value=settings.get('alarm_weekday_0'), size="5", maxlength="5"),

        #~ form.Dropdown('alarm_station', args = StationList, pre = "Station ", description="", value = StationList[int(settings.get('alarm_station_0'))]),
        #~ form.Button("action",type="Action",value="Stop", html="Stop"),
        #~ form.Button("action",type="Action",value="Play", html="Play"),
        #~ form.Button("action",type="Action",value="Pause", html="Pause"),

      #~ )

   def GET(self):

        if userLoggedout(session):
            raise web.seeother('/signin')
        else:

            if media.playerActive():
                Status = "Playing"
            else:
                Status = "Stopped"

            playingStation = media.playerActiveStation()

            #~ selector = '<select id="current_station" name="current_station">'
            #~ selectorAlarmStation = '<select id="alarm_station" name="alarm_station">'

            selector = Getradioselector("current_station",playingStation)
            selectorAlarmStation = Getradioselector("alarm_station","")
            #~ for stationname in Settings.STATIONS:
                #~ if stationname['name'] == playingStation:
                    #~ selector += '<option selected value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'
                #~ else:
                    #~ selector += '<option value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'
                #~ selectorAlarmStation += '<option value="' + stationname['name'] +'">' + stationname['name'] +'</option>\n'

            #~ selector += '</select>'
            #~ selectorAlarmStation += '</select>'

            hoursselector = Gethoursselector("selecthours","") #'<select id="selecthours" name="current_hours">'
            #~ for hour in range(0 , 24):
                #~ hoursselector += '<option value="' + str(100+hour)[-2:] +'">' + str(100+hour)[-2:] +'</option>\n'
            #~ hoursselector += '</select>'

            minsselector = Getminsselector("selectminutes","") #'<select id="selectminutes" name="current_minutes">'
            #~ for minute in range(0 , 60):
                #~ minsselector += '<option value="' + str(minute) +'">' + str(minute) +'</option>\n'
            #~ minsselector += '</select>'

            #~ form = self.getForm()#()
            return render.player(selector, selectorAlarmStation, hoursselector, minsselector) #form,selector,Status, playingStation, MainLoop.getBrightnessTweak())



class logout:
    def GET(self):
        #~ global session
        try:
            session.user = ""
            session.kill()
        except:
            log.debug("failed to close session")
        raise web.seeother('/signin')

class signin:
    def getForm(self):
        #~ global session, users
        # Commented 1st validator so we dont indicate valid usernames


        return form.Form(form.Textbox('username',
            #~ form.Validator("Username and password didn't match.",
                #~ lambda x: x in users.keys()),
                description='Username:'),
            form.Password('password',
                description='Password:'),
            validators = [form.Validator("Username and password didn't match.",
                lambda x: users[x.username].check_password(x.password)) ]
                )


    def GET(self):
        #~ global session
        #~ log.debug("signin")
        my_signin = self.getForm()()
        return render_nomenu.signin(GetUser(session), my_signin)

    def POST(self):
        #~ global session, users
        global webcredential_path
        my_signin = self.getForm()()


        if not my_signin.validates():
            if len(users) == 0: # if no users, then add the current user+passowrd
                username = my_signin['username'].value
                password = my_signin['password'].value
                log.debug("new user %s, %s", username, password)
                users[username] = PasswordHash(password)
                #~ users = {my_signin['username'].value: PasswordHash(my_signin['password'].value)}
                log.debug("create user info")
                pickle.dump(users, open(webcredential_path, "wb" ) )
            return render_nomenu.signin(GetUser(session), my_signin)
        else:
            session.user = my_signin['username'].value
            web.seeother('/home')
            #~ return render.signin(GetUser(session), my_signin)

class api: # returns json describing the Player State
    def GET(self):
        global StationList, iplist
        RequesterIP = web.ctx['ip']
        #~ log.info("%s=%s" %(RequesterIP, iplist[0]))
        #~ if (iplist.index(RequesterIP) == -1 ):
        if (RequesterIP not in iplist):
            if (userLoggedout(session)) :
                log.info("Not logged in")
                return ("")


        user_data = web.input(action="None",value="")
        ApiAction = user_data.action
        ApiValue = user_data.value

        #~ log.debug("API Action = %s " , ApiAction)


        if media.playerActive():
            iStatus = 1
            if media.playerPaused():
                iStatus = 2
        else:
            iStatus = 0

        if   (ApiAction == "play"): # or (ApiAction == "play" and ApiAction == "radio"):
            #~ StationList = []
            #~ for stationname in Settings.STATIONS:
                #~ StationList.append(stationname['name'])

            newstation = StationList[StationList.index(ApiValue)]
            if (iStatus == 0) or (media.playerActiveStation() <> newstation):
                # Need to stop the alarm or it will retrigger
                if alarm.isAlarmSounding():
                    alarm.stopAlarm()
                elif (iStatus == 1): # if playing something, but not an alarm
                    media.stopPlayer()

                #~ log.info("Playing : " + newstation)
                media.playStation(StationList.index(ApiValue))

        elif ApiAction == "stop":
            if (iStatus == 1) or (iStatus == 2):
                media.stopPlayer()

        elif ApiAction == "pause":
            if (iStatus <> 0):
                log.info("Pausing")
                media.pausePlayer()

        elif ApiAction == "brighter":
            brightnessthread.setBrightnessTweak(brightnessthread.getBrightnessTweak() + 3)
        elif ApiAction == "dimmer":
            brightnessthread.setBrightnessTweak(brightnessthread.getBrightnessTweak() -3)

        elif ApiAction == "brightnesschange":
            NewTweak = brightnessthread.getBrightnessTweak() + int(ApiValue)
            if (NewTweak > 100):
                    NewTweak = 100
            if (NewTweak < 0):
                    NewTweak = 0
            log.info("tweak = %d", NewTweak)
            brightnessthread.setBrightnessTweak(NewTweak)
            #~ elif (settings.getInt('brightness_tweak') <100) and (Change > 0):
            #~ MainLoop.setBrightnessTweak(MainLoop.getBrightnessTweak() -Change)

        elif ApiAction == "volumechange":
            NewVolume = settings.getInt('volume') + int(ApiValue)

            if (NewVolume > 100):
                NewVolume = 100
            elif (NewVolume < 0):
                NewVolume = 0

            settings.set('volume',NewVolume)

        elif (ApiAction == "cancelalarm") or ((ApiAction == "off") and( ApiValue == "alarm")):
            alarm.stopAlarm()

        elif ApiAction == "snoozealarm":
            alarm.snooze()

        #~ elif ApiAction == "SetAlarmStation":
            #~ AlarmStation = ApiValue
            #~ NewAlarmStation = StationList.index(ApiValue)
            #~ if settings.get('default_station') <> NewAlarmStation:
                #~ settings.set('default_station', NewAlarmStation)
                #~ alarm.manualSetAlarm(alarm.getNextAlarm(), NewAlarmStation)

        elif ApiAction == "SetAlarmInfo":

            CurrentAlarmStation = alarm.nextAlarmStation
            NewAlarmStation = StationList.index(ApiValue)

            # need the extra info
            ApiValue = user_data.extravalue
            if ApiValue[2] == ":": # HH:MM becomes HHMM
                ApiValue = ApiValue[:2] + ApiValue[3:]

            nextAlarm = alarm.getNextAlarm()
            alarmTime = ""

            if nextAlarm is not None:
                alarmTime = nextAlarm.strftime("%H%M")

            if ApiValue <> alarmTime:
                alarmHour = int(ApiValue[:2])
                alarmMin = int(ApiValue[2:])
                time = datetime.datetime.today() #(pytz.timezone('Europe/London'))

                # So we don't set an alarm in the past
                if alarmHour < time.hour:
                    time = time + datetime.timedelta(days=1)

                time = time.replace(hour=alarmHour, minute=alarmMin, microsecond=0, second=0)
                if CurrentAlarmStation <> NewAlarmStation:
                    CurrentAlarmStation = NewAlarmStation
                alarm.manualSetAlarm(time, CurrentAlarmStation)

            elif CurrentAlarmStation <> NewAlarmStation:
                CurrentAlarmStation = NewAlarmStation
                alarm.manualSetAlarm(nextAlarm, CurrentAlarmStation)


        elif ApiAction == "off":
            if ApiAction == "volume":
                NewVolume = settings.getInt('volume') - int(1)

                if (NewVolume > 100):
                    NewVolume = 100
                elif (NewVolume < 0):
                    NewVolume = 0
                settings.set('volume',NewVolume)

        elif ApiAction == "on":
            if ApiAction == "volume":
                NewVolume = settings.getInt('volume') + int(1)

                if (NewVolume > 100):
                    NewVolume = 100
                elif (NewVolume < 0):
                    NewVolume = 0
                settings.set('volume',NewVolume)

        elif ApiAction <> "status":
            log.debug("unknown api %s", ApiAction)
            return ("")

        # Return Current Status
        CurrentStation = media.playerActiveStation()
        if media.playerActive():
            iStatus = 1
            if media.playerPaused():
                iStatus = 2
                CurrentStation += " (Paused)"
        else:
            iStatus = 0

        if alarm.nextAlarmStation != None:
            AlarmStation = StationList[alarm.nextAlarmStation]
        else:
            AlarmStation = "None"
        AlarmTime = alarm.getNextAlarm()
        # AlarmState - bit 0 = 1 - Sounding
        #              bit 1 = 1 - Automatic
        AlarmState = 0
        if AlarmTime != None:
            AlarmTime = AlarmTime.time().strftime('%H:%M')

            if alarm.isAlarmSounding():
                AlarmState += 1

            if settings.get('manual_alarm') == '':
                NextAlarmType = "Automatic"
                AlarmState += 2
            else:
                NextAlarmType = "Manual"
        else:
            AlarmTime = "XX:XX"
            NextAlarmType = "None"


        Statusjson = { 'Status': PlayerStatus[iStatus], 'Station': CurrentStation, 'Brightness' : brightnessthread.getBrightnessTweak(),
            'Volume' : settings.getInt('volume'), 'AlarmState': AlarmState, 'AlarmTIme':AlarmTime, 'AlarmStation':AlarmStation, 'NextAlarmType' : NextAlarmType}

        web.header('Content-Type','application/json')
        return json.dumps(Statusjson)


class WebApplication(threading.Thread):
   def __init__(self, alarmThread, Settingsthread, Media, Caller, brightnessthreadptr):
      global alarm, users, settings, media, MainLoop, brightnessthread, webcredential_path, iplist
      threading.Thread.__init__(self)
      alarm = alarmThread
      brightnessthread = brightnessthreadptr
      settings = Settingsthread
      media = Media
      MainLoop = Caller

      if os.path.isfile(webcredential_path):
          #~ log.debug("getting webcredentials")
          log.info("loading user info")
          users = pickle.load( open(webcredential_path, "rb" ) )


      iplist = []
      NetworksIP = GetIPForNetwork("eth0")
      if (NetworksIP != ""):
        log.info("Have LAN Connection")
        iplist.append(NetworksIP)

      NetworksIP = GetIPForNetwork("wlan0")
      if (NetworksIP != ""):
        log.info("Have Wifi Connection")
        iplist.append(NetworksIP)

      #~ self.session = None


   def run(self):
      #~ global session
      log.debug("Starting up web server")

      home_dir = os.path.expanduser('~')

      #  openssl req -new -x509 -keyout serverssl.pem -out serverssl.pem -days 365 -nodes
      CherryPyWSGIServer.ssl_certificate = os.path.join(home_dir, "serverssl.pem")
      CherryPyWSGIServer.ssl_private_key = os.path.join(home_dir, "serverssl.pem")

      #~ self.app = web.application(urls, globals())
      #~ if web.config.get('_session') is None:
        #~ log.debug("reading session from disk")
        #~ self.session = web.session.Session(self.app, web.session.DiskStore('sessions'),
                              #~ initializer={'user': ''})
        #~ web.config._session = self.session
      #~ else:
        #~ self.session = web.config._session

      web.config.debug = False
      #~ web.config.log_file = "WebServer.log"
      #~ web.config.log_toprint = False
      #~ web.config.log_tofile = True

      #~ self.app.internalerror = web.debugerror
      web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", 443))
      log.debug("Web server has stopped")

   def stop(self):
      #~ global users
      log.debug("Shutting down web server")
      #~ only do this when things have changed now
      #~ pickle.dump(users, open(webcredential_path, "wb" ) )
      app.stop()

