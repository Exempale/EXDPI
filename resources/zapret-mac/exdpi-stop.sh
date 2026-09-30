#!/bin/sh
# EXDPI mac zapret engine stop.
# По мотивам stop.sh из ZapretMac (Flowseal, MIT), адаптировано под EXDPI.

ANCHOR=com.apple/exdpi-zapret
TOKEN_FILE=/var/run/exdpi-zapret.pf-token
KEEPINIT_FILE=/var/db/exdpi-zapret.keepinit
/bin/launchctl disable system/io.github.exdpi.zapret >/dev/null 2>&1 || true
/bin/launchctl bootout system/io.github.exdpi.zapret >/dev/null 2>&1 || true
/sbin/pfctl -a "$ANCHOR" -F all >/dev/null 2>&1 || true
/usr/bin/pkill -9 -x utunws >/dev/null 2>&1 || true
if [ -s "$TOKEN_FILE" ]; then
    TOKEN=$(/bin/cat "$TOKEN_FILE" 2>/dev/null || true)
    if [ -n "$TOKEN" ]; then /sbin/pfctl -X "$TOKEN" >/dev/null 2>&1 || true; fi
    /bin/rm -f "$TOKEN_FILE"
fi
if [ -s "$KEEPINIT_FILE" ]; then
    KEEPINIT=$(/bin/cat "$KEEPINIT_FILE" 2>/dev/null || true)
    case "$KEEPINIT" in
        *[!0-9]*|'') ;;
        *) /usr/sbin/sysctl -w "net.inet.tcp.keepinit=$KEEPINIT" >/dev/null 2>&1 || true ;;
    esac
    /bin/rm -f "$KEEPINIT_FILE"
fi
