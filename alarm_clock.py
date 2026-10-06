"""A small, dependency-free alarm clock for the terminal."""

from __future__ import annotations

import queue
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_INDEX = {name: index for index, name in enumerate(DAYS)}
SNOOZE_MINUTES = 5
PROMPT_ROW = 13


@dataclass
class Alarm:
    alarm_id: int
    hour: int
    minute: int
    weekdays: Optional[frozenset[int]]
    next_fire: datetime

    @property
    def repeat_label(self) -> str:
        if self.weekdays is None:
            return "once"
        return ",".join(DAYS[day] for day in sorted(self.weekdays))


def parse_days(value: str) -> Optional[frozenset[int]]:
    """Parse `once` or a comma-separated set of weekday abbreviations."""
    if value.lower() == "once":
        return None
    parts = [part.strip().lower()[:3] for part in value.split(",")]
    if not parts or any(part not in DAY_INDEX for part in parts):
        raise ValueError("Use 'once' or weekday abbreviations such as mon,wed,fri.")
    return frozenset(DAY_INDEX[part] for part in parts)


def next_occurrence(hour: int, minute: int, weekdays: Optional[frozenset[int]], now: datetime) -> datetime:
    """Return the next local wall-clock occurrence strictly after `now`."""
    if weekdays is None:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return candidate if candidate > now else candidate + timedelta(days=1)

    for offset in range(8):
        day = now + timedelta(days=offset)
        if day.weekday() not in weekdays:
            continue
        candidate = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate > now:
            return candidate
    raise ValueError("Choose at least one weekday.")


class AlarmClock:
    """Alarm scheduling model, independent of terminal rendering and input."""

    def __init__(self) -> None:
        self.alarms: dict[int, Alarm] = {}
        self._next_id = 1
        self.active: Optional[Alarm] = None
        self._snooze: Optional[tuple[Alarm, datetime]] = None

    def add(self, hour: int, minute: int, weekdays: Optional[frozenset[int]], now: datetime) -> Alarm:
        alarm = Alarm(self._next_id, hour, minute, weekdays,
                      next_occurrence(hour, minute, weekdays, now))
        self.alarms[alarm.alarm_id] = alarm
        self._next_id += 1
        return alarm

    def remove(self, alarm_id: int) -> bool:
        return self.alarms.pop(alarm_id, None) is not None

    def tick(self, now: datetime) -> Optional[Alarm]:
        """Return an alarm to ring when one becomes due."""
        if self.active is not None:
            return None
        if self._snooze is not None:
            alarm, due = self._snooze
            if now >= due:
                self._snooze = None
                self.active = alarm
                return alarm
        for alarm in sorted(self.alarms.values(), key=lambda item: item.next_fire):
            if now < alarm.next_fire:
                continue
            if alarm.weekdays is None:
                self.alarms.pop(alarm.alarm_id, None)
            else:
                alarm.next_fire = next_occurrence(alarm.hour, alarm.minute, alarm.weekdays, now)
            self.active = alarm
            return alarm
        return None

    def snooze(self, now: datetime) -> bool:
        if self.active is None:
            return False
        self._snooze = (self.active, now + timedelta(minutes=SNOOZE_MINUTES))
        self.active = None
        return True

    def stop(self) -> bool:
        if self.active is None:
            return False
        self.active = None
        return True


class Ringer:
    """Repeat an audible tone until snoozed or dismissed."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._ring_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None

    def _ring_loop(self) -> None:
        try:
            import winsound
        except ImportError:
            winsound = None

        while not self._stop_event.is_set():
            if winsound is not None:
                try:
                    winsound.Beep(880, 500)
                except RuntimeError:
                    winsound = None
                    continue
            else:
                print("\a", end="", flush=True)
            self._stop_event.wait(0.5)


def render_screen(now: datetime, clock: AlarmClock, notice: str) -> list[str]:
    """Build a consistent, centered terminal screen for the live clock."""
    width = 40
    border_top = "┌" + "─" * width + "┐"
    border_bottom = "└" + "─" * width + "┘"
    inside = lambda value: "│" + value[:width].center(width) + "│"
    lines = [
        border_top,
        inside("ALARM CLOCK"),
        inside(""),
        inside(now.strftime("%H:%M:%S")),
        inside(now.strftime("%A, %B %d, %Y")),
        inside(""),
    ]
    lines.extend((border_bottom, notice[:80]))
    if clock.alarms:
        upcoming = min(clock.alarms.values(), key=lambda alarm: alarm.next_fire)
        schedule_line = f"Next: {_format_alarm(upcoming)} at {upcoming.next_fire:%a %H:%M}"
    else:
        schedule_line = "No upcoming alarms"
    lines.extend((schedule_line, "", "Commands: add | list | delete | snooze | stop | help | quit"))
    return lines


def _data_dir() -> Path:
    override = os.environ.get("ALARM_CLOCK_HOME")
    if override:
        return Path(override)
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TerminalAlarmClock"
    return Path.home() / ".local" / "share" / "terminal-alarm-clock"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
    os.replace(temporary, path)


def _read_json(path: Path, fallback: dict) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else fallback
    except (OSError, json.JSONDecodeError):
        return fallback


def _alarm_record(alarm: Alarm) -> dict:
    return {
        "id": alarm.alarm_id,
        "hour": alarm.hour,
        "minute": alarm.minute,
        "weekdays": sorted(alarm.weekdays) if alarm.weekdays is not None else None,
        "next_fire": alarm.next_fire.isoformat(),
    }


def _persist_alarms(clock: AlarmClock) -> None:
    _write_json(_data_dir() / "alarms.json", {
        "next_id": clock._next_id,
        "alarms": [_alarm_record(alarm) for alarm in clock.alarms.values()],
    })


def _load_alarms(clock: AlarmClock) -> None:
    data = _read_json(_data_dir() / "alarms.json", {})
    for item in data.get("alarms", []):
        try:
            days = item["weekdays"]
            alarm = Alarm(
                int(item["id"]), int(item["hour"]), int(item["minute"]),
                frozenset(int(day) for day in days) if days is not None else None,
                datetime.fromisoformat(item["next_fire"]),
            )
            clock.alarms[alarm.alarm_id] = alarm
        except (KeyError, TypeError, ValueError):
            continue
    clock._next_id = max(int(data.get("next_id", 1)), max(clock.alarms, default=0) + 1)


def _clock_from_status(data: dict) -> AlarmClock:
    clock = AlarmClock()
    for item in data.get("alarms", []):
        try:
            days = item["weekdays"]
            alarm = Alarm(
                int(item["id"]), int(item["hour"]), int(item["minute"]),
                frozenset(int(day) for day in days) if days is not None else None,
                datetime.fromisoformat(item["next_fire"]),
            )
            clock.alarms[alarm.alarm_id] = alarm
        except (KeyError, TypeError, ValueError):
            continue
    return clock


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return ctypes.get_last_error() == 5  # Access denied means the process exists.
        except (AttributeError, OSError):
            pass
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _acquire_daemon_lock() -> bool:
    lock_path = _data_dir() / "daemon.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(str(os.getpid()))
            return True
        except FileExistsError:
            try:
                pid = int(lock_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pid = -1
            if _process_is_running(pid):
                return False
            try:
                lock_path.unlink()
            except OSError:
                return False
    return False


def _send_background_command(command: str, command_id: Optional[str] = None) -> str:
    command_id = command_id or uuid.uuid4().hex
    inbox = _data_dir() / "commands"
    _write_json(inbox / f"{command_id}.json", {"id": command_id, "command": command})
    return command_id


def _start_background() -> None:
    data_dir = _data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "daemon.lock"
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip())
        if _process_is_running(pid):
            return
    except (OSError, ValueError):
        pass
    options = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--daemon"], **options)


def run_daemon() -> None:
    """Headless worker that owns alarm timing after the terminal UI exits."""
    if not _acquire_daemon_lock():
        return
    lock_path = _data_dir() / "daemon.lock"
    try:
        clock = AlarmClock()
        _load_alarms(clock)
        ringer = Ringer()
        notice = "Background alarm service is running."
        last_second: Optional[datetime] = None
        last_command_id: Optional[str] = None
        while True:
            now = datetime.now()
            for command_path in sorted((_data_dir() / "commands").glob("*.json")):
                request = _read_json(command_path, {})
                command_path.unlink(missing_ok=True)
                command_id = request.get("id")
                line = request.get("command", "")
                if line == "shutdown":
                    notice = "Background alarm service stopped."
                    _write_json(_data_dir() / "status.json", {
                        "alarms": [_alarm_record(item) for item in clock.alarms.values()],
                        "active": None,
                        "notice": notice,
                        "last_command_id": command_id,
                    })
                    return
                notice = handle_command(line, clock, now)
                last_command_id = command_id
                if line.strip() and line.split(maxsplit=1)[0].lower() in ("add", "delete"):
                    _persist_alarms(clock)

            due = clock.tick(now)
            if due is not None:
                notice = f"ALARM {_format_alarm(due)} — type snooze or stop"
                _persist_alarms(clock)
            if clock.active is None:
                ringer.stop()
            else:
                ringer.start()
            if last_second is None or now.second != last_second.second or now.date() != last_second.date():
                _write_json(_data_dir() / "status.json", {
                    "alarms": [_alarm_record(item) for item in clock.alarms.values()],
                    "active": _format_alarm(clock.active) if clock.active else None,
                    "notice": notice,
                    "last_command_id": last_command_id,
                })
                last_second = now
            time.sleep(0.2)
    finally:
        if "ringer" in locals():
            ringer.stop()
        try:
            lock_path.unlink()
        except OSError:
            pass


def _format_alarm(alarm: Alarm) -> str:
    return f"#{alarm.alarm_id} {alarm.hour:02d}:{alarm.minute:02d} ({alarm.repeat_label})"


def handle_command(line: str, clock: AlarmClock, now: datetime) -> str:
    """Apply one user command and return a concise status message."""
    parts = line.strip().split()
    if not parts:
        return "Enter a command, or type help."
    command = parts[0].lower()
    if command == "help":
        return "Commands: add HH:MM [once|mon,tue,...], list, delete ID, snooze, stop, quit"
    if command == "add":
        if len(parts) not in (2, 3):
            return "Usage: add HH:MM [once|mon,tue,...]"
        try:
            hour_text, minute_text = parts[1].split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return "Use a valid 24-hour time, for example 07:30."
            weekdays = parse_days(parts[2]) if len(parts) == 3 else None
        except ValueError as error:
            if len(parts) == 3 and str(error).startswith("Use 'once'"):
                return str(error)
            return "Use a valid 24-hour time, for example 07:30."
        alarm = clock.add(hour, minute, weekdays, now)
        return f"Added {_format_alarm(alarm)}; next at {alarm.next_fire:%a %Y-%m-%d %H:%M}."
    if command == "list":
        if not clock.alarms:
            return "No scheduled alarms."
        return " | ".join(_format_alarm(item) + f" next {item.next_fire:%m-%d %H:%M}"
                           for item in sorted(clock.alarms.values(), key=lambda item: item.next_fire))
    if command == "delete":
        if len(parts) != 2 or not parts[1].isdigit():
            return "Usage: delete ID"
        return "Alarm deleted." if clock.remove(int(parts[1])) else "No alarm with that ID."
    if command == "snooze":
        if clock.snooze(now):
            return f"Snoozed for {SNOOZE_MINUTES} minutes."
        return "No alarm is ringing."
    if command == "stop":
        return "Alarm stopped." if clock.stop() else "No alarm is ringing."
    if command == "quit":
        return "quit"
    return "Unknown command. Type help for available commands."


def _read_commands(commands: queue.Queue[str]) -> None:
    while True:
        try:
            commands.put(input("alarm> "))
        except EOFError:
            commands.put("quit")
            return


def run() -> None:
    _start_background()
    commands: queue.Queue[str] = queue.Queue()
    notice = "Background alarm service ready. Type help for commands."
    pending_command_id: Optional[str] = None
    last_second: Optional[datetime] = None
    print(f"\033[2J\033[{PROMPT_ROW};1H", end="", flush=True)
    reader = threading.Thread(target=_read_commands, args=(commands,), daemon=True)
    reader.start()
    try:
        while True:
            now = datetime.now()
            status = _read_json(_data_dir() / "status.json", {})
            if pending_command_id is not None and status.get("last_command_id") == pending_command_id:
                notice = status.get("notice", notice)
                pending_command_id = None
            elif pending_command_id is None and status.get("notice"):
                notice = status["notice"]
            while True:
                try:
                    line = commands.get_nowait()
                except queue.Empty:
                    break
                command = line.strip().split(maxsplit=1)[0].lower() if line.strip() else ""
                if command == "quit":
                    return
                pending_command_id = _send_background_command(line)
                notice = "Sending command to background alarm service..."
            if last_second is None or now.second != last_second.second or now.date() != last_second.date():
                lines = render_screen(now, _clock_from_status(status), notice)
                # Save the command prompt cursor, repaint only the clock area, then restore it.
                print("\033[s\033[H" + "\n".join(line.ljust(80) + "\033[K" for line in lines)
                      + "\033[u", end="", flush=True)
                last_second = now
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h\nGoodbye.", flush=True)


def stop_background() -> None:
    lock_path = _data_dir() / "daemon.lock"
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        print("Background alarm service is not running.")
        return
    if not _process_is_running(pid):
        print("Background alarm service is not running.")
        return
    _send_background_command("shutdown")
    print("Requested background alarm service shutdown.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--daemon"]:
        run_daemon()
    elif sys.argv[1:] == ["--stop-background"]:
        stop_background()
    else:
        run()
