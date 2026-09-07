"""
Download YouTube videos (single videos or whole playlists) as audio, then
transcribe them with Whisper and dump the transcripts as plain-text files.

Uses yt-dlp and FFmpeg, then local Whisper transcription.

Usage:
    python scripts/yt_to_docdump.py --url https://youtu.be/VIDEO_ID
    python scripts/yt_to_docdump.py --url https://youtu.be/VIDEO_ID --out school/courses/python101/notes/youtube

Notes:
    - Playlist URLs are expanded automatically (every video downloaded).
    - Already-transcribed videos are skipped (tracked by video id), so the run
      is resumable -- safe to re-run if it gets interrupted.
"""

import argparse
import json
import os
import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Windows consoles default to cp1252; transcripts/titles contain unicode, so
# force UTF-8 on our own stdout/stderr to avoid charmap encode crashes.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# --- Defaults -----------------------------------------------------------------
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "school" / "youtube"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def yt_dlp(args: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    """Run yt-dlp from the same env as this Python, UTF-8 safe on Windows."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--no-warnings", *args],
        capture_output=capture, text=True, encoding="utf-8", env=env,
    )


def expand_urls(urls: list[str]) -> list[dict]:
    """Resolve each URL (expanding playlists) into a flat list of video entries."""
    videos: list[dict] = []
    seen: set[str] = set()
    for url in urls:
        log(f"Resolving {url}")
        res = yt_dlp([
            "--flat-playlist", "--dump-json",
            "--no-warnings", url,
        ])
        if res.returncode != 0:
            log(f"  ! failed to resolve: {res.stderr.strip()[:200]}")
            continue
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = entry.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)
            videos.append({
                "id": vid,
                "title": entry.get("title") or vid,
                # Always use the canonical watch URL -- for a single-video resolve
                # yt-dlp's "url" field is the raw googlevideo stream URL.
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
    return videos


def download_audio(video: dict, audio_dir: Path, attempts: int = 3) -> Path | None:
    """Download a single video as mp3. Returns the mp3 path (or None on failure).

    YouTube downloads are occasionally flaky (throttling / JS-challenge / dropped
    fragments leaving a stale .part), so retry a few times before giving up.
    """
    out_tmpl = str(audio_dir / "%(id)s.%(ext)s")
    mp3 = audio_dir / f"{video['id']}.mp3"
    for attempt in range(1, attempts + 1):
        if mp3.exists():
            return mp3
        res = yt_dlp([
            "--no-playlist",
            "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
            "--retries", "10", "--fragment-retries", "10",
            # Gentle pacing within a download to avoid tripping rate limits.
            "--sleep-requests", "1",
            "-o", out_tmpl,
            video["url"],
        ], capture=True)
        if mp3.exists():
            return mp3
        # Clean up any stale partial download before retrying.
        for part in audio_dir.glob(f"{video['id']}.*"):
            if part.suffix != ".mp3":
                try:
                    part.unlink()
                except OSError:
                    pass
        if attempt < attempts:
            log(f"  ! download attempt {attempt} failed, retrying...")
        else:
            log(f"  ! download failed after {attempts} attempts: "
                f"{res.stderr.strip()[-300:]}")
    return mp3 if mp3.exists() else None


def safe_name(title: str, vid: str) -> str:
    keep = "-_.() "
    cleaned = "".join(c for c in title if c.isalnum() or c in keep).strip()
    cleaned = cleaned[:120].rstrip(". ")
    return f"{cleaned} [{vid}]" if cleaned else vid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="append", dest="urls", required=True,
                    help="YouTube video/playlist URL (repeatable; required).")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="Output folder for transcripts (default: school/youtube).")
    ap.add_argument("--backend", default="openai", choices=["faster", "openai"],
                    help="Transcription engine (default: openai; optional faster-whisper backend).")
    ap.add_argument("--whisper-model", default="base",
                    help="Whisper model: tiny/base/small/medium/large-v3 "
                         "(default base).")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"],
                    help="auto/cuda/cpu (default auto -> cuda when available).")
    ap.add_argument("--sleep", type=float, default=8.0,
                    help="Seconds to wait between downloads to avoid YouTube "
                         "rate-limiting (default 8). Set 0 to disable.")
    ap.add_argument("--prefetch", type=int, default=2,
                    help="How many videos the downloader may stay ahead of the "
                         "transcriber (default 2). Higher = more buffered on disk.")
    ap.add_argument("--keep-audio", action="store_true",
                    help="Keep downloaded mp3s instead of deleting after transcription.")
    args = ap.parse_args()

    for executable in ("ffmpeg", "ffprobe"):
        if not shutil.which(executable):
            ap.error(f"{executable} is missing from PATH. See README.md (Recordings).")
    for package in ("yt_dlp", "torch", "faster_whisper" if args.backend == "faster" else "whisper"):
        if importlib.util.find_spec(package) is None:
            ap.error("Missing optional dependencies. Run: python -m pip install -r requirements-youtube.txt")
    urls = args.urls
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = out_dir / "_audio"
    audio_dir.mkdir(exist_ok=True)

    # Resumability ledger.
    ledger_path = out_dir / "_transcribed.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}

    videos = expand_urls(urls)
    log(f"{len(videos)} video(s) to process. Output -> {out_dir}")
    if not videos:
        log("No videos resolved. Check the URL and update yt-dlp; no model was loaded.")
        return 1

    pending = [v for v in videos if v["id"] not in ledger or not (out_dir / ledger[v["id"]]["transcript"]).is_file() or not (out_dir / ledger[v["id"]]["timestamps"]).is_file()]
    if not pending:
        log("Nothing to do -- everything already transcribed.")
        return 0

    import torch  # imported late so --help is instant

    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        log("  ! cuda requested but not available -- falling back to cpu")
        device = "cpu"
    gpu_name = torch.cuda.get_device_name(0) if device == "cuda" else "CPU"

    # Both backends are normalized to return a dict shaped like openai-whisper's
    # result: {"text": str, "segments": [{"start","end","text"}, ...]}.
    if args.backend == "faster":
        # ctranslate2 needs cuDNN/cuBLAS DLLs at runtime; the torch cu128 wheel
        # bundles them under torch/lib, so make that dir discoverable.
        if device == "cuda" and os.name == "nt":
            _dll_handle = os.add_dll_directory(str(Path(torch.__file__).parent / "lib"))
        from faster_whisper import WhisperModel
        compute_type = "float16" if device == "cuda" else "int8"
        log(f"Loading faster-whisper '{args.whisper_model}' on {device} "
            f"({gpu_name}, {compute_type})...")
        _fw = WhisperModel(args.whisper_model, device=device,
                           compute_type=compute_type)

        def transcribe(path: str) -> dict:
            segments, _info = _fw.transcribe(path, beam_size=5)
            segs = [{"start": s.start, "end": s.end, "text": s.text}
                    for s in segments]  # generator -> realize (runs inference)
            return {"text": "".join(s["text"] for s in segs), "segments": segs}
    else:
        import whisper
        use_fp16 = device == "cuda"  # fp16 on GPU ~2x faster; CPU only does fp32
        log(f"Loading openai-whisper '{args.whisper_model}' on {device} "
            f"({gpu_name})...")
        _ow = whisper.load_model(args.whisper_model, device=device)

        def transcribe(path: str) -> dict:
            return _ow.transcribe(path, fp16=use_fp16)

    for v in videos:
        if v not in pending:
            log(f"SKIP already done: {v['title']}")

    # Producer/consumer: downloads are network-bound, transcription is GPU-bound,
    # so a background thread prefetches the next mp3(s) while the GPU works on the
    # current one. A bounded queue (maxsize=prefetch) plus a per-download sleep
    # means the downloader can never get more than `prefetch` videos ahead, which
    # keeps us from hammering YouTube even though the GPU is fast.
    import queue as _queue
    import threading
    import time

    total = len(pending)
    work_q: _queue.Queue = _queue.Queue(maxsize=max(1, args.prefetch))
    _SENTINEL = object()

    def downloader() -> None:
        for idx, video in enumerate(pending, 1):
            if idx > 1 and args.sleep > 0:
                time.sleep(args.sleep)  # gap between consecutive downloads
            log(f"DOWNLOAD ({idx}/{total}) {video['title']}")
            try:
                mp3 = download_audio(video, audio_dir)
            except Exception as e:  # never let the producer die silently
                log(f"  ! download crashed: {e}")
                mp3 = None
            work_q.put((video, mp3))  # blocks if transcriber is `prefetch` behind
        work_q.put(_SENTINEL)

    dl_thread = threading.Thread(target=downloader, daemon=True)
    dl_thread.start()

    done = 0
    failures = 0
    while True:
        item = work_q.get()
        if item is _SENTINEL:
            break
        video, mp3 = item
        vid = video["id"]
        done += 1
        tag = f"({done}/{total}) {video['title']}"
        if not mp3:
            log(f"  ! skipping (download failed): {tag}")
            failures += 1
            continue

        log(f"TRANSCRIBE {tag}")
        try:
            result = transcribe(str(mp3))
        except Exception as e:
            log(f"  ! transcription error: {e}")
            failures += 1
            continue

        base = safe_name(video["title"], vid)
        txt_path = out_dir / f"{base}.txt"
        ts_path = out_dir / f"{base}_timestamps.txt"

        header = (f"# {video['title']}\n"
                  f"# {video['url']}\n"
                  f"# transcribed {datetime.now().isoformat(timespec='seconds')} "
                  f"({args.backend}-whisper {args.whisper_model})\n\n")
        txt_path.write_text(header + result["text"].strip() + "\n", encoding="utf-8")

        with ts_path.open("w", encoding="utf-8") as f:
            f.write(header)
            for seg in result["segments"]:
                m, s = divmod(int(seg["start"]), 60)
                f.write(f"[{m:02d}:{s:02d}] {seg['text'].strip()}\n")

        dur = result["segments"][-1]["end"] if result["segments"] else 0
        ledger[vid] = {
            "title": video["title"], "url": video["url"],
            "transcript": txt_path.name, "timestamps": ts_path.name,
            "duration_seconds": dur, "chars": len(result["text"]),
            "transcribed_at": datetime.now().isoformat(timespec="seconds"),
        }
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
        log(f"  -> {len(result['text'])} chars, {dur/60:.1f} min  ->  {txt_path.name}")

        if not args.keep_audio:
            try:
                mp3.unlink()
            except OSError:
                pass

    dl_thread.join(timeout=5)
    log(f"DONE. {len(ledger)} transcript(s) in {out_dir}")
    if not args.keep_audio:
        try:
            audio_dir.rmdir()
        except OSError:
            pass
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
