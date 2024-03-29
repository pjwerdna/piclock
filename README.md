# Pi Clock

Raspberry Pi Based Internet Radio Alarm clock with 3.5 inch touchscreen. Each day of the week can have a differant alarm time and internet radio station to play.
 Also has a "Holiday Mode" which sets the alarm to a fixed time.

 Originally based on http://mattdyson.org/projects/alarmpi/ (https://github.com/mattdy/alarmpi) But its changed considerably

# Features

- 3.5 inch TFT touch screen
- Web page for alarms and settings
- api for use by the above webpage
- fsapi for use by OpenHab (or can use MQTT)
- Uses Google calendar to indicate holidays when that days alarm goes of later (at a fixed time)
- Optional MQTT server for radio and alarm control as well as station name and URL configuration

# Hardware required

- Raspberry Pi with Wifi
 Any version with Wifi builtin or available using a dongle

- PiTFT 480x320 3.5" - https://www.adafruit.com/product/2097

- Adafruit TL2561 - https://www.adafruit.com/product/439

- Adafruit MAX98306 - https://www.adafruit.com/product/3006 + 8 ohm Speakers
 OR
 Powered Speakers

# Install packages Etc

- Python 2
- mplayer2
- mplayer.py
- festival
- Fonts

## mplayer Install
Plays the Inernet radio streams
```
sudo apt-get install mplayer2
```

## mplayer.py Install
Python interface to mplayer2
```
sudo git clone https://github.com/baudm/mplayer.py.git
```
The clone command puts the code in the mplayer.py folder so link mplayer to a sub folder where the piclock.py is
~~~
cd piclock
ln -s mplayer ..../mplayer.py/mplayer
~~~

## festival Install
Allows the clock to speak. Two choices "festival" or "pico"
~~~
sudo apt-get install festival
sudo apt-get install libttspico-utils
~~~

## Fonts Install
Install 7 & 14 segment Font from http://www.keshikan.net/fonts-e.html

Probably
~~~
sudo apt-get install fonts-dseg
~~~

## Python 2 Librarys
~~~
sudo apt-get install python-gflags python-httplib2
sudo apt-get install python-dateutil
sudo apt-get install python-pip
sudo pip install pytz
sudo pip install --upgrade google-api-python-client
sudo pip install --upgrade oauth2client
sudo pip install --upgrade oauth2client.tools
sudo pip install TSL2561
sudo pip install Adafruit_GPIO
~~~

## SSL Certificate generation
~~~
openssl req -new -x509 -keyout serverssl.key -out serverssl.crt -days 365 -nodes -extensions req_ext -config sslconfig.txt
~~~

  Sample sslconfig.txt provided in the config directory. This certificate will have to be renewed every 365 days

## Calendar credentials

- Generate Client ID and Client Secret
  - Goto https://console.developers.google.com/apis/credentials
  - Change to the "Credentials" section
  - Click "Create credentials" at the top and choose "OAuth Client ID"
  - Set Application Type "Other"
  - Give it a name e.g. PiClock" and click create
- Copy and rename the file `~/piclock/config/client_secret.json.txt` to `\~/piclock/calendar-python.json` (Note change of name)
- Edit the file calendar-python.json and fillin &lt;CLIENTID&gt; and &lt;CLIENTSECRET&gt;
- Run the code as follows
~~~
sudo python piclock.py  --noauth_local_webserver
~~~
- Copy the displayed URL and past into your web browser
- Follow the prompts to allow accesss
- Copy and Paste the authorisation code back into piclock
- You can then stop piclock using CRTL+C and start it normally

Note
- If the clientid or client secret change, delete your previously saved credentials
- at ~/.credentials/calendar-python.json

## TFT Configuration

Follow instruction at https://learn.adafruit.com/adafruit-pitft-3-dot-5-touch-screen-for-raspberry-pi

## Starting the Clock
### Manual Startup
```
sudo python piclock.py
```
Starting this way logs everything to the screen

### Auto Startup
You should do this only when you're sure the clock is working correctly when you start it manually

```
sudo ln -s /home/pi/piclock/piclock.sh /etc/init.d/piclock
```
Logs go to /home/pi/piclock/piclock.log and as a last resort /home/pi/piclock/piclockerror.log
Normally errors will go to the normal piclock.log as "INFO" due to the web server also logging connections to stderr

### FSAPI based on the following
- https://github.com/openhab/openhab1-addons/wiki/Frontier-Silicon-Radio-Binding
- https://github.com/flammy/fsapi
- https://github.com/openhab/openhab/blob/master/bundles/binding/org.openhab.binding.frontiersiliconradio/src/main/java/org/openhab/binding/frontiersiliconradio/internal/FrontierSiliconRadio.java
