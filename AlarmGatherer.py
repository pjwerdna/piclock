import gflags
import httplib2
import datetime
import pytz
import dateutil.parser
import logging
import os
import pickle

# Updates
# 13/08/2020 - MInor change to even cache timeout message
# 12/10/2020 - Shows Start and End time for Google Events

#from apiclient.discovery import build
#from oauth2client.file import Storage
#from oauth2client.client import OAuth2WebServerFlow
#from oauth2client.tools import run

# from google's example
#
from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage

import Settings

log = logging.getLogger('root')

flags = None

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/calendar-python.json
SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'Google PiCock'

#~ try:
    #~ import argparse
    #~ flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
#~ except ImportError:
    #~ flags = None

def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.getcwd() #os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'calendar-python.json')
    log.info("credential_path=%s", credential_path)

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        #if flags:
        credentials = tools.run_flow(flow, store, flags)
        #else: # Needed only for compatibility with Python 2.6
        #   credentials = tools.run(flow, store)
        log.info("Storing credentials to %s",  credential_path)
    return credentials

class AlarmGatherer:
   def __init__(self, Mediaplayer):

      self.settings = Settings.Settings()

      self.credentials = get_credentials()
      self.media = Mediaplayer

      # Cache for events from Google calendar
      self.getNextEventTimeout = None
      self.eventCache = None

      try:
        if os.path.isfile('calender.cache'):
            self.eventCache = pickle.load( open( 'calender.cache', "rb" ) )

            # start with the time from the file
            timeout = datetime.datetime.fromtimestamp(os.path.getmtime('calender.cache'))
            timeout += datetime.timedelta(hours=4) # Don't keep the cache for too long, just long enough to avoid request spam
            self.getNextEventTimeout = timeout
            log.info("Using Calender cache from file. Timeout at %s", timeout)


      except:
        log.exception("Failed to load Calender cache")
        self.eventCache = None
        self.getNextEventTimeout = None


   def checkCredentials(self):
      return not (self.credentials is None or self.credentials.invalid == True)

   def generateAuth(self):
      self.credentials = run(self.FLOW, self.storage)

   # Get the first event that isn't today
   def getNextEvent(self, today=False):
      """Gets Next event from google or the cache

         Should cope with no events being cached, but not really tested that

      Returns:
        None or first event
      """
      log.debug("Fetching details of next event")
      if not self.checkCredentials():
         log.error("GCal credentials have expired")
         log.warn("Remove credentials\calendar-python.json and run 'python AlarmGatherer.py' to fix")
         self.media.playVoice('Google Calendar credentials have expired')
         raise Exception("GCal credentials not authorized")

      time = datetime.datetime.utcnow() #.isoformat(); + 'Z' # 'Z' indicates UTC time
      #time = datetime.datetime.now()

      # No event cache or cache has timed out
      if (self.getNextEventTimeout == None) or (len(self.eventCache) == 0) or (datetime.datetime.now() > self.getNextEventTimeout):
            http = self.credentials.authorize(httplib2.Http())
            try:
                service = discovery.build('calendar', 'v3', http=http)
            except Exception as e:
                log.debug("Failed to build calendar credentials")

            if not today:
                # We want to find events tomorrow, rather than another one today
                log.debug("Skipping events from today")
                time += datetime.timedelta(days=1) # Move to tomorrow
                time = time.replace(hour=10,minute=0,second=0,microsecond=0) # Reset to 10am the next day
                # 10am is late enough that a night shift from today won't be caught, but a morning shift
                #  from tomorrow will be caught

                log.debug('Getting next 2 events for %s', time)

                # Trap network errors etc
            try:
            #if (True):
                eventsResult = service.events().list(
                    calendarId='primary', timeMin="%sZ" % (time.isoformat()),
                    maxResults=2, singleEvents=True,
                    orderBy='startTime').execute()
                events = eventsResult.get('items', [])

                self.eventCache = events

                log.debug("Creating Calender Cache file")
                pickle.dump(events, open( 'calender.cache', "wb" ) )

            except Exception as e:
            #if (False):
                log.exception("Could not Get Next Event. Using last result")
                events = self.eventCache

            finally: # Always need to update the timeout
            #if (True):
                self.getNextEventTimeout = datetime.datetime.now() + datetime.timedelta(hours=4)

      else:
        log.debug("Using event cache")
        events = self.eventCache

      # when no events are available
      if len(events) == 0:
          events = None
          log.debug("no events returned")
      else:
          try:
              for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                finish = event['end'].get('dateTime', event['end'].get('date'))
                log.debug("%s to %s is '%s'", start, finish, event['summary'])
          except Exception as e:
              log.debug("failed displaying alarm info")
              events = None

          #~ self.getNextEventTimeout = datetime.datetime.now() + datetime.timedelta(hours=1)
          log.debug("Next Event cache timeout %s", self.getNextEventTimeout)

      if events == None:
        return None
      else:
        return events[0]

   def getNextEventTime(self, includeToday=False):
      log.debug("Fetching next event time (including today=%s)" % (includeToday))
      nextEvent = self.getNextEvent(today=includeToday)
      #start = dateutil.parser.parse(nextEvent['start']['dateTime'])
      start = dateutil.parser.parse(nextEvent['start'].get('dateTime', nextEvent['start'].get('date')))
      #start = dateutil.parser.parse(nextEvent['start']['dateTime'],ignoretz=True)
      #start = start.replace(tzinfo=pytz.timezone('Europe/London'))

      return start

   def getNextEventAttribute(self, attribute = "summary", includeToday=False):
      log.debug("Fetching next event %s (including today=%s)" % (attribute, includeToday))
      nextEvent = self.getNextEvent(today=includeToday)
      try:
        if(nextEvent[attribute]):
            return nextEvent[attribute]
      except:
            return None

      return None

   def getNextEventDetails(self, includeToday=False):
      log.debug("Fetching next event time (including today=%s)" % (includeToday))
      nextEvent = self.getNextEvent(today=includeToday)
      return nextEvent

   def getNextEventLocation(self, includeToday=False):
      log.debug("Fetching next event location (including today=%s)" % (includeToday))
      nextEvent = self.getNextEvent(today=includeToday)
      try:
        if(nextEvent['location']):
            return nextEvent['location']
      except:
            return None

      return None

   def getDefaultAlarmTime(self):
      defaultTime = self.settings.get('default_wake')
      defaultHour = int(defaultTime[:2])
      defaultMin = int(defaultTime[2:])

      alarm = datetime.datetime.now(pytz.timezone('Europe/London'))
      alarm += datetime.timedelta(days=1) # Move to tomorrow
      alarm = alarm.replace(hour=defaultHour,minute=defaultMin,second=0,microsecond=0)

      return alarm


if __name__ == '__main__':
   print "Running credential check"

   #try:
   import argparse
   flags = argparse.ArgumentParser(parents=[tools.argparser]).parse_args()
   #except ImportError:
   #     flags = None
   a = get_credentials()
   try:
      if not a.checkCredentials():
         raise Exception("Credential check failed")
   except:
      print "Credentials not correct, please generate new code"
      a.generateAuth()
      a = AlarmGatherer()

   print a.getNextEventTime()
   print a.getNextEventLocation()
