import datetime
import pytz
import urllib2
import Settings
import logging
import requests
import CalendarCredentials
import json
import os
import time

log = logging.getLogger('root')

# Fetches weather information
class WeatherFetcher:
   def __init__(self):
      self.cacheTimeout = None
      self.cache = None
      self.settings = Settings.Settings()
      self.jsoncache= None
      self.jsoncacheTimeout = None

      try:
        cachefile = open('weather.cache.json','r')
        self.jsoncache = json.load(cachefile)
        cachefile.close()

        attempt = self.jsoncache
        #~ for iindex, iitem in enumerate(attempt['response']['results'][0]):
            #~ print iindex , " = " , iitem

        #~ print attempt['response']['results'][0]['zmw']

        # start with the time from the file
        timeout = datetime.datetime.fromtimestamp(os.path.getmtime('weather.cache.json'))
        timeout += datetime.timedelta(minutes=30) # Don't keep the cache for too long, just long enough to avoid request spam
        self.jsoncacheTimeout = timeout
        log.info("Using cache from file. Timeout at %s", timeout)
        #~ cachefile = open('weather.cache.json.txt','w')
        #~ json.dump(self.jsoncache,cachefile,skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True, cls=None, indent=4)
        #~ cachefile.close()

      except:
        log.exception("Failed to load weather cache")
        self.jsoncache = None
        self.jsoncacheTimeout = None

   def getWeather(self):
      if(self.cache is None or self.cacheTimeout is None or self.cacheTimeout < datetime.datetime.now(pytz.timezone('Europe/London'))):
         weather = Weather()

         #~ if (self.jsoncacheTimeout > datetime.datetime.now(pytz.timezone('Europe/London'))):
             #~ log.info("jason cache %s > %s", self.jsoncacheTimeout, datetime.datetime.now(pytz.timezone('Europe/London')))

         if (self.jsoncache != None) and (self.jsoncacheTimeout > datetime.datetime.now()):
             log.info("Reusing json Weather cache")
             log.debug("%s > %s", self.jsoncacheTimeout, datetime.datetime.now())
             response = self.jsoncache
         else:
            log.info("Weather cache expired or doesn't exist, re-fetching")
            try:
                log.debug("Making request to wunderground")

                place = self.settings.get('weather_location')
                if(place is None or place is ""):
                    place = "London" # Default to Gatwick

                log.debug('http://api.wunderground.com/api/%s/forecast/q/UK/%s.json' % (CalendarCredentials.WUG_KEY, place))
                response = requests.get('http://api.wunderground.com/api/%s/forecast/q/UK/%s.json' % (CalendarCredentials.WUG_KEY, place), timeout=3)
                log.debug("Completed request to wunderground")

                #~ cachefile = open('weather.cache2.txt','w')
                #~ cachefile.write(response.text)
                #~ cachefile.close()

                response = response.json()
                log.debug("Parsed response")

                # find forecast
                hasforecast = False
                for itemid in response:
                    if itemid == 'forecast':
                        hasforecast = True

                #~ for iindex, iitem in enumerate(response['response']['results'][0]['zmw']):
                    #~ print iindex , " = " , iitem



                if hasforecast == True:
                    log,info("has forecast")
                    attempt = response['forecast'] # So we get a KeyError thrown if the response isn't correct
                    self.jsoncache = response
                else:
                    log.info("Weather has no forecast, trying redirected location")
                    cachefile = open('weather.cache.json.txt','w')
                    json.dump(response,cachefile)
                    cachefile.close()
                    # ['response']['results'][0]['zmw']
                    sNewLocation = response['response']['results'][0]['zmw']
                    log.debug('http://api.wunderground.com/api/%s/forecast/q/zmw:%s.json' % (CalendarCredentials.WUG_KEY, sNewLocation))
                    response = requests.get('http://api.wunderground.com/api/%s/forecast/q/zmw:%s.json' % (CalendarCredentials.WUG_KEY, sNewLocation), timeout=3)

                    response = response.json()
                    log.debug("Parsed response")

                    #~ for iindex, iitem in enumerate(response):
                        #~ print iindex , " = " , iitem

                    try:
                        attempt = response['forecast'] # So we get a KeyError thrown if the response isn't correct
                        self.jsoncache = response
                    except:
                        log.exception("Weather has no forecast")

                log.debug("writing weather to local cache")
                cachefile = open('weather.cache.json','w')
                json.dump(response,cachefile)
                cachefile.close()

                # Update cache timeout to avoid repeatedly spamming requests (see https://github.com/mattdy/alarmpi/issues/2)
                timeout = datetime.datetime.fromtimestamp(os.path.getmtime('weather.cache.json'))
                timeout += datetime.timedelta(minutes=60) # Don't keep the cache for too long, just long enough to avoid request spam
                self.jsoncacheTimeout = timeout

                timeout = datetime.datetime.now(pytz.timezone('Europe/London'))
                timeout += datetime.timedelta(minutes=60) # Don't keep the cache for too long, just long enough to avoid request spam
                self.cacheTimeout = timeout




            except:
                log.exception("Error fetching weather")

                self.jsoncache = None
                self.cacheTimeout = None


            #~ if(self.cache is not None):
               #~ return self.cache # we have a cache, so return that rather than an empty object
            #~ else:
               #~ return weather # return empty Weather object as we have nothing else

         log.info("extracting weather")

         try:
             Today_simple = response['forecast']["simpleforecast"]["forecastday"][0]
             Today = response['forecast']["txt_forecast"]["forecastday"][0]

             weather.setTempC(Today_simple["high"]["celsius"])
             #weather.setCondition(response['forecast'][0].get("fcttext").replace("intensity ",""))
             weather.setCondition(Today["fcttext_metric"])
             weather.setWindSpeedKts(Today_simple["maxwind"]["mph"])
             weather.setWindDirection(Today_simple["maxwind"]["dir"])
             weather.setPressure(Today_simple["qpf_allday"]["in"])
             #~ timeout = datetime.datetime.now(pytz.timezone('Europe/London'))
             #~ timeout += datetime.timedelta(minutes=30) # Cache for 30 minutes
             #~ self.cacheTimeout = timeout
             #~ self.jsoncacheTimeout = timeout

             #log.debug("Generated weather: %s" % (weather))
         except:
             log.exception("Error Decoding weather")

             weather = None
             self.cacheTimeout = None


         self.cache = weather

      return self.cache

   def forceUpdate(self):
      self.cacheTimeout = None

# Take a number or string, and put spaces between each character, replacing 0 for the word zero
def splitNumber(num):
   split = ' '.join("%s" % num)
   return split.replace("0","zero")

# Holds our weather information
class Weather:
   def __init__(self):
      self.temp = 0
      self.condition = ""
      self.wspeed = 0
      self.wdir = 0
      self.pressure = 0

   def setTempK(self,temperature):
      self.temp = int(int(temperature) - 273.15)

   def setTempC(self,temperature):
      self.temp = int(temperature)

   def setCondition(self,condition):
      self.condition = condition

   def setWindSpeedMps(self,wspeed):
      self.wspeed = int(int(wspeed) * 1.9438444924406)

   def setWindSpeedKts(self,wspeed):
      self.wspeed = wspeed

   def setWindDirection(self,wdir):
      #~ if wdir==0:
         #~ wdir = 360
      self.wdir = wdir

   def setPressure(self,pressure):
      if pressure != None:
          self.pressure = int(pressure)
      else:
          self.pressure = 0

   def display(self):
      #return "%sC, %03d@%s, %shPa %s" % (self.temp, self.wdir, self.wspeed, self.pressure, self.condition)
      return "Temperature %sC, Wind %03d@%s, %s" % (self.temp, self.wdir, self.wspeed, self.condition)

   def speech(self):
      speech = ""
      speech += "The weather is currently %s. " % (self.condition)
      speech += "Temperature %s degrees, " % (self.temp)
      #~ speech += "wind %s at %s m p h" % (splitNumber(self.wdir), self.wspeed)
      speech += "wind %s at %s miles per hour" % (self.wdir, self.wspeed)
      #speech += ", Q N H %s hectopascals" % (splitNumber(self.pressure))

      return speech

   def __str__(self):
      return "Weather[temp=%s,wdir=%s,wspeed=%s,press=%s,cond='%s']" % (self.temp, self.wdir, self.wspeed, self.pressure, self.condition)
