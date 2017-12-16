# Code from http://www.dronkert.net/rpi/vol.html for volume adjustment

import time
import datetime
#import pytz
import threading
import sys
import subprocess
#import Settings
#import MediaPlayer
import logging
import pygame
import subprocess
from pygame.locals import *
import Settings
import os

import colours
import math
import requests

log = logging.getLogger('root')

TUNEINSTARTURL = "http://opml.radiotime.com/Browse.ashx?id=r101309"

LOOP_TIME=float(0.2)

menuItems = [ "Settings", "Browse Radio", "Dim Screen", "Info", "Shutdown"]
menu_DimScreen = ["5 Up", "1 Up","1 Down","5 Down","Minimum","Automatic"]

menu_clockformat = ["4 digit clock", "6 digit clock", "Clock - Default font", "Clock - 7 Segment", "Menu - Default Font", "Menu - 14 Segment" ]

menu_alarm = ["Auto-set Alarm", "Manual Alarm"]
Daynames = ["Mon :","Tue :","Wed :","Thu :","Fri :","Sat :","Sun :"]
menu_onoff = [ "On", "Off" ]

oRequestLink = requests.Session()

MenuColour = colours.RED

class MenuControl(threading.Thread):
   def __init__(self,lcd, MediaPlayer, Weather, CallBack, brightnessThreadptr): # ,alarmThread):
      threading.Thread.__init__(self)

      #self.shutdownCallback = shutdownCallback
      #self.alarmThread = alarmThread
      self.settings = Settings.Settings()
      self.media = MediaPlayer
      self.lcd = lcd
      self.Weather = Weather
      self.brightness = brightnessThreadptr

      #self.menuPointer = None
      self.menuTimeout = 0
      self.menuActive = False
      #self.tmp = 0
      self.active = False
      self.stopping = False
      self.MenuDisplayed = False
      #self.settings = settings
      self.MainLoop = CallBack
      self.ExitAllMenus = False

   def isActive(self):
      return self.active

   def backgroundRadioActive(self):
      return self.media.playerActive()

   def DisplayMenu(self,MenutoDisplay = [], Title = "Main Menu", MenuValues = None):
       ptr = 0

       self.MainLoop.pauseclock(True)
       self.active = True
       pygame.mouse.set_visible(True)
       self.ExitAllMenus = False

       if MenutoDisplay == []:
           MenutoDisplay = menuItems
           #~ MenuValues = [self.settings.get('volume') +"%","","",self.__getOnOrOff("holiday_mode"),""]

       if MenutoDisplay[-1] != "Back":
           MenutoDisplay.append("Back")

       action = self.DisplaySubMenu(MenutoDisplay, Title, MenuValues)

       #if (action == "Exit"):
       #     self.MainLoop.stop()
       pygame.mouse.set_visible(False)
       self.MainLoop.pauseclock(False)
       self.exitMenu()
       #print "finished menu"
       return action


   def DisplaySubMenu(self,MenutoDisplay, Title = "", MenuValues = None):
       if MenutoDisplay[-1] != "Back":
           MenutoDisplay.append("Back")

       offset = 0
       LineHeight, maxoffset = self.lcd.DisplayMenu(Title, MenutoDisplay,MenuColour, -1, MenuValues, displayoffset=offset)
       calcTimeout = self.settings.getInt('menu_timeout')*(1/LOOP_TIME) # We're unlikely to update this on the fly
       menuwaiting = True
       menuTimeout = 0
       self.menuTimeout = calcTimeout + 2
       lastpos = (-1,-1)
       LastMenuItem = "?"
       MenuChoice = ""
       downpos = -1000
       dragchange = 0
       Dragging = False


       while(not self.stopping) and (menuwaiting == True) and (self.ExitAllMenus == False):
            time.sleep(LOOP_TIME)
            if menuTimeout > calcTimeout:
                #self.exitMenu()
                menuwaiting = False
            else:
                menuTimeout = menuTimeout + 1

            for event in pygame.event.get():
               pos = event.pos # pygame.mouse.get_pos()
               if (event.type is QUIT):
                   #~ self.stopping = True
                   self.stop()

               elif (event.type is MOUSEMOTION):
                    if downpos <> -1000:
                        mx,my = pos
                        dragchange = downpos - my
                        if abs(dragchange) > 4: #LineHeight:
                            Dragging = True
                            log.debug("move line %d - %d",offset, dragchange)
                            offset = offset - dragchange #(math.copysign(1, dragchange) * LineHeight)
                            if offset + maxoffset < 0:
                                offset = 0-maxoffset
                            if offset > 0:
                                offset = 0
                            log.debug("move line %d , %d",offset, maxoffset)
                            if LastMenuItem <> "?":
                                LineHeight, maxoffset = self.lcd.DisplayMenu(Title, MenutoDisplay, MenuColour, Highlighted, MenuValues, colours.BLUE, ExtraMessage=MenuChoice, displayoffset=offset)
                            else:
                                LineHeight, maxoffset = self.lcd.DisplayMenu(Title, MenutoDisplay,MenuColour, -1, MenuValues, displayoffset=offset)
                            downpos = my


               elif (event.type is MOUSEBUTTONDOWN):
                    mx,my = pos
                    downpos = my
                    Dragging = False
                    #~ dragchange = 0

               elif (event.type is MOUSEBUTTONUP):
                  #~ pos = pygame.mouse.get_pos()
                  menuTimeout = 0
                  downpos = -1000
                  if (pos != lastpos) and (Dragging == False):
                    lastpos = pos
                    mx,my = pos
                    my = my - 5 - offset
                    if (Title != ""):
                        my = my - LineHeight
                    Highlighted = int(my / LineHeight)
                    if (Highlighted > len(MenutoDisplay)-1) or (Highlighted < 0):
                        if (Highlighted > len(MenutoDisplay)): # probably the automatically appended "back" option
                            menuwaiting = False
                        Highlighted = -1
                    if (Highlighted > -1):
                        #~ print "my=" , my
                        #~ log.info ("Selection %d, '%s'", my, MenutoDisplay[my])
                        LineHeight,maxoffset = self.lcd.DisplayMenu(Title, MenutoDisplay, MenuColour, Highlighted, MenuValues, colours.BLUE, ExtraMessage=MenuChoice, displayoffset=offset)
                        if (MenutoDisplay[Highlighted] == LastMenuItem):
                            MenuChoice = self.MenuSelection(MenutoDisplay[Highlighted], Title)
                            #~ log.info ("MenuChoice=%s", MenuChoice)

                            # Handle special case results of menu selection
                            if (MenuChoice == "Cancel"):
                                self.cancel()
                            elif (MenuChoice == "Back"):
                                menuwaiting = False
                            elif (MenuChoice == "Exit"):
                                menuwaiting = False
                                return MenuChoice
                            else: # Display returned message
                                LineHeight,maxoffset = self.lcd.DisplayMenu(Title, MenutoDisplay, MenuColour, Highlighted, MenuValues, colours.BLUE, ExtraMessage=MenuChoice, displayoffset=offset)
                        else:
                            LastMenuItem = MenutoDisplay[Highlighted]

                  Dragging = False

               #~ if (event.type is QUIT):
                   #~ self.stop()


       self.lcd.setMessage("",False, colour = (0,0,0))
       return ""

   def MenuSelection(self,SelectedItem, Title):

        if (SelectedItem == "Back"):
            return "Back"
        elif (SelectedItem == "Cancel"):
            return "Cancel"

        # ways out, exit or restart
        elif (SelectedItem == "Stop Clock"): # and (Title == "Confirm Exit"):
                return "Exit"
        elif (SelectedItem == "Restart Clock"): # and (Title == "Confirm Exit"):
                #~ self.settings.set("quiet_reboot","1")
                #~ subprocess.Popen('/etc/init.d/piclock restart', shell=True)
                self.MainLoop.stop(3)
                return "Exit"
        elif (SelectedItem == "Shutdown Clock"):
            self.MainLoop.stop(2)
            return "Exit"
        elif (SelectedItem == "Reboot Clock"):
            self.MainLoop.stop(1)
            return "Exit"
        elif (SelectedItem == "Shutdown"):
            #~ if (Title == "Confirm Exit"):
                #~ return "Exit"

            # Return the results incase it needs passing right back to the top level
            menu_ConfirmExit = ["Stop Clock", "Reboot Clock", "Restart Clock", "Shutdown Clock", "Cancel" ]
            return self.DisplaySubMenu(menu_ConfirmExit, "Confirm Shutdown")

        elif (SelectedItem == "Holiday Mode"):
            if self.settings.getInt("holiday_mode") == 0:
                self.settings.set("holiday_mode","1")
            else:
                self.settings.set("holiday_mode","0")
            return self.__getOnOrOff("holiday_mode")

        # volume control
        elif (SelectedItem == "Volume"):
            menu_volume = [ "Volume Up", "Volume Down" ]
            self.DisplaySubMenu(menu_volume, "Volume Control")
        elif (SelectedItem == "Volume Up"):
            newvol = int(self.settings.get('volume')) + 2
            if newvol > 100:
                newvol = 100
            self.settings.set('volume',newvol)
            return self.settings.get('volume')
        elif (SelectedItem == "Volume Down"):
            newvol = int(self.settings.get('volume')) - 2
            if newvol < 1:
                newvol = 1
            self.settings.set('volume',newvol)
            return self.settings.get('volume')

        elif (SelectedItem == "Settings"):
            MenuValues = [self.settings.get('volume') +"%","","",self.__getOnOrOff("holiday_mode"),""]
            menusettings = ["Volume", "Alarm Settings", "Display Settings", "Holiday Mode"]
            self.DisplaySubMenu(menusettings, "Settings", MenuValues)

        elif (SelectedItem == "Display Settings"):
            menu_display = ["Menu Timeout", "Show Weather", "Dim Screen", "Clock Display"]
            self.DisplaySubMenu(menu_display, "Display Settings")


        elif (SelectedItem == "Show Weather"):
            weatherInfo = self.Weather.getWeather().speech()
            return weatherInfo

        elif (SelectedItem == "Info"):
            temp = int(open('/sys/class/thermal/thermal_zone0/temp').read()) / 1e3

            menu_display =     ["Lan IP  : " + self.MainLoop.GetIPForNetwork("eth0")]
            menu_display.append("Wifi IP : " + self.MainLoop.GetIPForNetwork("wlan0"))

            ssid = os.popen("iwgetid -r").read().replace(chr(10),"")
            menu_display.append("SSID    : " + ssid)
            if self.media.player:
                try:
                        menu_display.append("Title   : " + self.media.player.metadata['title'])
                except Exception as e :
                        menu_display.append("Title   : ?")
                try:
                    menu_display.append("Artist  : " + self.media.player.metadata['artist'])
                except Exception as e :
                    menu_display.append("Artist  : ?")
                log.debug(self.media.player.metadata)
                try:
                    log.info("current = %d", self.media.player.stream_pos)
                    log.info("end = %d", self.media.player.stream_end)
                except: # catch *all* exceptions
                    e = sys.exc_info()[0]
                    log.debug( "Error: %s" , e )

            menu_display.append("Temp (C) : %f" % temp)
            menu_display.append("Back" )
            self.DisplaySubMenu(menu_display, "Information")

        elif (SelectedItem == "Clock Display"):

            if int(self.settings.get('clock_format')) == 4:
                ClockStates = ["<--",""]
            else:
                ClockStates = ["","<--"]
            if self.settings.get('clock_font') == "":
                ClockStates.extend(["<--",""])
            else:
                ClockStates.extend(["","<--"])
            if self.settings.get('menu_font') == "":
                ClockStates.extend(["<--",""])
            else:
                ClockStates.extend(["","<--"])
            self.DisplaySubMenu(menu_clockformat, "Clock Display Format",ClockStates)
            #
        elif Title == "Clock Display Format": #(SelectedItem in menu_clockformat):

            DisplaySelection = menu_clockformat.index(SelectedItem)
            if   DisplaySelection == 0:
                self.settings.set('clock_format','4')
                return self.settings.get('clock_format') + " digit clock"
            elif DisplaySelection == 1:
                self.settings.set('clock_format','6')
                return self.settings.get('clock_format') + " digit clock"
            elif DisplaySelection == 2:
                self.settings.set('clock_font','')
                self.lcd.ChooseFonts()
                return "Clock Font is " + self.settings.get('clock_font')
            elif DisplaySelection == 3:
                self.settings.set('clock_font','dseg7modern')
                self.lcd.ChooseFonts()
                return "Clock Font is " + self.settings.get('clock_font')
            elif DisplaySelection == 4:
                self.settings.set('menu_font','')
                self.lcd.ChooseFonts()
                return "Menu Font is " + self.settings.get('menu_font')
            elif DisplaySelection == 5:
                self.settings.set('menu_font','dseg14modern')
                self.lcd.ChooseFonts()
                return "Menu Font is " + self.settings.get('menu_font')
            #~ elif (SelectedItem == "4 digit clock"):
                #~ self.settings.set('clock_format','4')
                #~ return self.settings.get('clock_format') + " digit clock"
            #~ elif (SelectedItem == "6 digit clock"):
                #~ self.settings.set('clock_format','6')
                #~ return self.settings.get('clock_format') + " digit clock"
            #~ elif (SelectedItem == "Menu - Default Font"):
                #~ self.settings.set('menu_font','')
                #~ self.lcd.ChooseFonts()
                #~ return "Menu Font is " + self.settings.get('menu_font')
            #~ elif (SelectedItem == "Menu - 14 Segment"):
                #~ self.settings.set('menu_font','dseg14modern')
                #~ self.lcd.ChooseFonts()
                #~ return "Menu Font is " + self.settings.get('menu_font')
                #
            #~ elif (SelectedItem == "Clock - Default font"):
                #~ self.settings.set('clock_font','')
                #~ self.lcd.ChooseFonts()
                #~ return "Clock Font is " + self.settings.get('clock_font')

            #~ elif (SelectedItem == "Clock - 7 Segment"):
                #~ self.settings.set('clock_font','dseg7modern')
                #~ self.lcd.ChooseFonts()
                #~ return "Clock Font is " + self.settings.get('clock_font')


        elif (SelectedItem == "Dim Screen"):
            # Defined as global as need it several times
            #~ menu_DimScreen = ["5 Up", " 1 Up"," 1 Down","5 Down", "Automatic"]
            self.DisplaySubMenu(menu_DimScreen, "Dim Screen")
            #~ self.MainLoop.setBrightness(1)
            return "Dimmed"

        elif Title == "Dim Screen": #(SelectedItem in menu_DimScreen):
            DimAmount = menu_DimScreen.index(SelectedItem)
            if DimAmount == 0:
                action = 5
            elif DimAmount == 1:
                action = 1
            elif DimAmount == 2:
                action = -1
            elif DimAmount == 3:
                action = -5
            elif DimAmount == 4:
                action = 100 #self.settings.getInt('max_brightness')
            else:
                action = 0
                self.brightness.setBrightnessTweak(0)

            #~ if (self.MainLoop.getBrightnessTweak() + action < 80) and
            if (action != 0):
                self.brightness.setBrightnessTweak(self.brightness.getBrightnessTweak() + action)
            return "Adjustment " + str(self.brightness.getBrightnessTweak())

        elif (SelectedItem == "Alarm Settings"): # List all alarm days, time and stations

            StationList = []
            for stationname in Settings.STATIONS:
                StationList.append(stationname['name'])
            alarmvalues = []
            for dayno in range(0,7):
                alarmvalues.append(self.settings.get('alarm_weekday_' + str(dayno)) + " " + StationList[int(self.settings.get('alarm_station_' + str(dayno)))])
            DayMenu = Daynames
            #~ DayMenu.append("Back")
            action = self.DisplaySubMenu(DayMenu, "Daily Alarm Details",alarmvalues)

            return action

        elif (SelectedItem in Daynames): # for daynames as menus selections, set the alarm for that day
            Dayno = Daynames.index(SelectedItem)
            log.debug("Found day no %d",Dayno)
            action = self.lcd.ChangeAlarmSettings(Dayno)
            if (action == True):
                # alarm should be "hh:mm"
                #~ self.settings.set('alarm_weekday_' + str(Dayno), "%02d:%1d%1d" % (action[0], action[1], action[2]))
                #~ self.settings.set('alarm_station_' + str(Dayno), str(action[3]))
                #~ log.info("Alarm for %s changed to %s at %02d:%1d%1d"  % (Daynames[Dayno], Settings.STATIONS[int(action[3])]['name'], action[0], action[1], action[2]))
                self.MainLoop.AutoSetAlarm()
                return "Alarm Changed"

            return "Alarm Not Changed"

        elif SelectedItem =="Browse Radio":
            return self.BrowseRadio(TUNEINSTARTURL)
            #~ self.DisplaySubMenu(RadioMenu, "Browse Radio")

        #~ elif  Title[:12] == "Browse Radio":

            #~ try:
                #~ NewLinkno = RadioMenu.index(SelectedItem)
                #~ log.info("Newlinkno = %d", NewLink)
                #~ log.info("NewLink   = %s", RadioLinks[NewLinkno])
                #~ RadioMenu, RadioLinks = self.BrowseRadio("http://opml.radiotime.com/")
                #~ self.DisplaySubMenu(RadioMenu, "Browse Radio - " + NewLink)
            #~ except:
                #~ log.exception("Error in Browse Radio")
            #~ return "oops"
        else:
            log.debug("Title     : %s", Title)
            log.debug("selection : %s", SelectedItem)

        #~ elif (SelectedItem == "Control Radio"):
            #~ #self.media.playerActive()
            #~ if self.media.playerActive():
                #~ Menu_Radio = [ "Stop Radio", "Choose Station" ]
            #~ else:
                #~ Menu_Radio = [ "Play Radio", "Choose Station" ]
            #~ return self.DisplaySubMenu(Menu_Radio, "Radio Settings",["", " (" + self.__getStationName(self.settings.getInt('station')) + ")"])
            #~ #
        #~ elif (SelectedItem == "Play Radio"):
            #~ if (self.media.playerActive() == False):
                #~ self.media.playStation()
                #~ return "Playing"
            #~ else:
                #~ return "Already Playing"
        #~ elif (SelectedItem == "Stop Radio"):
            #~ if (self.media.playerActive() != False):
                #~ self.media.stopPlayer()
                #~ return "Stopped"
            #~ else:
                #~ return "Already Stopped"
        #~ elif (SelectedItem == "Choose Station"):
            #~ StationList = []
            #~ for stationname in Settings.STATIONS:
                #~ StationList.append(stationname['name'])
            #~ NewStation = self.lcd.SelectValueFromList("Default Radio Station",20, 140, self.__getStationName(self.settings.getInt('station')), StationList, colours.WHITE)
            #~ #
            #~ stationNo = 0
            #~ for stationname in Settings.STATIONS:
                #~ if stationname['name'] == NewStation:
                    #~ log.debug("NewStation=%s", NewStation)
                    #~ self.settings.set('station', stationNo)
                    #~ if self.media.playerActive() == True:
                        #~ self.lcd.setMessage("Changing Radio Stations")
                        #~ self.media.stopPlayer()
                        #~ self.media.playStation()
                    #~ return NewStation
                #~ stationNo +=1

        return ""


   def select(self):
      if self.menuPointer is None:
         return # We can ignore this button if we're not in a menu

      if self.menuActive:
         # We're in an active menu item and have just hit select, so we should save the setting here
         if(menuItems[self.menuPointer]=="Volume"):
            self.settings.set('volume',self.tmp)
         elif(menuItems[self.menuPointer]=="Manual Alarm"):
            self.alarmThread.manualSetAlarm(self.__alarmTimeFromInput())
         elif(menuItems[self.menuPointer]=="Station"):
            self.settings.set('station',self.tmp)
         elif(menuItems[self.menuPointer]=="Play/Stop Radio"):
            # Because of the check in the !self.menuActive below, we must be requesting to play if we get here
            log.debug("Request to start playing %s" % (self.__getStationName(self.tmp)))
            self.media.playStation(self.tmp)
         elif(menuItems[self.menuPointer]=="Holiday Mode"):
            if self.settings.getInt('holiday_mode')!=self.tmp:
               # We don't want to do drastic things unless we've changed the setting
               self.settings.set('holiday_mode',self.tmp)
               if self.tmp==1:
                  # We've just enabled holiday mode, so clear any alarms
                  log.info("Holiday Mode enabled")
                  self.alarmThread.clearAlarm()
               else:
                  log.info("Holiday Mode disabled")
                  # We've just disabled holiday mode, so start auto-setup
                  self.alarmThread.autoSetAlarm()

         self.exitMenu()
      else:
         # We're not in an active menu item, so we must have just selected one

         if(menuItems[self.menuPointer]=="Restart"):
            self.exitMenu()
            self.shutdownCallback()
            return

         if(menuItems[self.menuPointer]=="Auto-set Alarm"):
            self.alarmThread.autoSetAlarm()
            self.exitMenu()
            return

         if(menuItems[self.menuPointer]=="Play/Stop Radio" and self.media.playerActive()):
            # Media player active, so stop it
            log.info("Stopping radio player")
            self.media.stopPlayer()
            self.exitMenu()
            return

         self.menuActive = True

         # Set our temporary variable to current setting
         self.tmp = {
            'Volume': self.settings.getInt('volume'),
            'Manual Alarm': 0,
            'Station': self.settings.getInt('station'),
            'Holiday Mode': self.settings.getInt('holiday_mode'),
            'Play/Stop Radio': self.settings.getInt('station'),
         }.get(menuItems[self.menuPointer])

         log.debug("Selected menu %s", menuItems[self.menuPointer])

   def cancel(self):
      #~ if self.backgroundRadioActive():
         #~ self.media.stopPlayer()

      self.exitMenu()


   # We need to catch a possible IndexError that crops up in getMessage()
   def __getStationName(self,stationindex):
      try:
         return Settings.STATIONS[stationindex]['name']
      except IndexError:
         return ""

   def __getOnOrOff(self, value):
      return "Enabled" if self.settings.getInt(value)==1 else "Disabled"

   def getMessage(self):
      message = ""
      if self.menuPointer is not None:
         if not self.menuActive:
            # We're browsing the menu, so show what we have selected
            message = "Options\n\n%s" % (menuItems[self.menuPointer])
         else:
            # We have an item active, so display our current option
            msg = {
               'Volume': "Volume: %s" % (self.tmp),
               'Manual Alarm': "Alarm at: %s" % (self.__alarmTimeFromInput().strftime("%H:%M")),
               'Station': "Alarm Station:\n%s" % (self.__getStationName(self.tmp)),
               'Holiday Mode': "Holiday Mode:\n%s" % (self.__getOnOrOff()),
               'Play/Stop Radio': "Play station:\n%s" % (self.__getStationName(self.tmp))
            }.get(menuItems[self.menuPointer])

            message = "Set %s" % (msg)

      return message

   def exitMenu(self):
      self.active = False
      #self.menuPointer = None
      self.menuTimeout = 0
      self.menuActive = False
      #self.tmp = ""
      self.ExitAllMenus = True

   def stop(self):
      self.stopping = True
      self.ExitAllMenus = True

   def run(self):
      calcTimeout = self.settings.getInt('menu_timeout')*(1/LOOP_TIME) # We're unlikely to update this on the fly
      while(not self.stopping):
         time.sleep(LOOP_TIME)
         if self.menuTimeout > calcTimeout:
            self.exitMenu()
         elif(self.menuPointer is not None):
            self.menuTimeout+=1

   def BrowseRadio(self,StartURL):
       global oRequestLink
       #MenutoDisplay, Title = "", MenuValues = None):

       MenuTitle, MenuText, MenuURLs, Subtexts, NowPlayings, Types = self.GetRadioURL(StartURL)
       Title = "Browse Radio"
       MenuValues = None

       offset = 0
       LineHeight, maxoffset = self.lcd.DisplayMenu(Title + " - " + MenuTitle, MenuText,MenuColour, -1, MenuValues, displayoffset=offset)
       calcTimeout = self.settings.getInt('menu_timeout')*(1/LOOP_TIME) # We're unlikely to update this on the fly
       menuwaiting = True
       menuTimeout = 0
       self.menuTimeout = calcTimeout + 2
       lastpos = (-1,-1)
       LastMenuItem = "?"
       MenuChoice = ""
       downpos = -1000
       dragchange = 0
       Dragging = False


       #~ MenuTextOld = []
       #~ MenuURLsOld = []
       #~ SubtextsOld = []
       #~ NowPlayingsOLD = []
       #~ Offsets = []
       LastMenuInfo = []

       while(not self.stopping) and (menuwaiting == True) and (self.ExitAllMenus == False):
            time.sleep(LOOP_TIME)
            if menuTimeout > calcTimeout:
                #self.exitMenu()
                menuwaiting = False
            else:
                menuTimeout = menuTimeout + 1

            for event in pygame.event.get():
               pos = event.pos # pygame.mouse.get_pos()
               if (event.type is QUIT):
                   #~ self.stopping = True
                   self.stop()

               elif (event.type is MOUSEMOTION):
                    if downpos <> -1000:
                        mx,my = pos
                        dragchange = downpos - my
                        if abs(dragchange) > LineHeight:
                            dragchange = dragchange * 2
                        if abs(dragchange) > LineHeight/2:
                            Dragging = True
                            offset = offset - dragchange #(math.copysign(1, dragchange) * LineHeight)
                            log.debug("move line %d",offset)
                            if offset > 0:
                                offset = 0
                            elif offset < - maxoffset:
                                offset = - maxoffset
                            log.debug("move line %d",offset)
                            if LastMenuItem <> "?":
                                LineHeight,maxoffset = self.lcd.DisplayMenu(Title, MenuText, MenuColour, Highlighted, MenuValues, colours.BLUE, ExtraMessage=MenuChoice, displayoffset=offset)
                            else:
                                LineHeight, maxoffset = self.lcd.DisplayMenu(Title, MenuText,MenuColour, -1, MenuValues, displayoffset=offset)
                            downpos = my


               elif (event.type is MOUSEBUTTONDOWN):
                    mx,my = pos
                    downpos = my
                    Dragging = False
                    #~ log.info("dragging = False = %s", Dragging)
                    #~ dragchange = 0

               elif (event.type is MOUSEBUTTONUP):
                  #~ pos = pygame.mouse.get_pos()
                  menuTimeout = 0
                  downpos = -1000
                  if (pos != lastpos) and (Dragging == False):
                    lastpos = pos
                    mx,my = pos
                    my = my - 5 - offset
                    if (Title != ""):
                        my = my - LineHeight
                    Highlighted = int(my / LineHeight)
                    if (Highlighted > len(MenuText)): # probably the automatically appended "back" option
                        Highlighted = len(MenuText)

                    if (Highlighted > -1):
                        LineHeight,maxoffset = self.lcd.DisplayMenu(Title + " - " + MenuTitle, MenuText, MenuColour, Highlighted, MenuValues, colours.BLUE, ExtraMessage=MenuChoice, displayoffset=offset)
                        if (MenuText[Highlighted] == LastMenuItem):
                            SelectedItem = MenuText[Highlighted]
                            log.info("Newlinkno = %d", Highlighted)
                            log.info("NewLink   = %s", MenuURLs[Highlighted])
                            #~ log.info ("MenuChoice=%s", MenuChoice)
                            MenuChoice = MenuURLs[Highlighted]

                            # Handle special case results of menu selection
                            if (MenuChoice == "Back"):
                                if len(LastMenuInfo) > 0:
                                    #~ MenuText = MenuTextOld.pop()
                                    #~ MenuURLs = MenuURLsOld.pop()
                                    #~ Subtexts = SubtextsOld.pop()
                                    #~ NowPlayings = NowPlayingsOLD.pop()

                                    #~ offset = Offsets.pop()
                                    LastInfo = LastMenuInfo.pop()
                                    MenuTitle, MenuText, MenuURLs, Subtexts, NowPlayings, offset, Highlighted = LastInfo
                                    LineHeight,maxoffset = self.lcd.DisplayMenu(Title + " - " + MenuTitle, MenuText, MenuColour, Highlighted, MenuValues, colours.BLUE, displayoffset=offset)
                                else:
                                    menuwaiting = False
                            elif Types[Highlighted] == "audio":
                                log.info("Would Play %s", MenuChoice)
                                self.GetRadioPlaylist(SelectedItem,MenuChoice)
                                #~ self.media.playStationURL(SelectedItem, MenuURLs[Highlighted])
                                menuwaiting = False
                            elif Types[Highlighted] == "link":
                                #~ MenuTextOld.append (MenuText)
                                #~ MenuURLsOld.append (MenuURLs)
                                #~ SubtextsOld.append (Subtexts)
                                #~ NowPlayingsOLD.append (NowPlayings)
                                #~ Offsets.append (offset)
                                LastMenuInfo.append ([MenuTitle, MenuText, MenuURLs, Subtexts, NowPlayings, offset, Highlighted])
                                MenuTitle, MenuText, MenuURLs, Subtexts, NowPlayings, Types = self.GetRadioURL(MenuChoice)
                                offset = 0
                                Highlighted = -1
                                LineHeight,maxoffset = self.lcd.DisplayMenu(Title + " - " + MenuTitle, MenuText, MenuColour, Highlighted, MenuValues, colours.BLUE, ExtraMessage=MenuChoice, displayoffset=offset)
                        else:
                            LastMenuItem = MenuText[Highlighted]

                  Dragging = False

               #~ if (event.type is QUIT):
                   #~ self.stop()


       self.lcd.setMessage("",False, colour = (0,0,0))
       return ""

   def GetRadioPlaylist(self, StationName, CurrentURL):
        response = oRequestLink.get(CurrentURL)
        html = response.text
        info = response.headers
        stype = info['Content-Type']
        if stype.find(";") > 0:
            stype=stype[:stype.find(";")]
            if stype.find(" ") > 0:
                stype=stype[:stype.find(" ")]
        #~ response = urllib2.urlopen(CurrentURL)
        #~ html = response.read()
        #~ info = response.info()
        #~ stype = info.type
        log.info("stype=%s", stype)

        if (stype == "audio/x-mpegurl"):

            htmllines = html.splitlines() #split(chr(13) + chr(10))
            StationURL = ""

            for lineno in htmllines:
                ifile = lineno.lower().find("file1=")
                log.info("ifile %d", ifile)
                if ifile > 0:
                    StationURL = lineno[ifile+6:]
            if StationURL == "":
                StationURL = htmllines[0]

            log.info("sURL=%s", StationURL)
            if StationURL <> "":
                self.media.playStationURL(StationName, StationURL)


   def GetRadioURL(self, CurrentURL):
        global oRequestLink
        #~ log.info("Grabbing %s", CurrentURL)
        #~ response = urllib2.urlopen(CurrentURL)
        #~ html = response.read()
        #~ info = response.info()
        #~ stype = info.type
        response = oRequestLink.get(CurrentURL)
        html = response.text
        info = response.headers
        stype = info['Content-Type']
        if stype.find(";") > 0:
            stype=stype[:stype.find(";")]
            if stype.find(" ") > 0:
                stype=stype[:stype.find(" ")]

        #~ log.info("Content is %s", stype)

        htmllines = html.split(chr(13) + chr(10))
        MenuText = []
        MenuURLs = []
        Subtexts = []
        NowPlayings = []
        Types = []
        stitle = ""

        if (stype == "audio/x-mpegurl"):
            log.info(html)
            response = oRequestLink.get(htmllines[0])
            html = response.text
            info = response.headers
            stype = info['Content-Type']
            if stype.find(";") > 0:
                stype=stype[:stype.find(";")]
                if stype.find(" ") > 0:
                    stype=stype[:stype.find(" ")]

            #~ response = urllib2.urlopen(htmllines[0])
            #~ playlist = response.read()
            #~ info = response.info()
            #~ stype = info.type
            log.info("Content is %s", stype)
            log.info("playlist is %s", playlist)

        elif (stype == "text/xml"):
            # <outline type="link" text="United Kingdom" URL="http://opml.radiotime.com/Browse.ashx?id=r101309" guide_id="r101309"/>
            for lineno in htmllines:
                ioutline = lineno.find("<")
                if ioutline > -1:
                    # Find the tag wich end in a space or >
                    ioutline += 1
                    Fullline = lineno[ioutline:]
                    iendtag = Fullline.find(">")
                    ispace = Fullline.find(" ")
                    if (ispace < iendtag) and (ispace > -1):
                        sTag= Fullline[:ispace].lower()
                    else:
                        sTag= Fullline[:iendtag].lower()
                        Fullline = Fullline[iendtag+1:]

                    # Decode and use the tag
                    if sTag == "title":
                        ioutline = Fullline.find("<")
                        stitle = Fullline[:ioutline]

                    elif sTag == "outline":
                        sText = self.GrabProperty(Fullline,"text")
                        sURL = self.GrabProperty(Fullline,"URL")
                        sSubtext = self.GrabProperty(Fullline,"subtext")
                        sNowPlaying = self.GrabProperty(Fullline,"now_playing_id")
                        stype = self.GrabProperty(Fullline,"type")

                        if (sText <> "") and (sURL <> ""):
                            MenuText.append (sText)
                            MenuURLs.append (sURL)
                            Subtexts.append (sSubtext)
                            NowPlayings.append (sNowPlaying)
                            Types.append (stype)
                        #~ log.info("%s = %s", sText, sURL)

            MenuText.append ("Back")
            MenuURLs.append ("Back")
            Subtexts.append ("Back")
            NowPlayings.append ("Back")
            Types.append ("Back")
        else:
            log.info("type %s", stype)
            log.info(html)

        return stitle, MenuText, MenuURLs, Subtexts, NowPlayings, Types

   def GrabProperty(self, sFullline, sProperty):
        iproperty = sFullline.find(sProperty + "=")
        if iproperty > 0:
            iproperty += 2 + len(sProperty)
            sresult  = sFullline[iproperty:]
            iquote = sresult.find(chr(34))
            sresult = sresult[:iquote]
        else:
            sresult = ""

        return sresult
