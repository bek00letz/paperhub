# Sleep test

A throwaway Android app used to find out whether an e-reader can keep a dashboard
current while it sleeps. The results are in
[docs/FINDINGS-2026-10-20.md](../../docs/FINDINGS-2026-10-20.md).

What it does: a full-screen dashboard (a test card, or a frame downloaded from an
address), a timer that checks for a new frame, and a log of every event with the
battery's charge counter at that moment:

```bash
adb shell cat /sdcard/Android/data/paperhub.experiment.sleeptest/files/sleep-log.csv
```

It also contains the first attempt, replacing the device's sleep screen
(`SleepDream`), which Onyx resets at every start.

## Building

Needs the Android command-line tools and Java 21 (Gradle 8.11 can't read newer
Java version strings):

```bash
export JAVA_HOME=$(/usr/libexec/java_home -v 21)
echo "sdk.dir=/opt/homebrew/share/android-commandlinetools" > local.properties
./gradlew assembleDebug
```

## On a Boox

Allow it to sleep (device admin), turn off auto-freeze, and lift the background
restriction Boox leaves behind:

```bash
adb shell cmd appops set --uid paperhub.experiment.sleeptest RUN_ANY_IN_BACKGROUND allow
```
