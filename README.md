# Terminal Alarm Clock

A dependency-free Python CLI alarm clock with a live digital time display, local date, weekday repeats, and snooze.

## Requirements

- Python 3.9 or newer
- A terminal that supports ANSI cursor controls
- No third-party packages

## Run

```console
python alarm_clock.py
```

Run the focused checks with:

```console
python -m unittest -v
```

The plain 24-hour `HH:MM:SS` display and date refresh once per second. The CLI starts a detached background worker automatically; alarms keep running after you type `quit` or close the terminal. Type commands at the `alarm>` prompt while the display continues updating:

```text
add 07:30 once
add 08:15 mon,tue,wed,thu,fri
add 09:00 mon,wed,fri
list
delete 2
```

An omitted repeat argument means `once`. Use `once` for a one-shot alarm or any comma-separated selection of `mon,tue,wed,thu,fri,sat,sun` for a recurring alarm. All seven days means daily. When the alarm rings, it repeats an audible tone until you type `snooze` for five minutes or `stop` to dismiss it. Windows uses Python's built-in `winsound`; other platforms use the terminal bell, which depends on terminal settings. The default is local machine time. A one-shot alarm whose time has already passed today is scheduled for tomorrow.

Alarms are saved in a JSON file under the current user's application data directory (Windows: `%LOCALAPPDATA%\TerminalAlarmClock`). To stop the background worker, run `python alarm_clock.py --stop-background`; saved alarms remain available the next time the CLI starts. The worker continues while you are logged in, but is not registered to start automatically after sign-out or reboot. Set `ALARM_CLOCK_HOME` to choose a different data directory.

## Design notes

- `AlarmClock` owns scheduling, repeat, and snooze state; it can be driven with explicit `datetime` values.
- `render_screen` is separate from alarm scheduling behavior.
- The detached worker owns alarm timing and sound; the terminal is a command and status view.
- Alarm definitions are persisted as JSON without a database. Weekday repeats use local wall-clock time.

## Build-exercise narration outline

1. State the scope: terminal-only, no dependencies or database, a live digital clock plus useful alarm controls.
2. Explain the key split: deterministic scheduling model, JSON persistence, detached worker, and terminal status view.
3. Show creating a one-shot and a weekday alarm, then listing and deleting an alarm.
4. Demonstrate the clock continuing to update while the command prompt is available; explain the five-minute snooze and stop commands.
5. Walk through validation and edge cases: invalid times/days, passed one-shot time rolling to tomorrow, selected weekdays, snooze deadline, and closing the terminal while the worker keeps running.

## Limitations

Snooze duration is fixed at five minutes. The worker does not automatically restart after sign-out or reboot; use Windows Task Scheduler for that behavior. The display relies on ANSI cursor control support.
