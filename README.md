# SchoolBot

**Keep your school context in files you own. Pick up in any AI chat.**

SchoolBot is a small Python tool for organizing classes, extracting study
materials, and carrying your progress into a fresh chat. Use it for Python,
biology, history, trade school, or any other subject.

Your notes, assignments, deadlines, and "where was I?" live in a local folder.
A chat can help you study; it doesn't have to be the only place that remembers
what you're doing. No SchoolBot account, API key, or paid AI integration needed.

```text
Materials + study status + saved chat handoffs
                    |
             schoolbot export
                    |
          One readable Markdown file
                    |
              A fresh AI chat
```

[Start here](#quick-start) · [Chat workflow](docs/CHAT_WORKFLOW.md) ·
[Recordings](#recordings-optional) · [YouTube](#youtube-optional) ·
[Troubleshooting](#troubleshooting)

## What it does

- Creates as many courses as you need, each with study and deadline templates.
- Reads Markdown, text, Python files, and notebook code/Markdown cells.
- Extracts PDF text with page numbers and embedded images (optional install).
- Transcribes local audio/video with timestamps using Whisper (optional install).
- Downloads and transcribes YouTube videos or playlists (optional install).
- Exports a course's context for a new chat, with source paths and an omissions report.
- Skips unchanged materials and saves progress after each successful extraction.

It is a folder-based command-line tool, not a chat app or calendar service.
It does not automatically read chats, save chat replies, generate summaries,
execute your notebooks, or send reminders. Saving a short handoff after studying
is the part that makes your context portable.

## Quick start

### 1. Get the folder and Python

On GitHub, choose **Code → Download ZIP** and extract it, or clone the repo:

```sh
git clone https://github.com/sc00ppp/schoolbot.git
cd schoolbot
```

You can also unzip a `schoolbot-starter.zip` shared by a friend. Open a terminal
**inside the extracted project folder**, where this README and `schoolbot.py`
live. On Windows, right-click the folder and choose **Open in Terminal**.

Install [Python](https://www.python.org/downloads/) if needed. The basic tool
requires Python 3.10 or newer. **Python 3.11 is a conservative choice if you
want Whisper too**; see its [upstream setup notes](https://github.com/openai/whisper#setup).
On Windows, enable the installer's PATH option. Check:

```sh
python --version
```

On macOS/Linux, use `python3` wherever this guide says `python` until you have
activated a virtual environment. If Windows recognizes `py` but not `python`,
use `py` for the basic commands.

### 2. Create your first course

No packages to install for this step:

```sh
python schoolbot.py init
python schoolbot.py add-course python101 --name "Introduction to Python"
python schoolbot.py export python101
```

Open `school/exports/python101-context.md`. That's your first portable context
file. `.md` means Markdown: ordinary text you can edit in any text editor.

### 3. Make it yours

Edit these files in any text editor:

- `school/STUDENT.md`: how you learn and what you're aiming for.
- `school/courses/python101/COURSE.md`: course details and topics.
- `school/courses/python101/STATUS.md`: what you're doing and where you're stuck.
- `school/courses/python101/TASKS.md`: assignments and deadlines.

Drop notes or `.py` files into the course's `notes/` folder. To try a ready-made
example, copy `examples/python-basics.md` there using your file manager.
Then run:

```sh
python schoolbot.py ingest --course python101
python schoolbot.py export python101
```

Attach or paste the exported context into a new Claude chat or another AI chat.
Try: **"Read my current status. Help me practice loops, one question at a time."**

### 4. Save the outcome, not just the conversation

Before leaving the chat, ask it for an updated `STATUS.md` and a handoff listing
what you learned, unresolved problems, files changed, and next steps.

```sh
python schoolbot.py session python101
```

Paste the handoff into the new session file printed by that command. Save the
updated status in `STATUS.md`. Export again before starting your next chat.
[Full prompts, including rescuing context from an old chat →](docs/CHAT_WORKFLOW.md)

## Your workspace

```text
school/                         # Your personal data; ignored by Git
├── schoolbot.json
├── STUDENT.md
├── manifest.json               # Created on first successful ingestion
├── courses/
│   └── python101/
│       ├── course.json         # Display name
│       ├── COURSE.md
│       ├── STATUS.md
│       ├── TASKS.md
│       ├── lectures/           # Slides, syllabus, lecture notes
│       ├── assignments/        # Subfolders such as hw1/, hw2/ are fine
│       ├── notes/              # Notes, practice code, saved explanations
│       ├── recordings/        # Audio/video to transcribe
│       ├── sessions/          # Saved chat handoffs
│       └── extracted/         # Generated text and PDF images
└── exports/
    ├── python101-context.md
    └── python101-omissions.md
```

Add another class with `python schoolbot.py add-course biology --name "Biology"`.
Course IDs use letters, numbers, hyphens and underscores, with no spaces.
Use separate IDs such as `fall26-biology` for different terms.

## Optional installs

Create a **virtual environment** once: a folder for this project's Python
packages. Activate it again whenever you open a new terminal to use these features.

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation, use the environment's Python directly, e.g.
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and
`.\.venv\Scripts\python.exe schoolbot.py ingest`. No execution-policy change needed.

**macOS / Linux:**

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### PDFs

```sh
python -m pip install -r requirements.txt
python schoolbot.py ingest --course python101
```

Put PDFs into `lectures/`, `assignments/`, or `notes/`. Extracted text keeps page
numbers. Embedded images are saved beside the extracted text, but are not
included in Markdown exports. Attach original PDFs when diagrams or layout
matter. Image-only scans need OCR outside SchoolBot.
[PyMuPDF installation reference](https://pymupdf.readthedocs.io/en/latest/installation.html).

### Recordings (optional)

**1. Install Whisper in your activated environment:**

```sh
python -m pip install -r requirements-transcription.txt
```

**2. Install FFmpeg**, the audio/video decoder. Both `ffmpeg` and `ffprobe`
come with a full FFmpeg distribution. This is a system tool, not the Python
package named `ffmpeg`.

| System | Install |
| --- | --- |
| Windows | If you use Chocolatey: `choco install ffmpeg`; if you use Scoop: `scoop install ffmpeg` |
| macOS with Homebrew | `brew install ffmpeg` |
| Ubuntu / Debian | `sudo apt install ffmpeg` |

On Windows without a package manager, use the Windows builds linked from the
[official FFmpeg downloads page](https://ffmpeg.org/download.html). Extract the
archive and add its `bin` folder (containing `ffmpeg.exe` and `ffprobe.exe`) to
your user PATH through **Edit environment variables for your account → Path →
Edit → New**. Open a new terminal afterward and activate `.venv` again.

Check setup:

```sh
ffmpeg -version
ffprobe -version
python schoolbot.py doctor
```

**3. Drop a recording into `school/courses/python101/recordings/`, then run:**

```sh
python schoolbot.py ingest --course python101 --recordings
python schoolbot.py export python101
```

Supported formats: MP4, MKV, AVI, MOV, WebM, MP3, WAV, M4A, OGG, FLAC.
Transcripts contain timestamps and feed into context exports. The first run
downloads the selected model; transcription then runs locally. No API key.
CPU operation is supported, but long recordings can take a while. Start with
`base`; try `tiny` for speed or `small` for more accuracy. Model tradeoffs and
installation details are in the [Whisper README](https://github.com/openai/whisper).

```sh
# Only recordings, across every course
python scripts/transcribe_all.py

# One course, with a different model
python scripts/transcribe_all.py --course python101 --whisper-model small

# One recording (path relative to school/, not the project folder)
python schoolbot.py ingest --file courses/python101/recordings/week1.mp4 --recordings
```

Changing the model reprocesses recordings. Use `--force` to retry an unchanged
file. The model is loaded once per batch; successful files are recorded as the
batch progresses, so rerunning resumes work.

### YouTube (optional)

Install FFmpeg as above, then the downloader and transcription packages:

```sh
python -m pip install -r requirements-youtube.txt
```

Install [Deno](https://docs.deno.com/runtime/getting_started/installation/) too:
yt-dlp uses this JavaScript runtime for YouTube support. On Windows with Scoop,
run `scoop install deno`; on macOS with Homebrew, run `brew install deno`. Other
platforms can use the installers on that page. Reopen your terminal, reactivate
the virtual environment, and check `deno --version`. Then:

```sh
python scripts/yt_to_docdump.py --url "https://www.youtube.com/watch?v=VIDEO_ID" --out "school/courses/python101/notes/youtube"
python schoolbot.py export python101
```

Replace `VIDEO_ID` with the actual video ID. Repeat `--url` for multiple videos
or supply a playlist URL to process the entire playlist. The example output
folder makes the transcripts part of the course's next export automatically.
Without `--out`, transcripts go to `school/youtube/` and aren't attached to a course.

The default uses Whisper `base`. `--backend faster` selects the included
faster-whisper backend; `--device cpu` avoids GPU setup; `--whisper-model small`
changes the model. `--keep-audio` retains downloaded MP3s. Completed videos are
tracked in the output folder and skipped on reruns. Remove their ledger entries
from `_transcribed.json` if you want to regenerate them with a different model.

YouTube requirements change. If downloads fail, update with
`python -m pip install -U "yt-dlp[default]"` and consult the
[yt-dlp dependency instructions](https://github.com/yt-dlp/yt-dlp#dependencies),
including its JavaScript runtime requirements. Use recordings you have permission
to download and process.

## Command reference

| Command | Purpose |
| --- | --- |
| `python schoolbot.py init` | Create a workspace; preserve existing notes |
| `python schoolbot.py add-course ID --name "Course name"` | Create a course |
| `python schoolbot.py list` | List courses |
| `python schoolbot.py ingest` | Process new/changed text, notebooks and PDFs |
| `python schoolbot.py ingest --course ID --recordings` | Also transcribe audio/video |
| `python schoolbot.py export ID` | Build a context file, default 80,000-character budget |
| `python schoolbot.py export ID --max-chars 200000` | Raise the export budget |
| `python schoolbot.py session ID` | Create a blank handoff note |
| `python schoolbot.py doctor` | Check optional dependencies |
| `python schoolbot.py share` | Build a clean starter ZIP |

Put `--workspace "path/to/my-school"` **before** the command to use another
workspace, e.g. `python schoolbot.py --workspace "../my-school" init`.
The default workspace stays next to the script even if you run it from another
folder. Custom workspaces inside this repository need their own `.gitignore` entry.
`python scripts/ingest.py` remains a shortcut for the new ingestion command.

Exports prioritize current status and deadlines, course/student information,
then session notes newest first, then materials. Whole sections that don't fit
are omitted, not silently cut off. The omissions report lists every omitted file.
The budget counts characters, not tokens; a chat service may have a smaller limit.
Old extraction files are excluded if their source changed or was removed.
Word documents, spreadsheets, standalone images and other unsupported files
must be attached separately or converted to supported formats.

## Sharing and existing SchoolBot users

```sh
python schoolbot.py share
```

Send `dist/schoolbot-starter.zip` to a friend. It contains only the tool, docs,
and a fictional example, with no personal coursework or Git history.

The original `AI/`, `ML/`, root `manifest.json`, and `COURSE_SUMMARY.md` are
kept locally and ignored by Git; they are no longer in the current shared file tree. The new tool uses `school/` and doesn't read
them automatically. To use old material, create courses and **copy** the wanted
files into their material folders; copy useful parts of the old summary into
`notes/`, then run ingestion. Existing extraction manifests aren't migrated.
The new README and starter package apply to the general-purpose workspace.

The shared repository starts with a clean history containing only the
general-purpose tool, documentation, and fictional example. Personal coursework
is excluded from both the current files and the published history.

## Troubleshooting

| Problem | Try this |
| --- | --- |
| `python` not found | Reopen the terminal after installing Python; Windows: try `py`; macOS/Linux: `python3` |
| `schoolbot.py` not found | Open the terminal in the extracted project folder |
| No workspace / unknown course | Run `init`, then `add-course`; use `list` to check the exact ID |
| Missing package after installation | Activate the same `.venv`; `doctor` prints the Python interpreter being used |
| Whisper won't install on a very new Python | Create the environment with Python 3.11 (Windows: `py -3.11 -m venv .venv311`) and activate it |
| FFmpeg missing | Install the full FFmpeg distribution, add its `bin` folder to PATH, and reopen the terminal |
| Transcription is slow | Test a short recording with `--whisper-model tiny` first |
| GPU library error in YouTube mode | Add `--device cpu` |
| Export doesn't contain a file | Read the omissions report; ingest changed PDFs/notebooks/recordings, raise the budget, or attach the original |
| The new chat doesn't know what happened | Save a handoff and update `STATUS.md`, then export again |

Back up the entire `school/` folder, not just exports. Local processing does not
upload course files; attaching an export to a chat shares its contents with that
service. Review the file before sharing it.

## Development

Core workflow tests use Python's standard library:

```sh
python -m unittest discover -s tests -v
```

PDF tests run when PyMuPDF is installed. Transcription integration is tested with
a fake model so the suite doesn't download model weights or require a GPU.
