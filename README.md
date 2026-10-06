# Terminal Alarm Clock

A dependency-free Python CLI alarm clock with a live digital time display, local date, weekday repeats, and snooze.

## Requirements

- Python 3.9 or newer
- A terminal that supports ANSI cursor controls
- No third-party packages

## Run

Foreground mode keeps alarms in the running CLI process:

```console
python alarm_clock.py
```

To opt into a detached worker that continues after the terminal closes, use:

```console
python alarm_clock.py --background
```

The terminal remains a control view while the worker runs. Type `quit` or close the terminal to leave the worker running. Stop the worker with:

```console
python alarm_clock.py --stop-background
```

Run the focused checks with:

```console
python -m unittest -v
```

The plain 24-hour `HH:MM:SS` display and date refresh once per second. Type commands at the `alarm>` prompt while the display continues updating:

```text
add 07:30 once
add 08:15 mon,tue,wed,thu,fri
add 09:00 mon,wed,fri
list
delete 2
```

An omitted repeat argument means `once`. Use `once` for a one-shot alarm or any comma-separated selection of `mon,tue,wed,thu,fri,sat,sun` for a recurring alarm. All seven days means daily. When the alarm rings, it repeats an audible tone until you type `snooze` for five minutes or `stop` to dismiss it. Windows uses Python's built-in `winsound`; other platforms use the terminal bell, which depends on terminal settings. The default is local machine time. A one-shot alarm whose time has already passed today is scheduled for tomorrow.

In background mode on Windows, pressing any non-modifier key while an alarm is ringing stops it, even when the terminal is closed. Press `Ctrl+Alt+S` to snooze instead. Modifier keys by themselves do nothing. The worker displays whether the global keyboard hook registered successfully; if unavailable, use the CLI commands. Foreground mode uses the `stop` and `snooze` commands.

Only background mode saves alarms in a JSON file under the current user's application data directory (Windows: `%LOCALAPPDATA%\TerminalAlarmClock`). The worker continues while you are logged in, but is not registered to start automatically after sign-out or reboot. Set `ALARM_CLOCK_HOME` to choose a different data directory.

## Design notes

- `AlarmClock` owns scheduling, repeat, and snooze state; it can be driven with explicit `datetime` values.
- `render_screen` is separate from alarm scheduling behavior.
- In background mode, the detached worker owns alarm timing and sound; the terminal is a command and status view.
- A Windows low-level keyboard hook handles stop and snooze input while the CLI is closed.
- Background alarm definitions are persisted as JSON without a database. Foreground alarms remain in memory. Weekday repeats use local wall-clock time.

## Build-exercise narration outline

1. State the scope: terminal-only, no dependencies or database, a live digital clock plus useful alarm controls.
2. Explain the optional background mode: deterministic scheduling model, JSON persistence, detached worker, and terminal status view.
3. Show creating a one-shot and a weekday alarm, then listing and deleting an alarm.
4. Demonstrate the clock continuing to update while the command prompt is available; explain the five-minute snooze and stop commands.
5. Walk through validation and edge cases: invalid times/days, passed one-shot time rolling to tomorrow, selected weekdays, snooze deadline, and closing the terminal while the worker keeps running.

## Limitations

Snooze duration is fixed at five minutes. The optional worker does not automatically restart after sign-out or reboot; use Windows Task Scheduler for that behavior. The display relies on ANSI cursor control support.
