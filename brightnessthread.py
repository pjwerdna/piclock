import time
import threading
from tsl2561 import TSL2561
#import Settings
#~ import RPi.GPIO as GPIO
#~ from RPIO import PWM
import logging
import math

import pigpio

LogBrightenss = False

log = logging.getLogger('root')

MINLOOP_TIME = float(0.25)
MAXLOOP_TIME = float(4)

class BrightnessThread(threading.Thread):

   def __init__(self,Settings):
      threading.Thread.__init__(self)
      #self.controlObjects = []
      self.stopping = False

      self.sensor = TSL2561(debug=False,autogain=True)
      #~ self.sensor.set_gain(1)

      self.settings = Settings #.Settings()

      self.manualTimeout = 0
      self.BrightnessTweak = self.settings.getIntOrSet('brightness_tweak',0)
      if (self.BrightnessTweak < 0) or (self.BrightnessTweak > 120):
          self.BrightnessTweak = 50
          self.settings.getIntOrSet('brightness_tweak',self.BrightnessTweak)

      self.currentLevel = 100 #+ self.BrightnessTweak

      self.readings = [15]*10 # average over the last 10 readings

      # Turn on brightness PWM
      self.pwmtftbrightness = pigpio.pi()
      self.pwmtftbrightness.set_PWM_range(18,400)
      self.pwmtftbrightness.set_PWM_frequency(18,400)
      self.pwmtftbrightness.set_PWM_dutycycle(18,8)
      self.pwmscale = 4.0

      #~ log.debug('Frequency %d', self.pwmtftbrightness.get_PWM_frequency(18))

      #~ GPIO.setmode(GPIO.BCM)
      #~ GPIO.setup(18,GPIO.OUT)
      #~ self.pwmtftbrightness = GPIO.PWM(18,70)
      #~ self.pwmtftbrightness.start(self.currentLevel)


   #def registerControlObject(self,object):
   #   self.controlObjects.append(object)

   def stop(self):
      self.stopping=True

   def maxBrightness(self):  # Must Disable brightnessTweak
      self.setBrightness(self.settings.getInt('max_brightness'), AllowTweak = False)

   def setBrightness(self, level, AllowTweak = True):
      self.manualTimeout = self.settings.getInt('brightness_timeout') * (1/MINLOOP_TIME)
      if (level > 100):
          level = 100
      if (level < 1):
          level = 1
      self.currentLevel = level
      self.updateBrightness(AllowTweak)

   def setBrightnessTweak(self, level):
       if level > 99:
           level = 99
       elif level < 0:
           level = 0
       self.BrightnessTweak = level
       self.settings.set('brightness_tweak',level)
       self.updateBrightness()

   def getBrightnessTweak(self):
       return self.BrightnessTweak

   def updateBrightness(self, AllowTweak = True): # With or without Manual Tweak
        if self.currentLevel < 1:
            self.currentLevel = 1
        elif self.currentLevel > 100:
            self.currentLevel = 100

        if AllowTweak:
            #~ if self.BrightnessTweak > 0:
                TheTweak = self.BrightnessTweak
                #~ TheTweak = math.log10(float(self.BrightnessTweak))*49.5
                if LogBrightenss:
                    log.info("log tweak = %f", (50-TheTweak))
                #~ newpwm = int((self.currentLevel-(TheTweak/4))*4.0)
                newpwm = int((self.currentLevel*self.pwmscale)+(50-TheTweak))
            #~ else:
                #~ newpwm = int(self.currentLevel*self.pwmscale)
        else:
            newpwm = int(self.currentLevel*self.pwmscale)
        if newpwm < 4:
            newpwm = 4
        elif newpwm > 255:
            newpwm = 255
        #~ log.debug("self.BrightnessTweak %d" , self.BrightnessTweak)
        self.pwmtftbrightness.set_PWM_dutycycle(18, newpwm-1)

        #~ log.info("duty cycle %d", self.pwmtftbrightness.get_PWM_dutycycle(18))

        #self.pwmtftbrightness.ChangeDutyCycle(self.currentLevel)
        if LogBrightenss:
            log.debug("pwm brightness %d", newpwm)
        #~ for obj in self.controlObjects:
        #~ obj.setBrightness(self.currentLevel)

   def run(self):
      maxBright = self.settings.getInt('max_brightness')
      minBright = self.settings.getInt('min_brightness')

      LoopTime = MAXLOOP_TIME
      while(not self.stopping):
         time.sleep(LoopTime)

         # We set the brightness manually, so just count down until we can resume auto-brightness
         if(self.manualTimeout > 0):
            self.manualTimeout = self.manualTimeout - 1
            continue

         #~ reading, IRreading = self.sensor._get_luminosity()
         reading= self.sensor.lux()
         scaledreading = float(reading) /2.8 # (was 7.0)

         #~ reading = float(100) # + self.BrightnessTweak)

         if(scaledreading > 100):
            scaledreading = float(100) # Seems like a sensible max for the IR sensor, can go into the 10's of thousands
         elif (scaledreading < 2):
            scaledreading = float(2)

         percentage = scaledreading/float(100)
         newLevel = percentage * float(maxBright)

         if(newLevel > maxBright):
            newLevel = float(maxBright)
         if(newLevel < minBright):
            newLevel = float(minBright)

         self.readings.pop(0)
         self.readings.append(newLevel)

         avgLevel = float( sum(self.readings) / float(len(self.readings)) )

         levelDiff = abs(self.currentLevel - avgLevel)

         #~ print "Reading: %s, Percentage: %s, NewLevel: %s, AvgLevel: %s, Diff: %s" % (reading,percentage,newLevel,avgLevel,levelDiff)

         if(levelDiff>=1):
            if LogBrightenss:
                log.debug( "Reading: %s, Percentage: %s, NewLevel: %s, AvgLevel: %s, Diff: %s" % (reading,percentage,newLevel,avgLevel,levelDiff))
            #~ log.debug("lux %s", self.sensor._calculate_lux(reading, IRreading))
            #~ print "Updating brightness to %s" % (avgLevel)
            self.currentLevel=avgLevel
            self.updateBrightness()
            if(levelDiff >= 2):
                LoopTime = MINLOOP_TIME
            else:
                LoopTime = MAXLOOP_TIME

      self.maxBrightness()

      # Turn off brightness PWM
      self.pwmtftbrightness.stop()
      #GPIO.cleanup()
      #PWM.cleanup()


