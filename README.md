# RAW File Monitor

A lightweight desktop application for automatically monitoring directories containing mass spectrometry RAW files and organizing them based on user-defined rules.

The application provides a graphical user interface (GUI) for configuring source and destination folders, file matching patterns, file age requirements, and organizational settings. It continuously monitors for eligible files and processes them automatically.

\---

## Features

* Monitor a folder for RAW files
* Regex-based file filtering
* Optional recursive directory scanning
* File age/idle-time validation before processing (DST/clock-change safe)
* Minimum file size filtering
* Automatic file organization into sample/project folders
* Persistent settings saved between sessions
* Activity logging with rotating log files
* Multi-tab support for monitoring several source/destination pairs at once
* GUI-based configuration using Tkinter

\---

## Requirements

### Python

Python 3.9 or newer is recommended.

Check your installation:

```bash
python --version
```

\---

## Dependencies

The application uses only the Python standard library:

* tkinter
* os
* re
* time
* json
* shutil
* logging
* threading
* datetime

These are included with most standard Python installations, so no `pip install` step is required.

\---

## Installation

### Clone the Repository

```bash
git clone https://github.com/lyons89/Raw-File-Mover.git
cd Raw-File-Mover
```

### Create a Virtual Environment (Recommended)

#### Windows

```bash
python -m venv .venv
.venv\\Scripts\\activate
```

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

No further dependency installation is needed — everything used is part of the standard library.

\---

## Running the Application

Launch the application with:

```bash
python raw\_file\_monitor.py
```

The RAW File Monitor GUI should appear.

\---

## Configuration

The application stores settings in:

```text
monitor\_settings.json
```

Typical settings include:

|Setting|Description|
|-|-|
|Source Folder|Directory being monitored|
|Destination Folder|Directory where files are copied|
|Pattern|Regex pattern used to identify eligible files|
|Idle Time|Minimum time a file must remain unchanged before it's considered complete|
|Minimum Size|Minimum file size requirement|
|Recursive|Scan subfolders|
|Organize Files|Automatically sort processed files into sample/project folders|

Settings are automatically loaded when the program starts and saved for future sessions.

\---

## Example Regular Expressions

### Match Every RAW File

```regex
.\*\\.raw$
```

### Match Files Containing "SmithLab"

```regex
^.\*SmithLab.\*\\.raw$
```

Examples matched:

```text
SmithLab.raw
SmithLab\_Run01.raw
20260805\_SmithLab\_Sample.raw
```

Examples not matched:

```text
SmithLab.txt
OtherLab.raw
SmithLab.raw.bak
```

### Match Files Beginning With "Sample"

```regex
^Sample.\*\\.raw$
```

\---

## File Processing Logic

A file is eligible for processing only when:

1. The filename matches the supplied regex pattern.
2. The file exceeds the configured minimum size threshold.
3. The file's size and modified-time have remained unchanged across multiple polling cycles (tracked using a monotonic clock, so it can't be fooled by Daylight Saving Time transitions or other clock changes).
4. The file is not currently held open by another process (e.g. still being written by instrument acquisition software).
5. Monitoring is actively running.

This combination of checks is designed to prevent files from being copied while they are still being written.

\---

## Logging

Application activity is written to:

```text
raw\_file\_monitor.log
```

A rotating log handler is used to prevent log files from becoming excessively large, and automatically recovers from transient write failures (e.g. a locked file or a brief network-drive hiccup) instead of silently going dark. Older log files are retained as numbered backups. A periodic heartbeat line is also written so a stalled monitor is easy to spot in the log itself.

\---

## Future Improvements

Potential enhancements include:

* Email/notification alerts on transfer failure or monitor stall
* Additional file-type support
* Automated archival workflows
* Dashboard reporting

\---

## License

Select the license appropriate for your organization or laboratory before public release.

* MIT License

