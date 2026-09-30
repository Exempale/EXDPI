#!/bin/sh
# EXDPI mac zapret engine install (LaunchDaemon).
# По мотивам install.sh из ZapretMac (Flowseal, MIT), адаптировано под EXDPI.
# Использование: exdpi-install.sh <SOURCE> <DATA_ROOT>
# SOURCE  — папка движка в бандле приложения (bin, strategies, default-lists, ...)
# DATA_ROOT — ~/Library/Application Support/EXDPI (состояние пользователя)
set -eu

SOURCE=$1
DATA_ROOT=$2
DEST='/Library/Application Support/EXDPI/zapret'
PLIST=/Library/LaunchDaemons/io.github.exdpi.zapret.plist
ANCHOR=com.apple/exdpi-zapret
KEEPINIT_FILE=/var/db/exdpi-zapret.keepinit

/bin/launchctl bootout system/io.github.exdpi.zapret >/dev/null 2>&1 || true
/sbin/pfctl -a "$ANCHOR" -F all >/dev/null 2>&1 || true
/usr/bin/pkill -9 -x utunws >/dev/null 2>&1 || true
/bin/mkdir -p "$DEST"
/usr/bin/rsync -a --delete "$SOURCE/" "$DEST/"
/bin/touch "$DEST/ipset-any.txt"
/usr/sbin/chown -R root:wheel "$DEST" || true
/bin/chmod 755 "$DEST/exdpi-install.sh" "$DEST/exdpi-run.sh" "$DEST/exdpi-stop.sh" "$DEST/bin/utunws" 2>/dev/null || true
/bin/chmod 755 "$DEST/watchdog.sh" 2>/dev/null || true
/usr/bin/sed "s|@DATA_ROOT@|$DATA_ROOT|g" "$DEST/exdpi-plist.xml.in" > "$PLIST"
/usr/sbin/chown root:wheel "$PLIST" || true
/bin/chmod 644 "$PLIST"
if [ ! -s "$KEEPINIT_FILE" ]; then
    /usr/sbin/sysctl -n net.inet.tcp.keepinit > "$KEEPINIT_FILE"
    /bin/chmod 600 "$KEEPINIT_FILE"
fi
/usr/sbin/sysctl -w net.inet.tcp.keepinit=7000 >/dev/null
/bin/launchctl enable system/io.github.exdpi.zapret
I=0
until /bin/launchctl bootstrap system "$PLIST"; do
    I=$((I + 1))
    if [ "$I" -gt 10 ]; then
        /bin/sh "$DEST/exdpi-stop.sh" || true
        exit 1
    fi
    sleep 0.5
done
/bin/launchctl kickstart -k system/io.github.exdpi.zapret

I=0
until /sbin/ifconfig utun50 >/dev/null 2>&1; do
    I=$((I + 1))
    if [ "$I" -gt 100 ]; then
        /bin/sh "$DEST/exdpi-stop.sh" || true
        echo 'utunws did not stay running' >&2
        /usr/bin/tail -40 "$DEST/engine.log" >&2 2>/dev/null || true
        exit 1
    fi
    sleep 0.1
done
