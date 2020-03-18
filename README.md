# Pi Clock

Raspberry Pi Based clock and Alarm clock with 3.5 inch touchscreen. Each day of the week can have a differant alarm time and internet radio station to play.
 Also has a "Holiday Mode" which sets the alarm to a fixed time.

# Hardware required

- Raspberry Pi with Wifi
 Any version with Wifi builtin or available using a dongle

- PiTFT 480x320 3.5" - https://www.adafruit.com/product/2097

- Adafruit TL2561 - https://www.adafruit.com/product/439

- Adafruit MAX98306 - https://www.adafruit.com/product/3006 + 8 ohm Speakers
 OR
 Powered Speakers

# Extra packages

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
The clone command puts the code in the mplayer.py folder so link mplayer to a sub folder where the xxx.py is
```
cd mplayer.py
ln -s ./mplayer.py/mplayer
```

## festival Install
Allows the clock to speak
- sudo apt-get install festival

## Fonts Install
See 7 & 14 segment Font from
 http://www.keshikan.net/fonts-e.html

## Python Libs
```
sudo apt-get install python-gflags python-httplib2
sudo easy_install pytz
sudo apt-get install python-dateutil
sudo pip install --upgrade google-api-python-client
sudo pip install --upgrade oauth2client
sudo pip install --upgrade oauth2client.tools
sudo pip install TSL2561
sudo pip install Adafruit_GPIO
sudo apt-get install libttspico-utils
```

## SSL Certificate generation
```
openssl req -new -x509 -keyout serverssl.key -out serverssl.crt -days 365 -nodes -extensions req_ext -config sslconfig.txt
```

