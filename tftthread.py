#!/usr/bin/python

# TFT running both input and output
# Also handles volume slider (right side)
# Alarm cancelling (Center when alarm playing)
# Menus (Center when alarm Not playing)
# radio control (left side)

# 27/03/2020 - Actually uses SCREEN_HEIGHT and SCREEN_WIDTH
# 18/10/2020 - Blanks the entire volume area to avoid leaving bits behind
# 18/10/2020 - Moved setting & adding to extra message into a function
# 26/01/2021 - Moved player monitoring to player Thread
#              Message creation & store moved to each thread
# 26/05/2021 - Volume slider is now changing volumepercent i.e. usable volume
# 30/05/2021 - Only try for weather if its been setup
# 11/09/2021 - Added mqtt input & output of display colour
# 23/11/2021 - Fixed colour output on mqtt on startup

#from LCDControl.LCDControl import LCDControl
#import gaugette.rotary_encoder
import time
import datetime
#import pytz
import threading
import MenuControl
import Settings
#from InputWorker import InputWorker
import logging
import os
import pygame
from pygame.locals import *
import math

log = logging.getLogger('root')


SCREEN_WIDTH = 480
SCREEN_HEIGHT = 320

CONTROL_ZONE = SCREEN_WIDTH / 6

import colours

# index meanings for onscreen buttons etx
KEY_ControlType =0
KEY_UpButtonarea=1
KEY_UpButton=2
KEY_DownButtonarea=3
KEY_DownButton=4
KEY_SelectButtonarea=5
KEY_scrollsurface=6
KEY_fontlineheight=7
KEY_SelectedValue=8
KEY_OldSelectedValue=9
KEY_MinValue=10
KEY_MaxValue=11
KEY_xs =12
KEY_ys = 13
KEY_yoffset = 14
KEYSelectAction = 15

#
# Date convenience methods
#

def suffix(d):
   return 'th' if 11<=d<=13 else {1:'st',2:'nd',3:'rd'}.get(d%10, 'th')

def formatDate(dateObj):
   message = dateObj.strftime("%a ")
   message+= dateObj.strftime("%d").lstrip("0")
   message+= suffix(dateObj.day)
   message+= dateObj.strftime(" %B")

   return message

# Ensure PiTFT is usable
os.putenv('SDL_VIDEODRIVER','fbcon')
os.putenv('SDL_FBDEV','/dev/fb1')
os.putenv('SDL_MOUSEDRV','TSLIB')
os.putenv('SDL_MOUSEDEV','/dev/input/touchscreen')

pygame.init()
pygame.mixer.quit()
#
# Class dealing with displaying relevant information on the LCD screen
#


class TFTThread(threading.Thread):

   def __init__(self,Callback, Settings): #alarmThread,Callback, media, weather):
      threading.Thread.__init__(self)
      self.alarmThread = None #alarmThread
      self.stopping=False
      self.lcd = self
      self.caller = Callback
      self.media = None #media
      self.mqttbroker = None

      self.message=""
      self.volumebar = False
      self.SleepTime = 1 # sleep less when volume shown
      self.MenuWaiting = False

      self.settings = Settings #Settings.Settings()

      self.checkmessage = 20 # Time between message updates

      #~ os.putenv('SDL_VIDEODRIVER','fbcon')
      #~ os.putenv('SDL_FBDEV','/dev/fb1')
      #~ os.putenv('SDL_MOUSEDRV','TSLIB')
      #~ os.putenv('SDL_MOUSEDEV','/dev/input/touchscreen')

      self.tftScreen = pygame.display.set_mode((SCREEN_WIDTH,SCREEN_HEIGHT))
      pygame.mouse.set_visible(False)

      # Fill with black
      self.tftScreen.fill((0,0,0))
      pygame.display.update()

      self.oldExtraText = ""
      self.ExtraTextoffset = 0
      self.oldExtrawidth = 0

      #~ fontlist = pygame.font.get_fonts()
      #~ for fontname in fontlist:
          #~ print fontname

      self.CurrentVolume = int(self.settings.get('volumepercent'))
      self.VisibleVolume = self.CurrentVolume
      self.ClockFontName = None
      self.newvolume = self.CurrentVolume


      self.ChooseFonts()
      #~ self.font_normal_bold.set_italic(True)

      self.weather = None #weather

      #Start menu thread (Later)
      #self.menu = MenuControl.MenuControl(self, media, weather, Callback)
      #self.menu.setDaemon(True)
      self.menu = None

      # self.lcd = LCDControl()
      # self.lcd.white()
      #~ self.setMessage("Booting up...")

      # self.rotor = InputWorker(self)
      # self.rotor.start()

      self.SegmentGap = 20
      self.segmentwidth = 60
      self.segmentheight = 60
      self.Clockformat = int(self.settings.get('clock_format'))
      self.pausedState = False
      self.LastTime = None
      self.Lasthourtens = -1
      self.Lasthoutunits = -1
      self.Lastmintens = -1
      self.Lastminunits = -1
      self.Lastsecstens = -1
      self.Lastsecsunits = -1
      self.VisibleVolume = False
      self.ExtraMessage = ""
      self.ClockColour = self.settings.getcolour('clock_colour')
      #~ self.ShowClock = True

   # def setBrightness(self,brightness):
      # We get passes a value from 0 - 15, which we need to scale to 0-255 before passing to LCDControl
      # colVal = int(255 * (float(brightness)/15))
      # self.lcd.setColour(colVal,colVal,colVal)

   def SetClockColour(self, colourValue): 
        # Input is 3 value csv String "R,G,B"
        # ClockColour variable is a 3 part tupple (R, G, B)

        try:
            colourRGB = colourValue.split(",")
            self.settings.set('clock_colour', str(colourRGB[0])+","+str(colourRGB[1])+","+str(colourRGB[2]))
        except ValueError:
            log.warn("Could not decode '%s' as colour. Using default",colourValue)
        self.ClockColour = self.settings.getcolour('clock_colour')
        if (self.mqttbroker != None):
            colourR, colourG, colourB = self.settings.getcolour('clock_colour')
            self.mqttbroker.publish("display/colourRGB", str(colourR)+","+str(colourG)+","+str(colourB))
            self.mqttbroker.publish("display/colorRGB", str(colourR)+","+str(colourG)+","+str(colourB))

   def publish(self):
        self.publishtext() #mqttbroker.publish("radio/text", self.ExtraMessage)      
        self.publishname() #mqttbroker.publish("radio/name", self.message + " ")
        self.publishcolour()

   def publishcolour(self):
        colourR, colourG, colourB = self.settings.getcolour('clock_colour')
        self.mqttbroker.publish("display/colourRGB", str(colourR)+","+str(colourG)+","+str(colourB))
        self.mqttbroker.publish("display/colorRGB", str(colourR)+","+str(colourG)+","+str(colourB))

   def publishtext(self):
        self.mqttbroker.publish("radio/text", self.ExtraMessage) 

   def publishname(self):
       self.mqttbroker.publish("radio/name", self.message + " ")

   def on_message(self, topic ,payload):
      method = topic[0:topic.find("/")] # before first "/"
      item = topic[topic.rfind("/")+1:]   # after last "/"
      log.info("TFT method='%s', item='%s'", method, item)
      done = False
      try:
         if (method == "display"):
            if (item == "colourrgb") or (item == "colorrgb"):
                log.debug("colour = '%s'", payload)
                #RGBcolour = payload.split(",")
                try:
                    self.SetClockColour(payload)
                    #self.settings.set('clock_colour', str(RGBcolour[0])+","+str(RGBcolour[1])+","+str(RGBcolour[2]))
                    #self.ClockColour = self.settings.getcolour('clock_colour')
                except ValueError:
                    log.warn("Could not decode %s as colour", payload)
                done = True

      except Exception as e:
         log.debug("on_message Error: %s" , e)
      return done # not for me  


   # From clock thread
   def ClockSegment(self, Segment, newvalue, oldSegmentvalue):
      y = 160 - (self.segmentheight)
      if (self.Clockformat == 6):
        x = 240 + ((-4 + Segment) * (self.segmentwidth + self.SegmentGap)) # + (Segment * (self.segmentwidth + self.SegmentGap))
      else:
        x = 240 + int((-2.5 + Segment) * (self.segmentwidth + self.SegmentGap)) # + (Segment * (self.segmentwidth + self.SegmentGap))

      if oldSegmentvalue != newvalue:
         if oldSegmentvalue != -1:
            self.lcd.Segmentdigit(x,y,(0,0,0), oldSegmentvalue, self.segmentwidth, self.segmentheight,8)

         self.lcd.Segmentdigit(x,y,self.ClockColour, newvalue, self.segmentwidth, self.segmentheight,8)

      return newvalue

   def paused(self, State):
        self.pausedState = State
        if (self.pausedState == False):
            self.Lasthourtens = -1
            self.Lasthoutunits = -1
            self.Lastmintens = -1
            self.Lastminunits = -1
            self.Lastsecstens = -1
            self.Lastsecsunits = -1
            self.Clockformat = int(self.settings.get('clock_format'))
            if (self.Clockformat == 4):
                self.segmentwidth = 60
                self.segmentheight = 60
            else:
                self.segmentwidth = 40
                self.segmentheight = 40

   def SetExtraMessage(self,NewMessage, CheckInterval = -1):
        self.ExtraMessage = NewMessage
        if (CheckInterval != -1) :
            self.checkmessage = CheckInterval
        if (self.mqttbroker != None):
            self.publishtext()

   def AddToExtraMessage(self,NewMessage, CheckInterval = -1):
        self.ExtraMessage += NewMessage
        if (CheckInterval != -1) :
            self.checkmessage = CheckInterval
        if (self.mqttbroker != None):
            self.publishtext()

   def SetConfig(self, alarmThread, media, weather, brightnessthreadptr, mqttbroker):  #Remaining info to allow startup
      self.alarmThread = alarmThread
      self.media = media
      self.weather = weather
      self.brightness = brightnessthreadptr
      # Startup Menu Thread
      self.menu = MenuControl.MenuControl(self, self.media, self.weather, self.caller, self.brightness)
      #self.menu.setDaemon(True)
      self.mqttbroker = mqttbroker

   def ChooseFonts(self):
      if (self.settings.getorset('menu_font','') == ""):
          MenuFontName = None
          getfont = None #pygame.font.match_font(MenuFontName)
          getfont_bold = None #pygame.font.match_font(MenuFontName, True)
          fontsize = 42
      else:
          MenuFontName = self.settings.get('menu_font')
          getfont = pygame.font.match_font(MenuFontName)
          getfont_bold = pygame.font.match_font(MenuFontName, True)
          fontsize = 32

      self.font_normal = pygame.font.Font(getfont,fontsize)
      self.font_normal_bold = pygame.font.Font(getfont_bold,fontsize)
      self.font_large = pygame.font.Font(getfont,50)
      self.font_largeButton = pygame.font.Font(getfont,90)

      if (self.settings.getorset('clock_font','dseg7modern') == ""):
            self.ClockFontName = None
            self.font_big = pygame.font.Font(None,130)
      else:
            self.ClockFontName = self.settings.get('clock_font')
            getfont = pygame.font.match_font(self.ClockFontName) # "dseg14modern")
            self.font_big = pygame.font.Font(getfont,130)

   def SetBigMessage(self,newMessage,center=False, colour = (255,255,255), ExtraText= "" ):
     # ExtraText will scroll along the bottom of the screen if its too long
     # returns true if this should happen (Need to call this more often in that case)
     area = []
     if newMessage != self.message: # Clear screen and put on it the new message
         self.message = newMessage
         #area =
         self.tftScreen.fill((0,0,0))
         text_surface = self.font_big.render(newMessage, True, colour)
         rect = text_surface.get_rect(center=(SCREEN_WIDTH/2,SCREEN_HEIGHT/2))
         area.append( self.tftScreen.blit(text_surface,rect))

     if (self.volumebar == True):
        if (abs(self.newvolume - self.CurrentVolume) > 1):
            area.append(self.VolumeSlider(self.CurrentVolume, colours.BLACK))
            self.CurrentVolume = self.newvolume
            #~ self.VolumeSlider(self.CurrentVolume, colours.GREEN)
        area.append(self.VolumeSlider(self.CurrentVolume, colours.GREEN))

     if (ExtraText != ""):
        #if (ExtraText != self.oldExtraText):
            #self.oldExtraText = ExtraText
        lineheight = self.font_normal.get_linesize()
        area.append(pygame.draw.rect(self.tftScreen,colours.BLACK,(0,SCREEN_HEIGHT-lineheight,SCREEN_WIDTH,lineheight)))
            #self.oldExtrawidth = text_surface.get_width()

        text_surface = self.font_normal.render(ExtraText, True, colour)
        rect = text_surface.get_rect(left=10-self.ExtraTextoffset,bottom=SCREEN_HEIGHT)
        area.append( self.tftScreen.blit(text_surface,rect))

        # If we have extra text work out how long it is for scrolling
        if (ExtraText != self.oldExtraText):
            self.ExtraTextoffset = -1
            self.oldExtraText = ExtraText
            self.oldExtrawidth = text_surface.get_width()
            if self.oldExtrawidth > self.tftScreen.get_width():
                self.ExtraTextoffset = 0

                #self.oldExtrawidth = self.oldExtrawidth + self.tftScreen.get_width()
                #~ log.debug("big text %d", self.oldExtrawidth)
        if self.ExtraTextoffset != -1:
            self.ExtraTextoffset += 2
            if self.ExtraTextoffset > self.oldExtrawidth:
                self.ExtraTextoffset = 0
     pygame.display.update(area)

     # Return True if we have scrolling extra text
     return (self.ExtraTextoffset != -1)

   def Segmentdigit(self,x,y,colour, newdigit,width=20,height=40,linewidth=4):
      #~ if (self.ClockFontName != None):
            #~ if (newdigit == 10):
                #~ newdigit = ":"
            #~ else:
                #~ newdigit = str(newdigit)
            #~ text_surface = self.font_big.render(newdigit, True, colour)
            #~ rect = text_surface.get_rect(left=x,top=y)
            #~ self.tftScreen.blit(text_surface,rect)
      #~ else:

      if newdigit == 0:
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x+width,y],[x+width,y+height+height],[x,y+height+height],[x,y]],linewidth)
      elif newdigit == 1:
         pygame.draw.lines(self.tftScreen,colour,False,[[x+width,y],[x+width,y+height+height]],linewidth)
      elif newdigit == 2:
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x+width,y],[x+width,y+height],[x,y+height],[x,y+height+height],[x+width,y+height+height]],linewidth)
      elif newdigit == 3:
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x+width,y],[x+width,y+height+height],[x,y+height+height]],linewidth)
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y+height],[x+width,y+height]],linewidth)
      elif newdigit == 4:
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x,y+height],[x+width,y+height],[x+width,y+height+height]],linewidth)
         pygame.draw.lines(self.tftScreen,colour,False,[[x+width,y],[x+width,y+height]],linewidth)
      elif newdigit == 5:
         pygame.draw.lines(self.tftScreen,colour,False,[[x+width,y],[x,y],[x,y+height],[x+width,y+height],[x+width,y+height+height],[x,y+height+height]],linewidth)
      elif newdigit == 6:
         pygame.draw.lines(self.tftScreen,colour,False,[[x+width,y],[x,y],[x,y+height+height],[x+width,y+height+height],[x+width,y+height],[x,y+height],[x,y+height+height]],linewidth)
      elif newdigit == 7:
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x+width,y],[x+width,y+height+height]],linewidth)
      elif newdigit == 8:
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x+width,y],[x+width,y+height+height],[x,y+height+height],[x,y]],linewidth)
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y+height],[x+width,y+height]],linewidth)
      elif newdigit == 9:
         pygame.draw.lines(self.tftScreen,colour,False,[[x+width,y+height],[x,y+height],[x,y],[x+width,y],[x+width,y+height+height],[x,y+height+height]],linewidth)
      elif newdigit == 10:
         pygame.draw.circle(self.tftScreen,colour, [x+int(width/2),y+int(height/2)], linewidth)
         pygame.draw.circle(self.tftScreen,colour, [x+int(width/2),y+int(height/2)+height], linewidth)
      elif (newdigit != -1):
         pygame.draw.lines(self.tftScreen,colour,False,[[x,y],[x+width,y],[x+width,y+height],[x,y+height],[x,y+height+height]],linewidth)

      pygame.display.flip()

   def setMessage(self,newMessage,center=False, colour = colours.RED):
     if newMessage != self.message:
        self.message = newMessage
        if (self.mqttbroker != None):
            self.publishname()

     area = self.tftScreen.fill((0,0,0))
     text_surface = self.font_normal.render(newMessage, True, colour)
     rect = text_surface.get_rect(center=(240,160))
     area = area.union(self.tftScreen.blit(text_surface,rect))
     if (self.volumebar == True):
        if (abs(self.newvolume - self.CurrentVolume) > 1):
            area = area.union(self.VolumeSlider(self.CurrentVolume, colours.BLACK))
            self.CurrentVolume = self.newvolume
            #~ self.VolumeSlider(self.CurrentVolume, GREEN)
        area = area.union(self.VolumeSlider(self.CurrentVolume, colours.GREEN))
     pygame.display.update(area)
     #~ self.ShowClock = False

   def DisplayMenu(self, Title, newMessage, colour = colours.RED, Highlight = -1, MenuValues = None, highlightcolour = colours.BLUE, ExtraMessage = "", displayoffset = 0):
     self.tftScreen.fill((0,0,0))
     lineno=0
     yoffset = 5 + displayoffset
     leftMargin = 5
     MenuValuesMargin = 240
     noofvalues = -1
     if MenuValues != None:
         noofvalues = len(MenuValues)
     self.showvolume(False)
     #log.debug ("Displaying %s", Title)
     # find menu items width
     listwidth = 0
     lineheight = self.font_normal.get_linesize()
     for textline in newMessage:
        valuewidth, valueheight = self.font_normal.size(textline)
        #if (valueheight > fontlineheight):
        #    fontlineheight = valueheight
        if (valuewidth > listwidth):
            listwidth = valuewidth

     if (Title != ""):
        text_surface = self.font_normal.render(Title, True, highlightcolour)
        rect = text_surface.get_rect(left=5,top=yoffset + (lineheight * lineno))
        self.tftScreen.blit(text_surface,rect)
        yoffset = yoffset + lineheight
        leftMargin = 20

     # where to put any values
     MenuValuesMargin = leftMargin + listwidth + 10 # gap

     # Display Each menu item and any values
     for textline in newMessage:
        if (Highlight == lineno):
            text_surface = self.font_normal_bold.render(textline, True, highlightcolour)
        else:
            text_surface = self.font_normal.render(textline, True, colour)
        rect = text_surface.get_rect(left=leftMargin,top=yoffset + (lineheight * lineno))
        self.tftScreen.blit(text_surface,rect)

        # Display menu items value if supplied
        if (MenuValues != None) and (lineno < noofvalues):
            text_surface = self.font_normal.render(MenuValues[lineno], True, colour)
            rect = text_surface.get_rect(left=MenuValuesMargin,top=yoffset + (lineheight * lineno))
            self.tftScreen.blit(text_surface,rect)
        lineno = lineno + 1

     # Always have "Back" as the last item
     #if (textline != "Back"):
     #   text_surface = self.font_normal.render("Back", True, colour)
     #   rect = text_surface.get_rect(left=leftMargin,top=yoffset + (self.font_normal.get_linesize() * lineno))
     #   self.tftScreen.blit(text_surface,rect)
     #   lineno = lineno + 1

     # Extra Info. Needa better place for this!
     if (ExtraMessage != ""):
        text_surface = self.font_normal.render(ExtraMessage, True, colour)
        rect = text_surface.get_rect(left=240,top=yoffset + (lineheight * lineno))
        self.tftScreen.blit(text_surface,rect)
        lineno = lineno + 1
     pygame.display.update()
     iSize = (lineheight * (lineno+1)) - SCREEN_HEIGHT
     if iSize < 0:
         iSize = 0
     return lineheight, iSize

   def DisplayLabel(self, x,y,Text,colour = colours.RED):

     if (Text != ""):
        text_surface = self.font_normal.render(Text, True, colour)
        if (x == SCREEN_WIDTH): # center it
            Textwidth, Textheight = self.font_normal.size(Text)
            x = (SCREEN_WIDTH/2) - (Textwidth/2)
        if (x<0) and (y>0):
            rect = text_surface.get_rect(right=SCREEN_WIDTH+x,top=y)
        elif (x<0) and (y<0):
            rect = text_surface.get_rect(right=SCREEN_WIDTH+x,bottom=SCREEN_HEIGHT+y)
        elif (x>0) and (y<0):
            rect = text_surface.get_rect(left=x,bottom=SCREEN_HEIGHT+y)
        else:
            rect = text_surface.get_rect(left=x,top=y)
        area = self.tftScreen.blit(text_surface,rect)
        return area
     return None

   def DisplayButton(self, x,y,Text,Action = None,colour = colours.WHITE, backcolour = colours.GREY):

     if (Text != ""):
        Textwidth, Textheight = self.font_normal.size(Text)
        Textwidth += 8
        Textheight +=8
        text_surface = self.font_normal.render(Text, True, colour)
        #pygame.draw.rect(text_surface,border,(0,0,Textwidth-1,Textheight-1,1))
        area = []
        if (x<0) and (y<0):
            rect = text_surface.get_rect(right=SCREEN_WIDTH+x+4,bottom=SCREEN_HEIGHT+y-4, width=Textwidth, height=Textheight)
            area = pygame.draw.rect(self.tftScreen,backcolour,(SCREEN_WIDTH-Textwidth+x,SCREEN_HEIGHT-Textheight+y,Textwidth-1,Textheight-1),0)
            pygame.draw.rect(self.tftScreen,colour,(SCREEN_WIDTH-Textwidth+x,SCREEN_HEIGHT-Textheight+y,Textwidth-1,Textheight-1),1)
        else:
            rect = text_surface.get_rect(left=x+4,top=y+4, width=Textwidth, height=Textheight)
            area = pygame.draw.rect(self.tftScreen,backcolour,(x,y,Textwidth-1,Textheight-1),0)
            pygame.draw.rect(self.tftScreen,colour,(x,y,Textwidth-1,Textheight-1),1)
        area = area.union(self.tftScreen.blit(text_surface,rect))


        return [3, area, Action, x, y]

     return [None, Action]

   def DisplayBigButton(self, x,y,Text,Action = None,colour = colours.WHITE, backcolour = colours.GREY):

     if (Text != ""):
        Textwidth, Textheight = self.font_largeButton.size(Text)
        Textwidth += 8
        Textheight +=8
        text_surface = self.font_largeButton.render(Text, True, colour)
        #pygame.draw.rect(text_surface,border,(0,0,Textwidth-1,Textheight-1,1))
        area = []
        if x >= SCREEN_WIDTH:
            x = (SCREEN_WIDTH/2)-(Textwidth/2)

        if (x<0) and (y<0):
            rect = text_surface.get_rect(right=SCREEN_WIDTH+x+4,bottom=SCREEN_HEIGHT+y-4, width=Textwidth, height=Textheight)
            area = pygame.draw.rect(self.tftScreen,backcolour,(SCREEN_WIDTH-Textwidth+x,SCREEN_HEIGHT-Textheight+y,Textwidth-1,Textheight-1),0)
            pygame.draw.rect(self.tftScreen,colour,(SCREEN_WIDTH-Textwidth+x,SCREEN_HEIGHT-Textheight+y,Textwidth-1,Textheight-1),1)

        else:
            rect = text_surface.get_rect(left=x+4,top=y+4, width=Textwidth, height=Textheight)
            area = pygame.draw.rect(self.tftScreen,backcolour,(x,y,Textwidth-1,Textheight-1),0)
            pygame.draw.rect(self.tftScreen,colour,(x,y,Textwidth-1,Textheight-1),1)
        area = area.union(self.tftScreen.blit(text_surface,rect))


        return [3, area, Action, x, y]

     return [None, Action]


   def DisplayImageButton(self, x,y,ImageName,Action = None,colour = colours.WHITE, backcolour = colours.GREY, ImagePath = "/usr/share/icons/Adwaita/48x48/actions/"):
     # Returns a list of [Rect, Action ptr]

     if (ImageName != ""):
        if ImagePath == "":
            home_dir = os.path.expanduser('~')
            Image = os.path.join(home_dir, ImageName)
        elif ImagePath[0] == ".":
            home_dir = os.path.expanduser('~')
            Image = os.path.join(home_dir, ImagePath[1:])
            Image = os.path.join(home_dir, ImageName)

        else:
            Image = os.path.join(ImagePath, ImageName)
        ImageSurface = pygame.image.load(Image)
        Imagewidth, Imageheight = ImageSurface.get_size()
        Imagewidth += 8
        Imageheight +=8
        #pygame.draw.rect(text_surface,border,(0,0,Textwidth-1,Textheight-1,1))
        outerarea = None
        if (x<0) and (y<0):
            rect = ImageSurface.get_rect(right=SCREEN_WIDTH+x+4,bottom=SCREEN_HEIGHT+y-4, width=Imagewidth, height=Imageheight)
            if colour != None:
                outerarea = pygame.draw.rect(self.tftScreen,colour,(SCREEN_WIDTH-Imagewidth+x,SCREEN_HEIGHT-Imageheight+y,Imagewidth-1,Imageheight-1),0)
            if backcolour != None:
                pygame.draw.rect(self.tftScreen,backcolour,(SCREEN_WIDTH-Imagewidth+x,SCREEN_HEIGHT-Imageheight+y,Imagewidth-1,Imageheight-1),1)
        else:
            rect = ImageSurface.get_rect(left=x+4,top=y+4, width=Imagewidth, height=Imageheight)
            if colour != None:
                outerarea = pygame.draw.rect(self.tftScreen,colour,(x,y,Imagewidth-1,Imageheight-1),1)
            if backcolour != None:
                pygame.draw.rect(self.tftScreen,backcolour,(x,y,Imagewidth-1,Imageheight-1),0)
        area = (self.tftScreen.blit(ImageSurface,rect))
        if outerarea != None:
            area = area.union(outerarea)
        return [3, area, Action,x,y]

     return [3, None, Action,x,y]


   def ControlRadio(self, colour = colours.WHITE):

    def ControlRadioPlay(Control):
        if (self.media.playerActive() == False):
            self.media.playStation(Controls[3][KEY_SelectedValue])
            return "Playing"
        else:
            return "Already Playing"

    def ControlRadioStop(Control):
        if (self.media.playerActive() != False):
            self.media.stopPlayer()
            return "Stopped"
        else:
            return "Already Stopped"

    def ControlRadioPause(Control):
        if self.media.pausePlayer() == 1:
            log.info("Pause")
            return "Paused"
        else:
            log.info("UnPause")
            return "Playing"

    def ControlRadioClose(Control):
        self.MenuWaiting = False
        return "Closing Menu"

    def ControlRadioSetStation(Control):
        # Control[KEY_SelectedValue]
        self.settings.set('station', Control[KEY_SelectedValue])
        return self.settings.getStationName(self.settings.getInt('station'))

    self.caller.pauseclock(True)
    self.tftScreen.fill((0,0,0))

    dimcolour = (colour[0]/2, colour[1]/2, colour[2]/2)

    Controls = []

    # Controls along the bottom of the screen
    x = 30
    y = SCREEN_HEIGHT - 80

    #~ ControlPlay = self.DisplayImageButton(x,y,"media-playback-start.png", ControlRadioPlay)
    ControlPlay = self.DisplayImageButton(x,y,"play.png", ControlRadioPlay, colour = None, backcolour=None, ImagePath ="/home/pi/Images")
    Controls.append(ControlPlay)

    x += ControlPlay[1][2]+20
    #~ ControlStop = self.DisplayImageButton(x,y,"media-playback-stop.png", ControlRadioStop)
    ControlStop = self.DisplayImageButton(x,y,"stop.png", ControlRadioStop, colour = None, backcolour=None, ImagePath ="/home/pi/Images")
    Controls.append(ControlStop)

    x += ControlStop[1][2]+20
    ControlPause = self.DisplayImageButton(x,y,"pause.png", ControlRadioPause, colour = None, backcolour=None, ImagePath ="/home/pi/Images")
    Controls.append(ControlPause)

    x += ControlPause[1][2]+20

    #~ self.DisplayLabel(150,100,"Station",colours.GREEN)

    #SxtationList = []
    #for stationname in self.settings.STATIONS:
    #    SxtationList.append(stationname['name'])
    DefaultStation = self.settings.getInt('station')
    radioselector = self.DisplaySelectValueFromList("",75, 120, DefaultStation, self.settings.getStationList(), colour, ControlRadioSetStation)

    Controls.append(list(radioselector))

    CloseArea  = self.DisplayButton(-30,-30,"Close", ControlRadioClose)
    Controls.append(CloseArea)

    pygame.display.update()
    NewValues = self.HandleGUI(Controls, colour, dimcolour, Statusx = SCREEN_WIDTH, Statusy = 20)
    log.info(NewValues)
    self.caller.pauseclock(False)

   def HandleGUI(self,Controls, colour = colours.WHITE, dimcolour = colours.GREY, Statusx = -20, Statusy = 20):
    StartDrag = -1 # tapped on scroll value and dragged
    self.MenuWaiting = True
    menuTimeout = 0
    LOOP_TIME=float(0.1)
    gadgetcount = len(Controls)-1
    calcTimeout = self.settings.getInt('menu_timeout')*(1/LOOP_TIME) # We're unlikely to update this on the fly
    #~ gadgetcount = len(valueListSize)
    controlcount = len(Controls)

    StatusMessage = ""
    LastStatusMessage = ""
    LastStatusarea = None
    while (self.MenuWaiting == True) or (self.stopping == True):
        time.sleep(LOOP_TIME)
        if menuTimeout > calcTimeout:
            #self.exitMenu()
            self.MenuWaiting = False
        else:
            menuTimeout = menuTimeout + 1

        for event in pygame.event.get():
            if (event.type is QUIT):
               self.MenuWaiting = False

            elif (event.type is MOUSEBUTTONUP) and (StartDrag == -1):
                menuTimeout = 0
                area = None

                for ControlNo in range(0,controlcount):
                    Control = Controls[ControlNo]
                    if Control[KEY_ControlType] == 3: # Text or Image based button

                        if (Control[1].collidepoint(event.pos)) and (Control[2] != None):
                            #~ Button in loop
                            StatusMessage = Control[2](Control)

                    elif (Control[KEY_ControlType] == 1) or (Control[KEY_ControlType] == 2): # Scrollable selector
                        # ControlType, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight, SelectedValue, OldSelectedValue, MinValue, MaxValue
                        area = None

                        if (Control[KEY_UpButtonarea].collidepoint(event.pos)):
                           if (Control[KEY_SelectedValue] < Control[KEY_MaxValue]): # valueListSize[button]):
                               Control[KEY_SelectedValue] += 1
                               area  = pygame.draw.polygon(self.tftScreen,dimcolour, Control[KEY_UpButton],0) # UpButtons[button]
                               ScrollDirection = +1
                        elif (Control[KEY_DownButtonarea].collidepoint(event.pos)):
                           if (Control[KEY_SelectedValue] > Control[KEY_MinValue]): # SelectedValues[button] > 0):
                               Controls[ControlNo][KEY_SelectedValue] -= 1
                               area = pygame.draw.polygon(self.tftScreen,dimcolour,Control[KEY_DownButton] ,0) # DownButtons[button]
                               ScrollDirection = -1

                        # we never get here as this is a scroll start point
                        #~ elif (Control[KEY_SelectButtonarea].collidepoint(event.pos)):
                            #~ log.info("Scroll in loop")
                            #~ StatusMessage = Control[KEYSelectAction](Control[KEY_SelectedValue])
                            #~ log.info("StatusMessage %s", StatusMessage)

                        if (Control[KEY_SelectedValue] != Control[KEY_OldSelectedValue]):
                            pygame.display.update(area) # draw button push
                            offset = 0
                            Controls[ControlNo][KEY_OldSelectedValue]= Control[KEY_SelectedValue]
                            # scroll the value surface under the select area the right number of values
                            #~ self.tftScreen.set_clip(SelectButtonareas[button])
                            self.tftScreen.set_clip(Control[KEY_SelectButtonarea])
                            while (offset < Control[KEY_fontlineheight]): #fontlineheights[button]):
                                rect = Control[KEY_scrollsurface].get_rect(left=Control[KEY_xs],top=Control[KEY_ys]-Control[KEY_yoffset])
                                area = self.tftScreen.blit(Control[KEY_scrollsurface],rect)
                                pygame.display.update(area)
                                offset = offset + 1
                                Control[KEY_yoffset] = Control[KEY_yoffset] + ScrollDirection
                                pygame.time.wait(3)
                            self.tftScreen.set_clip(None)
                            # Leave Shaded the scroll buttons at top and bottom of the list
                            if (Control[KEY_SelectedValue] == Control[KEY_MinValue]):
                                area = pygame.draw.polygon(self.tftScreen,dimcolour, Control[KEY_DownButton],0)
                            else:
                                area = pygame.draw.polygon(self.tftScreen,colour, Control[KEY_DownButton],0)
                            if (Control[KEY_SelectedValue] == Control[KEY_MaxValue]):
                                area = area.union(pygame.draw.polygon(self.tftScreen,dimcolour, Control[KEY_UpButton],0))
                            else:
                                area = area.union(pygame.draw.polygon(self.tftScreen,colour, Control[KEY_UpButton],0))
                            pygame.display.update(area)


            # if mid drag
            elif (StartDrag != -1):
               if (event.type is MOUSEMOTION):
                   dragchange = dragy - event.pos[1]
                   if abs(dragchange) > StartDrag[KEY_fontlineheight]:
                        movement = int(dragchange / StartDrag[KEY_fontlineheight])
                        Newplace = StartDrag[KEY_SelectedValue] + movement
                        if (Newplace < StartDrag[KEY_MinValue]):
                            Newplace = StartDrag[KEY_MinValue]
                        elif (Newplace >= StartDrag[KEY_MaxValue]):
                            Newplace = StartDrag[KEY_MaxValue]
                        #~ log.debug("scroll %d moves to %d", movement, Newplace)

                        StartDrag[KEY_SelectedValue] = Newplace

                        ScrollDirection = math.copysign(1,movement)
                        if StartDrag[KEY_OldSelectedValue] != StartDrag[KEY_SelectedValue]:
                            offset = 0
                            ChangeAmount = abs(StartDrag[KEY_SelectedValue] - StartDrag[KEY_OldSelectedValue]) # might be less then "movement"
                            StartDrag[KEY_OldSelectedValue] = StartDrag[KEY_SelectedValue]
                            self.tftScreen.set_clip(StartDrag[KEY_SelectButtonarea])
                            while (offset < (StartDrag[KEY_fontlineheight] * ChangeAmount)):
                                rect = StartDrag[KEY_scrollsurface].get_rect(left=StartDrag[KEY_xs],top=StartDrag[KEY_ys]-StartDrag[KEY_yoffset])
                                area = self.tftScreen.blit(StartDrag[KEY_scrollsurface],rect)
                                pygame.display.update(area)
                                offset = offset + 1
                                StartDrag[KEY_yoffset] = StartDrag[KEY_yoffset] + ScrollDirection
                                pygame.time.wait(3)
                            self.tftScreen.set_clip(None)
                            # Leave Shaded the scroll buttons at top and bottom of the list
                            if (StartDrag[KEY_SelectedValue] == StartDrag[KEY_MinValue]):
                                area = pygame.draw.polygon(self.tftScreen,dimcolour, StartDrag[KEY_DownButton],0)
                            else:
                                area = pygame.draw.polygon(self.tftScreen,colour, StartDrag[KEY_DownButton],0)
                            if (StartDrag[KEY_SelectedValue] == StartDrag[KEY_MaxValue]):
                                area = area.union(pygame.draw.polygon(self.tftScreen,dimcolour, StartDrag[KEY_UpButton],0))
                            else:
                                area = area.union(pygame.draw.polygon(self.tftScreen,colour, StartDrag[KEY_UpButton],0))
                            pygame.display.update(area)
                        dragy = event.pos[1]

               elif (event.type is MOUSEBUTTONUP):
                    StartDrag = -1
                    for ControlNo in range(0,controlcount):
                        Control = Controls[ControlNo]
                        # if still in select area, must be a tap
                        if (Control[KEY_ControlType] == 1) or (Control[KEY_ControlType] == 2):
                            if (Control[KEY_SelectButtonarea].collidepoint(event.pos)) and (Control[KEYSelectAction] != None):
                                #~ log.debug("Tap Scroll in loop")
                                StatusMessage = Control[KEYSelectAction](Control)
                   #~ log.debug("End drag")


            elif (event.type is MOUSEBUTTONDOWN):
                menuTimeout = 0
                area = None

                # Check in start of scroll areas
                for ControlNo in range(0,controlcount):
                    Control = Controls[ControlNo]
                    #~ for Control in Controls
                    if (Control[KEY_ControlType] == 1) or (Control[KEY_ControlType] == 2): # Scrollable selector
                        area = None
                        if (Control[KEY_SelectButtonarea].collidepoint(event.pos)):
                            #~ log.debug("Started dragging")
                            dragx, dragy = event.pos
                            StartDrag = Control

        if StatusMessage != "":
            if LastStatusMessage != StatusMessage:
                if LastStatusarea != None:
                    area = pygame.draw.rect(self.tftScreen,(0,0,0),LastStatusarea,0)
                    #~ pygame.draw.rect(self.tftScreen,(0,0,0),(x,y,Textwidth-1,Textheight-1),1)
                    #~ area = area.union(self.tftScreen.blit(text_surface,rect))
                    pygame.display.update(area)

            LastStatusMessage = StatusMessage
            LastStatusarea = self.DisplayLabel(Statusx, Statusy, StatusMessage, colours.GREEN)
            pygame.display.update(LastStatusarea)


    currentValues = []
    for ControlNo in range(0,controlcount):
        Control = Controls[ControlNo]
        if Control[KEY_ControlType] == 3: # Text or Image based button
            currentValues.append("")

        elif (Control[KEY_ControlType] == 1) or (Control[KEY_ControlType] == 2): # Scrollable selector
            currentValues.append(Control[KEY_SelectedValue])

    self.tftScreen.fill((0,0,0))
    pygame.display.update()

    return currentValues


   def ChangeAlarmSettings(self,alarmno):
    """Allows changing of daily alarm settings"""

    def ChangeAlarmSettingsSave(Control):
        # Control[KEY_SelectedValue]
        log.info("set %d is %s:%s%s with '%s'", alarmno, str(Controls[0][KEY_SelectedValue]), str(Controls[1][KEY_SelectedValue]),
            str(Controls[2][KEY_SelectedValue]), str(Controls[3][KEY_SelectedValue]))
        if int(Controls[0][KEY_SelectedValue]) < 10:
            self.settings.set('alarm_weekday_' + str(alarmno),"0" + str(Controls[0][KEY_SelectedValue]) + ":" + str(Controls[1][KEY_SelectedValue]) + str(Controls[2][KEY_SelectedValue]))
        else:
            self.settings.set('alarm_weekday_' + str(alarmno),str(Controls[0][KEY_SelectedValue]) + ":" + str(Controls[1][KEY_SelectedValue]) + str(Controls[2][KEY_SelectedValue]))
        self.settings.set('alarm_station_' + str(alarmno), str(Controls[3][KEY_SelectedValue]))
        #~ Control[KEY_OldSelectedValue] = Control[KEY_SelectedValue]
        self.MenuWaiting = False
        return "Saveing & Closing Menu"

    def ChangeAlarmSettingsCancel(Control):
        self.MenuWaiting = False
        return "Closing Menu"

    FullDaynames = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    colour  = colours.WHITE
    self.tftScreen.fill((0,0,0))

    # give it a title of the day
    self.DisplayLabel(SCREEN_WIDTH,5,"Alarm settings for " + FullDaynames[alarmno],colours.GREEN)

    valuewidth, valueheight = self.font_large.size("23")

    alarmtime = self.settings.get('alarm_weekday_' + str(alarmno))
    alarmhours,alarmminutes = alarmtime.split(":")
    alarmmintens  = int(int(alarmminutes) / 10)
    alarmminsunits = int(alarmminutes) % 10


    # This needs to be a station number
    alarmstation = int(self.settings.get('alarm_station_' + str(alarmno)))
    #~ AllButtons = []
    Controls = []

    #~ UpButtons = []
    #~ UpButtonareas = []
    #~ DownButtons = []
    #~ DownButtonareas = []
    #~ SelectButtonareas = []
    #~ scrollsurfaces = []
    #~ fontlineheights = []
    #~ SelectedValues = []
    #~ OldSelectedValues = []
    #~ valueListSize = []
    #~ xs = []
    #~ ys = []

    #~ valuewidth, valueheight = self.font_large.size("23")

    y = 80
    x = 120
    #~ hourselector = self.DisplayScrollValue(x,y,int(alarmhours),0,23,colour)
    hourlist = []
    for anhour in range(0,24):
        hourlist.append(str(100+anhour)[1:])
    hourselector = self.DisplaySelectValueFromList("",x, y, int(alarmhours), hourlist, colour)
    Controls.append(list(hourselector))

    #~ xs.append(x)
    #~ ys.append(y)
    #~ #ControlType, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight = hourselector
    #~ UpButtonareas.append(hourselector[1])
    #~ UpButtons.append(hourselector[2])
    #~ DownButtonareas.append(hourselector[3])
    #~ DownButtons.append(hourselector[4])
    #~ SelectButtonareas.append(hourselector[5])
    #~ scrollsurfaces.append(hourselector[6])
    #~ fontlineheights.append(hourselector[7])
    #~ SelectedValues.append(int(alarmhours))
    #~ OldSelectedValues.append(int(alarmhours))
    #~ valueListSize.append(23)

    x += hourselector[5][2] + 8
    #~ x += valuewidth + 5
    #~ valuewidth, valueheight = self.font_large.size("8")
    #~ tensselector = self.DisplayScrollValue(x,y,int(alarmmintens),0,5,colour)
    tensselector = self.DisplaySelectValueFromList("",x, y, int(alarmmintens), ["0","1","2","3","4","5"], colour)
    Controls.append(list(tensselector))

    #~ xs.append(x)
    #~ ys.append(y)
    #~ # ControlType, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight = tensselector
    #~ UpButtonareas.append(tensselector[1])
    #~ UpButtons.append(tensselector[2])
    #~ DownButtonareas.append(tensselector[3])
    #~ DownButtons.append(tensselector[4])
    #~ SelectButtonareas.append(tensselector[5])
    #~ scrollsurfaces.append(tensselector[6])
    #~ fontlineheights.append(tensselector[7])
    #~ SelectedValues.append(int(alarmmintens))
    #~ OldSelectedValues.append(int(alarmmintens))
    #~ valueListSize.append(5)

    x += tensselector[5][2] + 8
    #~ x += valuewidth + 5
    #~ unitsselector = self.DisplayScrollValue(x,y,int(alarmminsunits),0,9,colour)
    unitsselector = self.DisplaySelectValueFromList("",x, y, int(alarmminsunits), ["0","1","2","3","4","5","6","7","8","9"], colour)
    Controls.append(list(unitsselector))

    #~ xs.append(x)
    #~ ys.append(y)
    #~ # ControlType, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight = unitsselector
    #~ UpButtonareas.append(unitsselector[1])
    #~ UpButtons.append(unitsselector[2])
    #~ DownButtonareas.append(unitsselector[3])
    #~ DownButtons.append(unitsselector[4])
    #~ SelectButtonareas.append(unitsselector[5])
    #~ scrollsurfaces.append(unitsselector[6])
    #~ fontlineheights.append(unitsselector[7])
    #~ SelectedValues.append(int(alarmminsunits))
    #~ OldSelectedValues.append(int(alarmminsunits))
    #~ valueListSize.append(9)

    self.DisplayLabel(20,140,"Station",colours.GREEN)

    StationList = self.settings.getAllStationInfo()
    #for stationname in self.settings.STATIONS:
    #    StationList.append(stationname['name'])
    radioselector = self.DisplaySelectValueFromList("",10, 220, alarmstation, StationList, colour)
    Controls.append(list(radioselector))

    #~ xs.append(70)
    #~ ys.append(190)
    #~ # ControlType, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight = radioselector
    #~ UpButtonareas.append(radioselector[1])
    #~ UpButtons.append(radioselector[2])
    #~ DownButtonareas.append(radioselector[3])
    #~ DownButtons.append(radioselector[4])
    #~ SelectButtonareas.append(radioselector[5])
    #~ scrollsurfaces.append(radioselector[6])
    #~ fontlineheights.append(radioselector[7])
    #~ SelectedValues.append(alarmstation)
    #~ OldSelectedValues.append(alarmstation)
    #~ valueListSize.append(len(StationList)-1)

    SaveArea = self.DisplayButton(-5,-55,"Save", ChangeAlarmSettingsSave)
    Controls.append(SaveArea)

    CancelArea  = self.DisplayButton(-5,-5,"Cancel", ChangeAlarmSettingsCancel)
    Controls.append(CancelArea)

    pygame.display.update()

    dimcolour = (colour[0]/2, colour[1]/2, colour[2]/2)

    menuwaiting = True
    menuTimeout = 0
    ScrollDirection = 0

    LOOP_TIME=float(0.1)
    calcTimeout = self.settings.getInt('menu_timeout')*(1/LOOP_TIME) # We're unlikely to update this on the fly

    NewValues = self.HandleGUI(Controls, colour, dimcolour)
    if (alarmtime != self.settings.get('alarm_weekday_' + str(alarmno))) or (alarmstation != int(self.settings.get('alarm_station_' + str(alarmno)))):
        log.info("alarm %d updated", alarmno)
        return True
    else:
        return False

    return False

    if False:
        gadgetcount = len(UpButtonareas)

        yoffsets = []
        currentValues = []
        area = [] # rect list that needs updating
        for button in range(0,gadgetcount):
            #~ OldSelectedValues.append(SelectedValues[button])
            yoffsets.append(fontlineheights[button]*SelectedValues[button])
            currentValues.append(SelectedValues[button])
            if (SelectedValues[button] == 0):
                area.append( pygame.draw.polygon(self.tftScreen,dimcolour, DownButtons[button],0))
            else:
                area.append( pygame.draw.polygon(self.tftScreen,colour, DownButtons[button],0))
            if (SelectedValues[button] == valueListSize[button]):
                area.append( pygame.draw.polygon(self.tftScreen,dimcolour, UpButtons[button],0))
            else:
                area.append( pygame.draw.polygon(self.tftScreen,colour, UpButtons[button],0))


        pygame.display.update(area)
        StartDrag = -1 # tapped on scroll value and dragged

        while (menuwaiting == True) or (self.stopping == True):
            time.sleep(LOOP_TIME)
            if menuTimeout > calcTimeout:
                #self.exitMenu()
                menuwaiting = False
            else:
                menuTimeout = menuTimeout + 1

            for event in pygame.event.get():
               if (event.type is QUIT):
                   menuwaiting = False

               elif (event.type is MOUSEBUTTONUP) and (StartDrag == -1):
                    menuTimeout = 0
                    area = None

                    for button in range(0,gadgetcount):
                        if (UpButtonareas[button].collidepoint(event.pos)):
                           if (SelectedValues[button] < valueListSize[button]):
                               SelectedValues[button] += 1
                               area  = pygame.draw.polygon(self.tftScreen,dimcolour, UpButtons[button],0)
                               PushButton = UpButtons[button]
                               ScrollDirection = 1
                               #time.sleep(0.1)
                               #~ log.info("down")
                        elif (DownButtonareas[button].collidepoint(event.pos)):
                           if (SelectedValues[button] > 0):
                               SelectedValues[button] -= 1
                               area = pygame.draw.polygon(self.tftScreen,dimcolour, DownButtons[button],0)
                               PushButton = DownButtons[button]
                               ScrollDirection = -1
                               #time.sleep(0.1)
                               #~ log.info("up")
                        #~ elif (SelectButtonareas[button].collidepoint(event.pos)):
                           #~ #menuwaiting = False
                           #~ currentValues[button] = SelectedValues[button]
                        elif (SaveArea[1].collidepoint(event.pos)):
                            menuwaiting = False
                            currentValues[button] = SelectedValues[button]
                        elif (CancelArea[1].collidepoint(event.pos)):

                            menuwaiting = False
                            currentValues = None

                        if area != None:
                            pygame.display.update(area)

                        if (SelectedValues[button] != OldSelectedValues[button]):
                            offset = 0
                            OldSelectedValues[button] = SelectedValues[button]
                            # scroll the value surface under the select area the right number of values
                            self.tftScreen.set_clip(SelectButtonareas[button])
                            while (offset < fontlineheights[button]):
                                rect = scrollsurfaces[button].get_rect(left=xs[button],top=ys[button]-yoffsets[button])
                                area = self.tftScreen.blit(scrollsurfaces[button],rect)
                                pygame.display.update(area)
                                offset = offset + 1
                                yoffsets[button] = yoffsets[button] + ScrollDirection
                                pygame.time.wait(3)
                            self.tftScreen.set_clip(None)
                            # Leave Shaded the scroll buttons at top and bottom of the list
                            if (SelectedValues[button] == 0):
                                area = pygame.draw.polygon(self.tftScreen,dimcolour, DownButtons[button],0)
                            else:
                                area = pygame.draw.polygon(self.tftScreen,colour, DownButtons[button],0)
                            if (SelectedValues[button] == valueListSize[button]):
                                area = area.union(pygame.draw.polygon(self.tftScreen,dimcolour, UpButtons[button],0))
                            else:
                                area = area.union(pygame.draw.polygon(self.tftScreen,colour, UpButtons[button],0))
                            pygame.display.update(area)

               # if mid drag
               elif (StartDrag != -1):
                   if (event.type is MOUSEMOTION):
                       dragchange = dragy - event.pos[1]
                       if abs(dragchange) > fontlineheights[StartDrag]:
                            movement = int(dragchange / fontlineheights[StartDrag])
                            Newplace = SelectedValues[StartDrag] + movement
                            if (Newplace < 0):
                                Newplace = 0
                            elif (Newplace >= valueListSize[StartDrag]):
                                Newplace = valueListSize[StartDrag]
                            #~ log.debug("scroll %d moves to %d", movement, Newplace)

                            SelectedValues[StartDrag] = Newplace
                            button = StartDrag
                            ScrollDirection = math.copysign(1,movement)
                            if OldSelectedValues[button] != SelectedValues[button]:
                                offset = 0
                                ChangeAmount = abs(SelectedValues[button] - OldSelectedValues[button]) # might be less then "movement"
                                OldSelectedValues[button] = SelectedValues[button]
                                self.tftScreen.set_clip(SelectButtonareas[button])
                                while (offset < (fontlineheights[button] * ChangeAmount)):
                                    rect = scrollsurfaces[button].get_rect(left=xs[button],top=ys[button]-yoffsets[button])
                                    area = self.tftScreen.blit(scrollsurfaces[button],rect)
                                    pygame.display.update(area)
                                    offset = offset + 1
                                    yoffsets[button] = yoffsets[button] + ScrollDirection
                                    pygame.time.wait(3)
                                self.tftScreen.set_clip(None)
                                # Leave Shaded the scroll buttons at top and bottom of the list
                                if (SelectedValues[button] == 0):
                                    area = pygame.draw.polygon(self.tftScreen,dimcolour, DownButtons[button],0)
                                else:
                                    area = pygame.draw.polygon(self.tftScreen,colour, DownButtons[button],0)
                                if (SelectedValues[button] == valueListSize[button]):
                                    area = area.union(pygame.draw.polygon(self.tftScreen,dimcolour, UpButtons[button],0))
                                else:
                                    area = area.union(pygame.draw.polygon(self.tftScreen,colour, UpButtons[button],0))
                                pygame.display.update(area)
                            dragy = event.pos[1]

                   elif (event.type is MOUSEBUTTONUP):
                       StartDrag = -1
                       #~ log.debug("End drag")


               elif (event.type is MOUSEBUTTONDOWN):
                    menuTimeout = 0
                    area = None
                    for button in range(0,gadgetcount):
                        if (SelectButtonareas[button].collidepoint(event.pos)):
                            #~ log.debug("Started dragging")
                            dragx, dragy = event.pos
                            StartDrag = button



        return currentValues #valueList[SelectedValue]


   # Scrollable number field
   def DisplayScrollValue(self, x, y, currentValue, minValue = 0, maxValue = 23, colour = colours.WHITE):
     fontlineheight = self.font_large.get_linesize()
     valuewidth, valueheight = self.font_large.size(str(maxValue))
     scrollheight = fontlineheight * (maxValue - minValue+1)
     valuewidth += 8

     if valuewidth < 40:
        valuewidth = 40
     scrollsurface = pygame.Surface((valuewidth, scrollheight))

     val = minValue
     ypos = 0
     while (val <= maxValue):
        text_surface = self.font_large.render(str(val), True, colour)
        rect = text_surface.get_rect(center=(valuewidth/2,ypos+(fontlineheight/2)))
        scrollsurface.blit(text_surface,rect)
        ypos = ypos + fontlineheight
        val = val + 1

     rect = scrollsurface.get_rect(left=x,top=y-(fontlineheight*(currentValue-minValue)))

     UpButton = ((x,y-4),(x+valuewidth,y-4),(x+(valuewidth/2),y-(fontlineheight/2)))
     UpButtonarea = pygame.Rect(x,y-4-(fontlineheight/2),valuewidth,(fontlineheight/2))

     DownButton = ((x,y+fontlineheight+3),(x+valuewidth,y+fontlineheight+3),(x+(valuewidth/2),y+fontlineheight+(fontlineheight/2)))
     DownButtonarea = pygame.Rect(x,y+fontlineheight+3,valuewidth,(fontlineheight/2))

     pygame.draw.polygon(self.tftScreen,colour,UpButton ,0)
     pygame.draw.rect(self.tftScreen,colour,(x-1,y-1,valuewidth+2,fontlineheight+2),1)
     #self.tftScreen.blit(scrollsurface,(0,-(fontlineheight*(currentValue-minValue))))
     SelectButtonarea = pygame.Rect(x,y,valuewidth, fontlineheight)
     self.tftScreen.set_clip(SelectButtonarea)
     self.tftScreen.blit(scrollsurface,rect)
     self.tftScreen.set_clip(None)
     pygame.draw.polygon(self.tftScreen,colour, DownButton,0)

     #~ log.debug("Displaying %d", currentValue)

     return [1,UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight,currentValue,currentValue,minValue,maxValue,x,y, fontlineheight*currentValue]


   def DisplaySelectValueFromList(self, Title, x, y, SelectedValue, valueList, colour = colours.WHITE, Action = None):
     # SelectedValue is a pointer to valuelist
     #self.tftScreen.fill((0,0,0))
     fontlineheight = self.font_large.get_linesize()
     listwidth = 0
     #~ Valno = 0
     overlap = fontlineheight/3
     dimcolour = (colour[0]/2, colour[1]/2, colour[2]/2)

     # Find widest and deepest value
     for oneval in valueList:
        valuewidth, valueheight = self.font_large.size(oneval)
        if (valueheight > fontlineheight):
            fontlineheight = valueheight
        if (valuewidth+12 > listwidth):
            listwidth = valuewidth+12
        #~ if (currentValue == oneval):
            #~ SelectedValue = Valno
        #~ Valno = Valno + 1

     listheight = fontlineheight * len(valueList)
     while (y - (fontlineheight) < 0):
         y+=1

     if (Title != ""):
        text_surface = self.font_normal.render(Title, True, colour)
        rect = text_surface.get_rect(left=5,top=5)
        self.tftScreen.blit(text_surface,rect)
        if ((y-(fontlineheight/2)) < self.font_normal.get_linesize()):
            y = y + self.font_normal.get_linesize()

     scrollsurface = pygame.Surface((listwidth, listheight))

     ypos = 4
     for oneval in valueList:
        text_surface = self.font_large.render(oneval, True, colour)
        rect = text_surface.get_rect(left=0,top=ypos)
        scrollsurface.blit(text_surface,rect)
        ypos = ypos + fontlineheight

     rect = scrollsurface.get_rect(left=x+4,top=y-(fontlineheight*SelectedValue))

     UpButton = ((x,y-overlap-2),(x+listwidth,y-overlap-2),(x+(listwidth/2),y-(fontlineheight)))
     UpButtonarea = pygame.Rect(x,y-(fontlineheight),listwidth,(fontlineheight)-overlap-2)

     DownButton = ((x,y+fontlineheight+overlap+2),(x+listwidth,y+fontlineheight+overlap+2),(x+(listwidth/2),y+fontlineheight+(fontlineheight)))
     DownButtonarea = pygame.Rect(x,y+fontlineheight+overlap+2,listwidth,(fontlineheight))

     SelectButtonarea = pygame.Rect(x+4,y-overlap,listwidth-4, fontlineheight+(overlap*2))

     pygame.draw.polygon(self.tftScreen,colour, UpButton,0)
     pygame.draw.rect(self.tftScreen,colour,(x-1,y-overlap,listwidth+2,fontlineheight+(overlap*2)+1),1)
     #self.tftScreen.blit(scrollsurface,(0,-(fontlineheight*(currentValue-minValue))))
     self.tftScreen.set_clip(SelectButtonarea) # pygame.Rect(x,y,listwidth, fontlineheight))
     self.tftScreen.blit(scrollsurface,rect)
     self.tftScreen.set_clip(None)
     pygame.draw.polygon(self.tftScreen,colour,  DownButton,0)

     #~ log.info ("Displaying %d", SelectedValue)
     #~ log.info ("Displaying %s", valueList[SelectedValue])

     #~ pygame.display.update()


     #self.tftScreen.set_clip(SelectButtonarea) # pygame.Rect(x,y,listwidth, fontlineheight))

     return [2, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight, SelectedValue,SelectedValue,0,len(valueList)-1,x,y, fontlineheight*SelectedValue, Action]

   def SelectValueFromList(self, Title, x, y, currentValue, valueList, colour = colours.WHITE, dimcolour = -1):
     # currentValue is text thats in the valuelist
     self.tftScreen.fill((0,0,0))
     # Find wich value to highlight
     Valno = 0
     for oneval in valueList:
        if (currentValue == oneval):
            SelectedValue = Valno
        Valno = Valno + 1

     ListSelector = self.DisplaySelectValueFromList(Title, x, y, SelectedValue, valueList, colour = colours.WHITE)

     pygame.display.update()

     ControlType, UpButtonarea,UpButton, DownButtonarea,DownButton, SelectButtonarea, scrollsurface, fontlineheight = ListSelector

     CancelArea  = self.DisplayButton(-90,-5,"Cancel")
     yoffset = (fontlineheight*SelectedValue)
     if dimcolour == -1:
        dimcolour = (colour[0]/2, colour[1]/2, colour[2]/2)
     OldSelectedValue = SelectedValue
     menuwaiting = True
     menuTimeout = 0
     ScrollDirection = 0

     LOOP_TIME=float(0.1)
     calcTimeout = self.settings.getInt('menu_timeout')*(1/LOOP_TIME) # We're unlikely to update this on the fly

     while (menuwaiting == True) or (self.stopping == True):
        time.sleep(LOOP_TIME)
        if menuTimeout > calcTimeout:
            #self.exitMenu()
            menuwaiting = False
        else:
            menuTimeout = menuTimeout + 1

        for event in pygame.event.get():
           if (event.type is QUIT):
               menuwaiting = False

           if (event.type is MOUSEBUTTONUP):
               menuTimeout = 0
               if (UpButtonarea.collidepoint(event.pos)):
                   if (SelectedValue < len(valueList)-1):
                       SelectedValue = SelectedValue + 1
                       pygame.draw.polygon(self.tftScreen,dimcolour, UpButton,0)
                       PushButton = UpButton
                       ScrollDirection = 1
                       #~ log.info("down")
                       time.sleep(0.1)
               elif (DownButtonarea.collidepoint(event.pos)):
                   if (SelectedValue > 0):
                       SelectedValue = SelectedValue - 1
                       pygame.draw.polygon(self.tftScreen,dimcolour, DownButton,0)
                       PushButton = DownButton
                       ScrollDirection = -1
                       time.sleep(0.1)
                       #~ log.info("up")
               elif (SelectButtonarea.collidepoint(event.pos)):
                   menuwaiting = False
                   currentValue  = valueList[SelectedValue]
               elif (CancelArea.collidepoint(event.pos)):
                   menuwaiting = False


        if (SelectedValue != OldSelectedValue):
            offset = 0
            OldSelectedValue = SelectedValue
            self.tftScreen.set_clip(SelectButtonarea)
            while (offset < fontlineheight):
                rect = scrollsurface.get_rect(left=x,top=y-yoffset)
                self.tftScreen.blit(scrollsurface,rect)
                pygame.display.update()
                offset = offset + 1
                yoffset = yoffset + ScrollDirection
            self.tftScreen.set_clip(None)
            # Leave Shaded the scroll buttons at top and bottom of the list
            if (SelectedValue > 0) and (ScrollDirection < 0):
                pygame.draw.polygon(self.tftScreen,colour, PushButton,0)
            if (SelectedValue < len(valueList)-1) and (ScrollDirection > 0):
                pygame.draw.polygon(self.tftScreen,colour, PushButton,0)

            # Leave Shaded the scroll buttons at top and bottom of the list
            #~ if (SelectedValue == 0):
                #~ pygame.draw.polygon(self.tftScreen,dimcolour, UpButton,0)
            #~ else:
                #~ pygame.draw.polygon(self.tftScreen,colour, UpButton,0)
            #~ if (SelectedValue == len(valueList)-1):
                #~ pygame.draw.polygon(self.tftScreen,dimcolour, DownButton,0)
            #~ else:
                #~ pygame.draw.polygon(self.tftScreen,colour, DownButton,0)
            # Shade the scroll buttons at top and bottom of the list
            #~ if (SelectedValue == 0) or (SelectedValue == len(valueList)-1):
                #~ pygame.draw.polygon(self.tftScreen,dimcolour, PushButton,0)


     #self.tftScreen.set_clip(None)

     #time.sleep(5)

     return currentValue #valueList[SelectedValue]


   def showvolume(self, newstate):
        self.volumebar = newstate
        if (self.volumebar == True):
            self.CurrentVolume = int(self.settings.get('volumepercent'))
            area = self.VolumeSlider(self.CurrentVolume, colours.GREEN)
            #~ self.SleepTime = 0.1
        else:
            # Blank the entire volume area
            area = self.VolumeSlider(100, colours.BLACK)
            #~ self.SleepTime = 1
        pygame.display.update(area)

   def newvolume(self):
    return self.CurrentVolume

   def VolumeSlider(self,VolumeValue, colour):
       scale = (SCREEN_HEIGHT-32)/100.0
       #~ log.info("vol %d at %d,%d to %f", VolumeValue, SCREEN_WIDTH - 32, SCREEN_HEIGHT-32 - (VolumeValue * scale), (VolumeValue * scale))
       area =            pygame.draw.rect(self.tftScreen, colour, [SCREEN_WIDTH - 32,SCREEN_HEIGHT-32 - (VolumeValue * scale), 20, (VolumeValue * scale)], 0)
       area = area.union(pygame.draw.rect(self.tftScreen, colour, [SCREEN_WIDTH - 32,0,20,SCREEN_HEIGHT-32], 1))
       return area
       #~ pygame.display.flip()

   # def scroll(self,direction):
      # self.menu.scroll(direction)

   # Called by InputWorker on press of the select button
   # def select(self):
      # if self.alarmThread.isAlarmSounding():
         # Lets snooze for a while
         # self.alarmThread.snooze()
         # return

      # self.menu.select()

   # Called by InputWorker on press of the cancel button
   # def cancel(self):
      # if self.alarmThread.isAlarmSounding() or self.alarmThread.isSnoozing():
         # Stop the alarm!
         # self.alarmThread.stopAlarm()
         # return

      # if self.alarmThread.alarmInSeconds() < self.settings.getInt('preempt_cancel') and not self.menu.isActive():
         # We're in the allowable window for pre-empting a cancel alarm, and we're not in the menu
         # log.info("Pre-empt cancel triggered")
         # self.alarmThread.stopAlarm()
         # return

      # self.menu.cancel()


   #~ def showvolumeSlider(self, VisibleState = False, NewValue = -1):
        #~ # Show existing volume level or what it could be
        #~ if (NewValue == -1):
            #~ NewValue = int(self.settings.get('volume'))
        #~ self.CurrentVolume = NewValue
        #~ self.VisibleVolume = VisibleState
        #~ if (self.VisibleVolume == False):
            #~ self.VolumeSlider(self.CurrentVolume, colours.BLACK)
        #~ else:
            #~ self.VolumeSlider(self.CurrentVolume, colours.GREEN)
        #~ return self.CurrentVolume

   def stop(self):
      self.stopping=True

   def ControlAlarm(self, colour = colours.WHITE):

    def StopAlarm(Control):
        self.SetExtraMessage("Stopping Alarm",20)
        #checkmessage = 20
        self.alarmThread.stopAlarmTrigger()
        self.MenuWaiting = False
        return "Stopping Alarm"

    def SnoozeAlarm(Control):
        self.SetExtraMessage("Snoozing Alarm",20)
        #checkmessage = 20
        self.alarmThread.snooze()
        self.MenuWaiting = False
        return "Stopping Alarm"

    def CloseControlAlarm(Control):
        self.MenuWaiting = False
        return "Exit"

    self.caller.pauseclock(True)
    self.tftScreen.fill((0,0,0))

    dimcolour = (colour[0]/2, colour[1]/2, colour[2]/2)

    AllButtons = []
    Controls = []

    x = 50
    y = 30

    CloseInfo  = self.DisplayBigButton(SCREEN_WIDTH,y,"Snooze Alarm", SnoozeAlarm)
    Controls.append(CloseInfo)

    y += CloseInfo[1][3]+50
    CloseInfo  = self.DisplayBigButton(SCREEN_WIDTH,y,"Cancel Alarm", StopAlarm)
    Controls.append(CloseInfo)

    CloseArea  = self.DisplayButton(-10,-10,"Close", CloseControlAlarm)
    Controls.append(CloseArea)

    pygame.display.update()
    self.HandleGUI(Controls, colour, dimcolour)

    self.caller.pauseclock(False)

   def run(self):

      self.SleepTime = float(0.1)
      volumedragstart = -1
      self.checkmessage = 20
      lastplayerpos = 1 # media player position
      NoneCount = 0

      tick = False
      checkalarm = 20
      lastsecond = -1
      Waittime = 0.1
      #~ self.ShowClock  = True
      quickpoll = False
      LastTime = datetime.datetime.now()

      # extract, Set and export clock info'
      colourR, colourG, colourB = self.settings.getcolour('clock_colour')
      self.SetClockColour(str(colourR)+","+str(colourG)+","+str(colourB))

      if self.mqttbroker != None:
        self.mqttbroker.set_display(self)
        self.publish()
      #~ self.settings.set("quiet_reboot","0")

      while(not self.stopping):
         time.sleep(self.SleepTime)

         try:
            #self.SleepTime = 0.1

            now = datetime.datetime.now().time()
            second = now.second

            if (self.pausedState == False ) and ((second != lastsecond) or (quickpoll == True)):
                
                # Republish to mqtt ever hour
                if ((now.minute == 0) and (now.second < 2)): # might do this twice but never mind
                    self.publish()

                if (self.lcd.ClockFontName == None):

                    hour = now.hour
                    minute = now.minute
                    second = now.second
                    #log.info("%d:%d:%d", hour, minute, second)

                    self.Lasthourtens  = self.ClockSegment(0, int(hour / 10), self.Lasthourtens)
                    self.Lasthoutunits = self.ClockSegment(1, hour % 10, self.Lasthoutunits)

                    self.Lastmintens  = self.ClockSegment(3, int(minute / 10), self.Lastmintens)
                    self.Lastminunits = self.ClockSegment(4, minute % 10, self.Lastminunits)

                    if (self.Clockformat == 6):
                        self.Lastsecstens  = self.ClockSegment(6, int(second / 10), self.Lastsecstens)
                        self.Lastsecsunits = self.ClockSegment(7, second % 10, self.Lastsecsunits)
                    elif (self.Clockformat == 4):
                        tick = not tick
                        if tick == True:
                            self.ClockSegment(2,10,-1)
                        else:
                            self.ClockSegment(2,-1,10)

                else: # if (second != lastsecond) or (quickpoll == True)
                        if (second != lastsecond):
                            tick = not tick
                            lastsecond = second
                        if tick == True:
                            quickpoll = self.lcd.SetBigMessage(now.strftime("%H %M"), True, self.ClockColour,self.ExtraMessage)
                        else:
                            quickpoll = self.lcd.SetBigMessage(now.strftime("%H:%M"), True, self.ClockColour,self.ExtraMessage)
                        if quickpoll:

                            #~ Waittime = 0.04
                            self.SleepTime = 0.04
                        else:
                            Waittime = 1
                        self.SleepTime = 0.1

            checkalarm -= 1
            if (checkalarm == 0):
                checkalarm = 60
                diff = datetime.datetime.now() - LastTime
                LastTime = datetime.datetime.now()
                if diff > datetime.timedelta(minutes=30):
                    #~ self.ExtraMessage = self.alarm.getMenuLine()
                    log.info("time change detected")
                    self.alarmThread.autoSetAlarm(quiet = True)


            if (self.menu.active == False) and (pygame.event.peek()):

                for event in pygame.event.get():

                    mx,my = event.pos
                    if (event.type is MOUSEBUTTONUP):

                        if (volumedragstart != -1): # volume was being dragged
                                volumedragstart = -1
                                self.lcd.showvolume(False)
                                self.settings.set('volumepercent',self.lcd.newvolume)
                                self.lcd.CurrentVolume = self.lcd.newvolume

                        elif self.alarmThread.isAlarmSounding():
                                self.ControlAlarm()


                        elif (mx > CONTROL_ZONE) and (mx < SCREEN_WIDTH - CONTROL_ZONE): # i the middle

                            # bottom tap and Weather has been setup
                            if (my > SCREEN_HEIGHT - CONTROL_ZONE) and (self.settings.get('WUG_KEY') != ""): 
                                #~ self.caller.clockMessage("Discovering Weather...")
                                self.SetExtraMessage("Discovering Weather...",20)
                                LocalWeather = self.weather.getWeather()

                                try:
                                    if LocalWeather != None:
                                        message=LocalWeather.display()
                                        speech = self.weather.getWeather().speech()
                                        self.media.playVoice(speech)
                                    else:
                                        message = "No weather is available"
                                        self.media.playVoice(message)
                                except Exception:
                                    log.exception("Failed to get weather information")
                                    message = "No weather is available"

                                #~ self.caller.clockMessage(message)
                                self.SetExtraMessage(message,20)
                                log.info("Weather Message = %s", message)
                                self.checkmessage = len(message) * 3 #110


                            else:
                                action = self.menu.DisplayMenu()
                                self.checkmessage = 1
                                if (action == "Exit"):
                                    self.pausedState = True
                                    self.caller.stop(0)


                        elif (mx < CONTROL_ZONE): # left side
                            self.ControlRadio()
                            self.checkmessage = 1

                    elif (event.type is MOUSEBUTTONDOWN) and (mx > SCREEN_WIDTH - CONTROL_ZONE): # Start Volume drag

                       if (volumedragstart == -1):
                            volumedragstart = my
                            self.lcd.showvolume(True)

                    elif (event.type is QUIT):
                        self.stop()

                    elif (volumedragstart != -1) and (event.type is MOUSEMOTION): # if volume open change volume

                        Adjustment = int(round((volumedragstart - my)/20.0))
                        if Adjustment != 0:
                            volumedragstart = my
                            log.info("volume adjustment %d", Adjustment)
                            newvolume = self.lcd.newvolume + Adjustment
                            if (newvolume < 2):
                                newvolume = 2
                            elif (newvolume > 100):
                                newvolume = 100

                            if self.lcd.newvolume != newvolume:
                                self.settings.setVolume(newvolume)
                                if (newvolume < self.lcd.newvolume):
                                    area = self.lcd.VolumeSlider(self.lcd.newvolume, colours.BLACK)
                                    area = area.union(self.lcd.VolumeSlider(newvolume, colours.GREEN))
                                else:
                                    area = self.lcd.VolumeSlider(newvolume, colours.GREEN)
                                self.lcd.newvolume = newvolume
                                pygame.display.update(area)

            self.checkmessage -= 1
            if (self.checkmessage <= 0):
                self.checkmessage = 200
                #self.caller.clockMessage(self.alarmThread.getMenuLine())

                message = ""

                #~ if self.menu.isActive():
                   #~ message += self.menu.getMessage()
                #~ if self.alarmThread.isAlarmSounding():
                   #~ message += ", Wakey wakey!"
                   #~ continue

                message += self.media.message

                ' Disabled as check and message is done in MediaPlayer.py'
                if False and self.media.playerActive(): # self.menu.backgroundRadioActive():
                    self.checkmessage = 10
                    try:
                        currentplayerpos = self.media.player.stream_pos
                        if (currentplayerpos > lastplayerpos) and (currentplayerpos != None):
                           message += ", Radio Playing"
                           #~ NoneCount = 0
                        elif (currentplayerpos == None) or (lastplayerpos == -1):
                           log.info("last %s, current pos %s",lastplayerpos, currentplayerpos) #, self.media.player.stream_length)
                           message += ", Radio Buffering"
                           #~ if (lastplayerpos == 0) and (currentplayerpos == None):
                               #~ NoneCount += 1
                        else:
                           message += ", Radio Paused"
                           log.info("last %s, current pos %s ",lastplayerpos, currentplayerpos) #, self.media.player.stream_length)
                        lastplayerpos = currentplayerpos
                    except Exception as e: # stream not valid I guess
                        log.error("Error: %s" , e)
                        message += ", Radio Erroring"
                        #~ NoneCount += 1
                        #~ lastplayerpos = currentplayerpos

                if self.alarmThread.message != "":
                    message += self.alarmThread.message
                    #if self.alarmThread.isAlarmSounding():
                    #   message += ", Wakey wakey!"

                else:
                    message += ", " + self.alarmThread.getMenuLine()

                #message+=", " + self.weather.getWeather().display()
                #message+="\n"

                if message[0] == ",":
                    message = message[2:]
                self.SetExtraMessage(message)
                #~ self.caller.clockMessage(message)


         except:
            log.exception("Error in LcdThread loop")
            pygame.display.quit()
            #self.stopping=True
            self.caller.stop()

      # end while not stopping
      #~ self.setMessage("Shutting down")
      # self.lcd.shutdown()
      self.menu.stop()
      self.caller.stop()
      pygame.display.quit()
      pygame.quit()

