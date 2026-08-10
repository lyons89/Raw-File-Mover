\# RAW File Monitor



A lightweight desktop application for automatically monitoring directories containing mass spectrometry RAW files and organizing them based on user-defined rules.



The application provides a graphical user interface (GUI) for configuring source and destination folders, file matching patterns, file age requirements, and organizational settings. It continuously monitors for eligible files and processes them automatically. 【1-e8b9bd】



\---



\## Features



\- Monitor a folder for RAW files

\- Regex-based file filtering

\- Optional recursive directory scanning

\- File age/idle-time validation before processing

\- Minimum file size filtering

\- Automatic file organization

\- Persistent settings saved between sessions

\- Activity logging with rotating log files

\- System tray integration

\- GUI-based configuration using Tkinter



\---



\## Requirements



\### Python



Python 3.9 or newer is recommended.



Check your installation:



```bash

python --version

```



\---



\## Dependencies



Install the required packages:



```bash

pip install pystray pillow

```



The application also uses standard Python libraries including:



\- tkinter

\- os

\- time

\- threading

\- shutil

\- re

\- json

\- logging

\- datetime



These are included with most Python installations. 【1-e8b9bd】



\---



\## Installation



\### Clone the Repository



```bash

git clone https://github.com/YOUR\_USERNAME/raw-file-monitor.git

cd raw-file-monitor

```



\### Create a Virtual Environment (Recommended)



\#### Windows



```bash

python -m venv .venv

.venv\\Scripts\\activate

```



\#### Linux / macOS



```bash

python3 -m venv .venv

source .venv/bin/activate

```



\### Install Dependencies



```bash

pip install pystray pillow

```



\---



\## Running the Application



Launch the application with:



```bash

python raw\_file\_monitor.py

```



The RAW File Monitor GUI should appear.



\---



\## Configuration



The application stores settings in:



```text

monitor\_settings.json

```



Typical settings include:



| Setting | Description |

|----------|-------------|

| Source Folder | Directory being monitored |

| Destination Folder | Directory where files are moved or copied |

| Pattern | Regex pattern used to identify files |

| Idle Time | Minimum time since last file modification |

| Minimum Size | Minimum file size requirement |

| Recursive | Scan subfolders |

| Organize Files | Automatically organize processed files |



Settings are automatically loaded when the program starts and saved for future sessions. 【1-e8b9bd】



\---



\## Example Regular Expressions



\### Match Every RAW File



```regex

.\*\\.raw$

```



\### Match Files Containing "JohnsonLab"



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



\### Match Files Beginning With "Sample"



```regex

^Sample.\*\\.raw$

```



\---



\## File Processing Logic



A file is eligible for processing only when:



1\. The filename matches the supplied regex pattern.

2\. The file exceeds the configured minimum size threshold.

3\. The file has remained unmodified longer than the configured idle period.

4\. Monitoring is actively running.



This helps prevent files from being moved while they are still being written by instrument acquisition software.



\---



\## Logging



Application activity is written to:



```text

raw\_file\_monitor.log

```



A rotating log handler is used to prevent log files from becoming excessively large. Older log files are automatically retained as backups. 



\---





\## Future Improvements



Potential enhancements include:



\- Email notifications

\- Additional file-type support

\- Automated archival workflows

\- File integrity verification

\- Dashboard reporting



\---



\## License



Select the license appropriate for your organization or laboratory before public release.



\- MIT License







