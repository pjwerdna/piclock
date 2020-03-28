#!/bin/sh
# /etc/init.d/fbdev
### BEGIN INIT INFO
# Provides: piclock
# Required-Start: $remote_fs $syslog
# Required-Stop: $remote_fs $syslog
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Start X server on HDMI, if plugged, otherwise TFT, at boot time
# Description: Start Pi CLock at boot time.
### END INIT INFO

# Set the FBUSER variable to the name of the user to start Xserver under
FBUSER="pi"

eval cd ~$FBUSER/piclock

case "$1" in
 forcestart)
   echo "Starting piClock"
   sudo python piclock.py --log=DEBUG --nolancheck > piclockweb.log 2>&1 &
   ;;
 start)
   echo "Starting piClock"
   sudo python piclock.py --log=DEBUG > piclockweb.log 2>&1 &
   ;;
 stop)
   pkill --signal SIGINT -f "sudo python piclock.py"
   echo "piClock stopped"
   ;;
restart)
   pkill --signal SIGINT -f "sudo python piclock.py"
   echo "piClock stopped"
   sleep 10
   echo "Starting piClock"
   sudo python piclock.py --log=DEBUG > piclockweb.log 2>&1 &
  ;;
 *)
   echo "Usage: /etc/init.d/piclock {start|stop|restart}"
   exit 1
   ;;
esac
exit 0
