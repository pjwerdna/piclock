import time
import threading
from tsl2561 import TSL2561
#import Settings
#~ import RPi.GPIO as GPIO
#~ from RPIO import PWM
import logging
import math

import pigpio

# 31/03/???? - Tweaked brightness up at higher lumin levels
# 20/09/2021 - Publish brightness in Lux to mqtt (piclock_out/display/lux)

LogBrightness = False

log = logging.getLogger('root')

MINLOOP_TIME = float(0.25)
MAXLOOP_TIME = float(1)
# For percentage change which doesnt work
# LuxChangePercent = 2
minLuxChange = 2

class BrightnessThread(threading.Thread):

    def __init__(self,Settings, mqtt):
      threading.Thread.__init__(self)
      #self.controlObjects = []
      self.stopping = False

      self.sensor = TSL2561(debug=False,autogain=True)
      #self.sensor.set_integration_time)1)
      #self.sensor.set_gain(1)
      #~ self.sensor.set_gain(1)

      self.settings = Settings #.Settings()

      self.manualTimeout = 0
      self.BrightnessTweak = self.settings.getIntOrSet('brightness_tweak',0)
      if (self.BrightnessTweak < 0) or (self.BrightnessTweak > 120):
          self.BrightnessTweak = 50
          self.settings.getIntOrSet('brightness_tweak',self.BrightnessTweak)

      self.currentLevel = 100 #+ self.BrightnessTweak
      self.currentluxLevel = 0

      #self.readings = [15]*10 # average over the last 10 readings
      self.LuxReadings = [15]*10 # average over the last 10 Lux readings

      # Turn on brightness PWM
      self.pwmtftbrightness = pigpio.pi()
      self.pwmtftbrightness.set_PWM_range(18,300) #400
      self.pwmtftbrightness.set_PWM_frequency(18,2000) #400
      self.pwmtftbrightness.set_PWM_dutycycle(18,8)
      self.pwmscale = 4.2
      self.lastreading = -1
      self.mqtt = mqtt
      self.forceUpdate  = False
      self.autoLux = self.settings.getIntOrSet("display_autolux",1)
      self.minLux = self.settings.getIntOrSet("display_minLux",2000)
      self.maxLux = self.settings.getIntOrSet("display_maxLux",100)
      self.maxWPM = 300
      self.loglux = False

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
        if self.mqtt != None:
            self.mqtt.publish("display/brightnessTweak",str(self.BrightnessTweak))
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
                if LogBrightness:
                    log.info("log tweak = %f", (50-TheTweak))
                #~ newpwm = int((self.currentLevel-(TheTweak/4))*4.0)
                #newpwm = int((self.currentLevel*self.pwmscale)+(50-TheTweak))
                newpwm = self.settings.remap(self.currentLevel,2,100,self.minPWMBright,self.maxPWMBright)
            #~ else:
                #~ newpwm = int(self.currentLevel*self.pwmscale)
        else:
            #newpwm = int(self.currentLevel*self.pwmscale)
            newpwm = self.settings.remap(self.currentLevel,2,100,self.minPWMBright,self.maxPWMBright)
        if newpwm < 4:
            newpwm = 4
        elif newpwm > self.maxWPM:
            newpwm = self.maxWPM
        ##log.debug("self.set_PWM_dutycycle %d" , newpwm-1)

        self.pwmtftbrightness.set_PWM_dutycycle(18, newpwm-1)
        if self.mqtt != None:
            self.mqtt.publish("display/brightness",str(newpwm))

        #~ log.info("duty cycle %d", self.pwmtftbrightness.get_PWM_dutycycle(18))

        #self.pwmtftbrightness.ChangeDutyCycle(self.currentLevel)
        if LogBrightness:
            log.debug("pwm brightness %d", newpwm)
        #~ for obj in self.controlObjects:
        #~ obj.setBrightness(self.currentLevel)

    def publish(self):
        self.mqtt.publish("display/brightnessMin",str(self.settings.getInt('min_brightness')))
        self.mqtt.publish("display/brightnessMax",str(self.settings.getInt('max_brightness')))
        self.mqtt.publish("display/brightnessTweak",str(self.BrightnessTweak))
        self.mqtt.publish("display/brightnessMinPWM",str(self.minPWMBright))
        self.mqtt.publish("display/brightnessMaxPWM",str(self.maxPWMBright))
        self.mqtt.publish("autolux",str(self.settings.get("display_autolux")))
        self.mqtt.publish("loglux",str(self.loglux))
        self.mqtt.publish("display/minLux",str(self.minLux))
        self.mqtt.publish("display/maxLux",str(self.maxLux))

    def on_message(self, topic ,payload):
        if (topic.rfind("/")>1):
            method = topic[0:topic.find("/")] # before first "/"
            item = topic[topic.rfind("/")+1:]   # after last "/"
        else: # No "/" present
            method = topic # before first "/"
            item = ""
        log.info("Brightness method='%s', item='%s'", method, item)
        done = False
        try:
            if (method == "display"):
                if (item == "brightnessmaxpwm"):
                    #log.debug("brightnessMaxPWM = '%s'", payload)
                    self.forceUpdate  = True
                    try:
                        self.maxPWMBright = int(payload)
                        self.settings.set("max_pwmbrightness",str(self.maxPWMBright))
                        self.mqtt.publish("display/brightnessMaxPWM",str(self.maxPWMBright))
                    except ValueError:
                        log.warn("Could not decode %s as integer", payload)
                    done = True

                elif (item == "brightnessminpwm"):
                    #log.debug("brightnessMinPWM = '%s'", payload)
                    self.forceUpdate  = True
                    try:
                        self.minPWMBright = int(payload)
                        self.settings.set("min_pwmbrightness",str(self.minPWMBright))
                        self.mqtt.publish("display/brightnessMinPWM",str(self.minPWMBright))
                    except ValueError:
                        log.warn("Could not decode %s as integer", payload)
                    done = True

                elif (item == "maxlux"):
                    #log.debug("maxLux = '%s'", payload)
                    self.forceUpdate  = True
                    try:
                        self.maxLux = int(payload)
                        self.settings.set("display_maxLux",self.maxLux)
                        self.mqtt.publish("display/maxLux",str(self.maxLux))
                    except ValueError:
                        log.warn("Could not decode %s as integer", payload)
                    done = True

                elif (item == "minlux"):
                    #log.debug("minLux = '%s'", payload)
                    self.forceUpdate  = True
                    try:
                        self.minLux = int(payload)
                        self.settings.set("display_minLux",self.minLux)
                        self.mqtt.publish("display/minLux",str(self.minLux))
                    except ValueError:
                        log.warn("Could not decode %s as integer", payload)                        
                    done = True
                elif (item == "brightnessmax"):
                    log.debug("brightnessmax = '%s'", payload)
                    self.forceUpdate  = True
                    try:
                        self.settings.set("max_brightness",int(payload))
                        self.mqtt.publish("display/brightnessMax",str(self.settings.getInt('max_brightness')))
                    except ValueError:
                        log.warn("Could not decode %s as brightnessMax", payload)                        
                    done = True
                elif (item == "brightnessmin"):
                    #log.debug("brightnessmin = '%s'", payload)
                    self.forceUpdate  = True
                    try:
                        self.settings.set("min_brightness",int(payload))
                        self.mqtt.publish("display/brightnessMin",str(self.settings.getInt('min_brightness')))
                    except ValueError:
                        log.warn("Could not decode %s as brightnessMin", payload)                        
                    done = True

            elif (method == "autolux"):
                #log.debug("autolux = '%s'", payload)
                self.forceUpdate  = True
                try:
                    self.autoLux = int(payload)
                    self.settings.set("display_autolux",self.autoLux)
                    self.mqtt.publish("autolux",str(self.settings.get("display_autolux")))
                except ValueError:
                    log.warn("Could not decode %s as integer", payload)                        

                done = True

            elif (method == "loglux"):
                self.forceUpdate  = True
                try:
                    if (payload.lower() == "false"):
                        self.loglux = False
                    elif (payload.lower() == "true"):
                        self.loglux = True
                    else:
                        self.loglux = (int(payload) > 0)
                    self.mqtt.publish("loglux",str(self.loglux))
                except ValueError:
                    log.warn("Could not decode %s as integer", payload)                        

                done = True

        except Exception as e:
            log.debug("on_message Error: %s" , e)
        return done # not for me if false 


    def run(self):
        maxBright = self.settings.getInt('max_brightness')
        minBright = self.settings.getInt('min_brightness')
        self.maxPWMBright = self.settings.getIntOrSet('max_pwmbrightness',300)
        self.minPWMBright = self.settings.getIntOrSet('min_pwmbrightness',60)
        self.minLux = self.settings.getInt("display_minLux")
        self.maxLux = self.settings.getInt("display_maxLux")
        
        # Not great but it works
        valueOver = minLuxChange
        valueUnder = minLuxChange
        # Lux Change Percentage  + or minus LuxChangePercent (Needs to be log scale!)
        # PercentOver  = float(LuxChangePercent) / 100
        # PercentUnder = float(LuxChangePercent) / 100

        if self.mqtt != None:
            self.mqtt.set_Brightness(self)
            self.publish()

        log.info("Brightness thread started")
        LoopTime = MAXLOOP_TIME
        while(not self.stopping):
            time.sleep(LoopTime)

            # We set the brightness manually, so just count down until we can resume auto-brightness
            if(self.manualTimeout > 0):
                self.manualTimeout = self.manualTimeout - 1
                continue

            #~ reading, IRreading = self.sensor._get_luminosity()
            try:
                reading = self.sensor.lux()
            except Exception as e:
                log.debug("Brightness thread Error: %s" , e)    
                reading = self.lastreading

            scaledreading = float(reading) /2.5 # (was 7.0)

            if LogBrightness and (reading != self.lastreading):
                log.debug("reading=%f, last=%f, percentage %f, %f", reading , self.lastreading ,(self.lastreading + valueOver), (self.lastreading - valueUnder)) 
            if (reading > (self.lastreading + valueOver)) or (reading < (self.lastreading - valueUnder)):
            
                if LogBrightness :
                    log.debug("lux,%f, scaledreading=%f", reading, scaledreading)
                if self.mqtt != None:
                    self.mqtt.publish("display/lux",str(reading))
                self.lastreading = reading


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

            #self.readings.pop(0)
            #self.readings.append(newLevel)
            self.LuxReadings.pop(0)
            self.LuxReadings.append(reading)

            #avgLevel = float( sum(self.readings) / float(len(self.readings)) )
            avgLuxLevel = float( sum(self.LuxReadings) / float(len(self.LuxReadings)) )

            levelDiff = abs(self.currentluxLevel - avgLuxLevel)

            #~ print "Reading: %s, Percentage: %s, NewLevel: %s, AvgLevel: %s, Diff: %s" % (reading,percentage,newLevel,avgLevel,levelDiff)

            if ((levelDiff>=1) or (self.forceUpdate == True)):
                #log.debug("mapped level %s" % (self.settings.remap(avgLuxLevel,2,100,self.minPWMBright,self.maxPWMBright)))
                if (self.loglux == True):
                    log.debug("Lux reading %s, Min Lux %s, Max Lux %s" %(avgLuxLevel, self.minLux, self.maxLux))
                if LogBrightness:
                    log.debug( "Reading: %s, Percentage: %s, NewLevel: %s, AvgLevel: %s, Diff: %s" % (reading,percentage,newLevel,avgLevel,levelDiff))
                #~ log.debug("lux %s", self.sensor._calculate_lux(reading, IRreading))
                #~ print "Updating brightness to %s" % (avgLevel)
                self.currentluxLevel = avgLuxLevel
                if(levelDiff >= 2):
                    LoopTime = MINLOOP_TIME
                else:
                    LoopTime = MAXLOOP_TIME
                self.forceUpdate  = False

                if (self.autoLux != 0):
                    if (avgLuxLevel < self.minLux):
                        log.debug("minlux %s > reading %s", self.minLux, avgLuxLevel)
                        self.minLux = avgLuxLevel
                        self.settings.set("display_minLux",str(int(self.minLux)))
                        if self.mqtt != None:
                            self.mqtt.publish("display/minLux",str(self.minLux))
                    elif (avgLuxLevel > self.maxLux):
                        log.debug("reading %s > maxlux %s", avgLuxLevel, self.maxLux)
                        self.maxLux = avgLuxLevel
                        self.settings.set("display_maxLux",str(int(self.maxLux)))
                        if self.mqtt != None:
                            self.mqtt.publish("display/maxLux",str(self.maxLux))                
                self.currentLevel = self.settings.remap(avgLuxLevel,self.minLux,self.maxLux,0,100)
                self.updateBrightness()

        self.maxBrightness()

        # Turn off brightness PWM
        self.pwmtftbrightness.stop()
        #GPIO.cleanup()
        #PWM.cleanup()


