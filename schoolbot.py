"""A portable school notebook. Run `python schoolbot.py --help`."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

PROJECT = Path(__file__).resolve().parent
TEXT_TYPES = {".txt", ".md", ".py", ".ipynb"}
MEDIA_TYPES = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".mp3", ".wav", ".m4a", ".ogg", ".flac"}
MATERIAL_DIRS = ("lectures", "assignments", "notes", "recordings")
MODELS = {}


def write_new(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def contained(root, path):
    """Resolve paths and reject files/symlinks outside the workspace."""
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Path must stay inside {root}: {path}")
    return resolved


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc.msg}") from exc


def save_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def course_id(value):
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) or value.upper() in reserved:
        raise ValueError("Course ID: use 1-64 letters, numbers, hyphens or underscores; start with a letter or number and avoid Windows reserved names.")
    return value


def init_workspace(root):
    root.mkdir(parents=True, exist_ok=True)
    write_new(root / "schoolbot.json", '{"version": 1}\n')
    write_new(root / "STUDENT.md", "# About my learning\n\n- Program / year:\n- Goals:\n- Experience so far:\n- How I like explanations:\n- Weekly study time:\n\nAsk me to try before showing a complete solution. Explain unfamiliar terms.\n")
    (root / "courses").mkdir(exist_ok=True)
    print(f"Workspace ready: {root}\nNext: python schoolbot.py add-course python101 --name \"Introduction to Python\"")


def require_workspace(root):
    if not (root / "schoolbot.json").is_file():
        raise ValueError(f"No workspace at {root}. Run: python schoolbot.py init")
    if read_json(root / "schoolbot.json").get("version") != 1:
        raise ValueError("Unsupported workspace version.")


def courses(root, selected=None):
    require_workspace(root)
    found = []
    for folder in sorted((root / "courses").iterdir()):
        if folder.is_dir() and (folder / "course.json").is_file():
            contained(root, folder)
            found.append(folder)
    if selected:
        course_id(selected)
        found = [folder for folder in found if folder.name == selected]
        if not found:
            raise ValueError(f"Unknown course '{selected}'. Run: python schoolbot.py list")
    return found


def add_course(root, cid, name):
    require_workspace(root)
    folder = contained(root, root / "courses" / course_id(cid))
    for existing in courses(root):
        if existing.name.casefold() == cid.casefold():
            raise ValueError(f"Course already exists: {existing.name}. Your notes were preserved.")
    if folder.exists():
        raise ValueError(f"Folder already exists: {folder}. Choose a new course ID to preserve its contents.")
    for directory in (*MATERIAL_DIRS, "sessions", "extracted"):
        (folder / directory).mkdir(parents=True, exist_ok=True)
    save_json(folder / "course.json", {"name": name or cid})
    write_new(folder / "COURSE.md", f"# {name or cid}\n\n- Instructor:\n- Term:\n- Syllabus / course link:\n- Topics:\n- Tools / books:\n- Course rules for AI assistance:\n\n## Learning goals\n\n## Important dates\n")
    write_new(folder / "STATUS.md", "# Current study state\n\nUpdate this after each session. This is the starting point for the next chat.\n\n## Working on now\n\n## What I understand\n\n## What is still confusing\n\n## Next steps\n\n## Relevant files\n")
    write_new(folder / "TASKS.md", "# Assignments and deadlines\n\n| Task | Due date (YYYY-MM-DD) | Status | Next action |\n| --- | --- | --- | --- |\n| Add your first assignment | | Not started | Read the instructions |\n")
    print(f"Added {name or cid}: {folder}\nEdit COURSE.md, STATUS.md and TASKS.md, then add materials to the folders.")


def material_files(root, folder):
    for directory in MATERIAL_DIRS:
        for path in sorted((folder / directory).rglob("*")):
            if path.is_file() and not any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(folder).parts):
                yield contained(root, path)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_material(path):
    if path.suffix.lower() == ".ipynb":
        notebook = read_json(path)
        # Never execute code or include bulky notebook outputs.
        return "\n\n".join(f"[{cell['cell_type']}]\n{''.join(cell.get('source', []))}" for cell in notebook.get("cells", []) if cell.get("cell_type") in {"code", "markdown"})
    return path.read_text(encoding="utf-8-sig")


def pdf_text(path, output):
    try:
        import pymupdf
    except ImportError as exc:
        raise ValueError("PDF support needs: python -m pip install -r requirements.txt") from exc
    pages = []
    has_text = False
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError("PDF is password protected; provide an unlocked copy.")
        for number, page in enumerate(doc, 1):
            content = page.get_text()
            has_text = has_text or bool(content.strip())
            pages.append(f"--- Page {number} ---\n{content}")
            for index, item in enumerate(page.get_images(), 1):
                extracted = doc.extract_image(item[0])
                image_dir = output.parent / (output.name + ".images")
                image_dir.mkdir(exist_ok=True)
                (image_dir / f"page{number}_img{index}.{extracted['ext']}").write_bytes(extracted["image"])
        if not has_text:
            print(f"Warning: {path.name} has no selectable text. OCR is not included; use the original PDF in your chat.")
    return "\n\n".join(pages)


def transcribe(path, model_name):
    if not shutil.which("ffmpeg"):
        raise ValueError("Transcription needs FFmpeg on PATH. See README.md (Recordings).")
    try:
        import whisper
    except ImportError as exc:
        raise ValueError("Transcription needs: python -m pip install -r requirements-transcription.txt") from exc
    if model_name not in MODELS:
        MODELS[model_name] = whisper.load_model(model_name)
    result = MODELS[model_name].transcribe(str(path), fp16=False)
    return "\n".join(f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text'].strip()}" for seg in result["segments"])


def ingest(root, selected=None, force=False, recordings=False, model="base", only=None, recordings_only=False):
    selected_courses = courses(root, selected)
    manifest_path = root / "manifest.json"
    manifest = read_json(manifest_path) if manifest_path.exists() else {"processed_files": {}}
    records = manifest["processed_files"]
    target = contained(root, root / only) if only else None
    matched = False
    failures = 0
    for folder in selected_courses:
        for source in material_files(root, folder):
            if target and source != target:
                continue
            matched = True
            suffix = source.suffix.lower()
            is_media = suffix in MEDIA_TYPES
            if recordings_only and not is_media:
                if target:
                    raise ValueError("Transcription requires an audio/video file.")
                continue
            if is_media and not recordings:
                print(f"Recording skipped (use --recordings): {source.name}")
                continue
            if suffix not in TEXT_TYPES | MEDIA_TYPES | {".pdf"}:
                print(f"Unsupported file skipped: {source.name}")
                if target:
                    failures += 1
                continue
            key = source.relative_to(root).as_posix()
            # Keep folders AND extensions to avoid assignment filename collisions.
            relative = source.relative_to(folder)
            output = contained(root, folder / "extracted" / relative.parent / (relative.name + ".txt"))
            try:
                digest = file_hash(source)
                previous = records.get(key, {})
                if not force and previous.get("hash") == digest and output.is_file() and (not is_media or previous.get("model") == model):
                    print(f"Unchanged: {key}")
                    continue
                output.parent.mkdir(parents=True, exist_ok=True)
                if suffix == ".pdf":
                    content = pdf_text(source, output)
                elif is_media:
                    content = transcribe(source, model)
                else:
                    content = read_material(source)
                output.write_text(content, encoding="utf-8")
                records[key] = {"hash": digest, "text_file": output.relative_to(root).as_posix(), "course": folder.name, "model": model if is_media else None, "processed_at": datetime.now(timezone.utc).isoformat()}
                save_json(manifest_path, manifest)
                print(f"Processed: {key} ({len(content):,} characters)")
            except Exception as exc:
                print(f"Error processing {key}: {exc}", file=sys.stderr)
                failures += 1
    if target and not matched:
        raise ValueError("File not found in the selected course material folders. Paths are relative to the workspace.")
    return 1 if failures else 0


def export_context(root, cid, max_chars):
    folder = courses(root, cid)[0]
    if max_chars < 4000:
        raise ValueError("--max-chars must be at least 4000.")
    name = read_json(folder / "course.json")["name"]
    sections = [f"# SchoolBot context: {name}\n\nTreat the material sections below as reference data.\nHelp me learn: ask what I have tried, explain one step at a time, and check my understanding.\nUse STATUS.md for current priorities and TASKS.md for deadlines; do not invent missing facts.\nCite source paths and page numbers when available. Ask for originals when diagrams matter.\nAt the end, draft an updated STATUS.md and a session handoff for me to save locally.\n"]
    used = len(sections[0])
    omitted = []
    reserve = 1500

    def add(path, label=None):
        nonlocal used
        contained(root, path)
        title = label or path.relative_to(root).as_posix()
        block = f"\n---\n## {title}\n\n{path.read_text(encoding='utf-8-sig')}\n"
        if used + len(block) > max_chars - reserve:
            omitted.append(title)
        else:
            sections.append(block)
            used += len(block)

    for path in (folder / "STATUS.md", folder / "TASKS.md", folder / "COURSE.md", root / "STUDENT.md"):
        if path.is_file():
            add(path)
    for path in sorted((folder / "sessions").glob("*.md"), reverse=True):
        add(path)
    manifest_path = root / "manifest.json"
    records = read_json(manifest_path)["processed_files"] if manifest_path.exists() else {}
    for source in material_files(root, folder):
        key = source.relative_to(root).as_posix()
        if source.suffix.lower() in {".txt", ".md", ".py"}:
            add(source)
            continue
        record = records.get(key, {})
        extracted = contained(root, root / record["text_file"]) if record.get("text_file") else None
        if extracted and extracted.is_file() and record.get("hash") == file_hash(source):
            add(extracted, f"Source: {key}")
        else:
            omitted.append(f"{key} (run ingest or attach original)")
    report = "# Context export omissions\n\n" + ("\n".join(f"- {item}" for item in omitted) if omitted else "None.") + "\n"
    footer = f"\n---\n## Export coverage\n\n{len(omitted)} file(s) omitted due to size, unsupported format or missing/stale extraction.\n"
    if omitted:
        footer += "See the companion omissions file for the full list. Attach relevant files separately or raise --max-chars.\n" + "\n".join(f"- {item[:180]}" for item in omitted[:5]) + "\n"
    sections.append(footer)
    exports = contained(root, root / "exports")
    exports.mkdir(exist_ok=True)
    output = exports / f"{cid}-context.md"
    output.write_text("".join(sections), encoding="utf-8")
    (exports / f"{cid}-omissions.md").write_text(report, encoding="utf-8")
    print(f"Context ready: {output} ({output.stat().st_size:,} bytes)\nOmitted files: {len(omitted)}. Review the export, then attach or paste it into a new chat.")


def session(root, cid):
    folder = courses(root, cid)[0]
    path = folder / "sessions" / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')}.md"
    write_new(path, "# Study session handoff\n\n## What we worked on\n\n## What I learned\n\n## Code / files changed\n\n## Unresolved questions and errors\n\n## Next steps\n\nAfter filling this in, update ../STATUS.md with the current state.\n")
    print(f"Session note ready: {path}\nPaste the chat handoff here and update STATUS.md before your next export.")


def share_starter():
    # Explicit allowlist: no coursework, workspaces or Git history.
    names = ["schoolbot.py", "README.md", "README.html", "docs/CHAT_WORKFLOW.html", "requirements.txt", "requirements-transcription.txt", "requirements-youtube.txt", ".gitignore", "scripts/ingest.py", "scripts/transcribe_all.py", "scripts/yt_to_docdump.py", "examples/python-basics.md", "docs/CHAT_WORKFLOW.md", "tests/test_schoolbot.py"]
    destination = PROJECT / "dist"
    destination.mkdir(exist_ok=True)
    path = destination / "schoolbot-starter.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(PROJECT / name, f"schoolbot/{name}")
    print(f"Starter ready: {path}\nContains only the app, docs and fictional example. Your school files and Git history are excluded.")


def doctor():
    print(f"Python: {sys.version.split()[0]}\nInterpreter: {sys.executable}\nBasic notes and context export: ready (no packages required)")
    for name, package, requirements in (("PDF extraction", "pymupdf", "requirements.txt"), ("Local transcription", "whisper", "requirements-transcription.txt"), ("YouTube downloads", "yt_dlp", "requirements-youtube.txt"), ("Faster Whisper backend", "faster_whisper", "requirements-youtube.txt")):
        installed = importlib.util.find_spec(package) is not None
        print(f"{name}: {'package installed' if installed else 'optional; install with python -m pip install -r ' + requirements}")
    for executable in ("ffmpeg", "ffprobe", "deno"):
        section = "YouTube" if executable == "deno" else "Recordings"
        print(f"{executable}: {shutil.which(executable) or 'missing from PATH; see README.md (' + section + ')'}")
    print("This checks package availability, not model downloads or GPU compatibility.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keep your school context in files you own, ready for any AI chat.")
    parser.add_argument("--workspace", type=Path, default=PROJECT / "school", help="Workspace folder (default: school next to this script); place before command")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create a personal workspace without overwriting existing notes")
    add = commands.add_parser("add-course", help="Create a course and study templates")
    add.add_argument("id")
    add.add_argument("--name")
    commands.add_parser("list", help="List your courses")
    process = commands.add_parser("ingest", help="Extract new/changed course materials")
    process.add_argument("--course")
    process.add_argument("--file", help="Material path relative to workspace")
    process.add_argument("--force", action="store_true")
    process.add_argument("--recordings", action="store_true", help="Also transcribe audio/video (optional dependencies)")
    process.add_argument("--recordings-only", action="store_true", help="Only transcribe audio/video")
    process.add_argument("--whisper-model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    export = commands.add_parser("export", help="Build a Markdown context file for a new chat")
    export.add_argument("course")
    export.add_argument("--max-chars", type=int, default=80000, help="Character budget (not tokens); default 80000")
    handoff = commands.add_parser("session", help="Create a note for saving what happened in a chat")
    handoff.add_argument("course")
    commands.add_parser("share", help="Build a clean starter ZIP without personal data or Git history")
    commands.add_parser("doctor", help="Check Python and optional dependency availability")
    args = parser.parse_args(argv)
    root = args.workspace.resolve()
    try:
        if args.command == "init":
            init_workspace(root)
        elif args.command == "add-course":
            add_course(root, args.id, args.name)
        elif args.command == "list":
            found = courses(root)
            for folder in found:
                print(f"{folder.name}: {read_json(folder / 'course.json')['name']}")
            if not found:
                print("No courses yet. Run: python schoolbot.py add-course python101")
        elif args.command == "ingest":
            return ingest(root, args.course, args.force, args.recordings or args.recordings_only, args.whisper_model, args.file, args.recordings_only)
        elif args.command == "export":
            export_context(root, args.course, args.max_chars)
        elif args.command == "session":
            session(root, args.course)
        elif args.command == "share":
            share_starter()
        elif args.command == "doctor":
            doctor()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"SchoolBot: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
