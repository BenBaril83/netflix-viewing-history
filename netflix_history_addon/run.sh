#!/bin/sh
# Virtual display + VNC server back the in-panel login browser (shown via noVNC).
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1280x800x24 &
x11vnc -display :99 -forever -shared -nopw -localhost -rfbport 5900 -quiet &
exec python -m netflix_history.addon
