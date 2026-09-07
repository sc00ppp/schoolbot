"""Behavior tests use isolated workspaces; no network, chat service or model download."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import shutil
import sys
import unittest
import uuid
from unittest.mock import Mock, patch
import zipfile

import schoolbot as sb


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.test_root = sb.PROJECT / ".test-workspaces"
        self.test_root.mkdir(exist_ok=True)
        # Inherit workspace permissions (Python 3.14's private temporary-dir
        # ACLs can make the directory unreadable in a Windows app sandbox).
        self.root = (self.test_root / uuid.uuid4().hex).resolve()
        self.root.mkdir()
        self.addCleanup(self.clean_workspace)
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)
        sb.init_workspace(self.root)
        sb.add_course(self.root, "python101", "Introduction to Python")
        self.course = self.root / "courses" / "python101"

    def clean_workspace(self):
        if not self.root.is_relative_to(self.test_root.resolve()):
            raise ValueError("Test cleanup must stay within the test workspace.")
        shutil.rmtree(self.root)

    def put(self, relative, content):
        path = self.course / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def export(self, limit=80000):
        sb.export_context(self.root, "python101", limit)
        return (self.root / "exports" / "python101-context.md").read_text(encoding="utf-8")

    def test_repeat_init_and_duplicate_course_preserve_notes(self):
        (self.root / "STUDENT.md").write_text("My learning preferences", encoding="utf-8")
        self.put("STATUS.md", "Keep my progress")
        sb.init_workspace(self.root)
        with self.assertRaisesRegex(ValueError, "already exists"):
            sb.add_course(self.root, "PYTHON101", "Duplicate")
        self.assertEqual((self.root / "STUDENT.md").read_text(), "My learning preferences")
        self.assertEqual((self.course / "STATUS.md").read_text(), "Keep my progress")

    def test_portable_context_contains_progress_and_only_selected_course(self):
        self.put("STATUS.md", "Currently stuck on return values")
        self.put("TASKS.md", "Lab due 2026-10-02")
        self.put("notes/lesson.md", "A function returns a value: café")
        self.put("sessions/2026-09-07.md", "Next: practice return vs print")
        sb.add_course(self.root, "biology", "Biology")
        (self.root / "courses/biology/notes/private.md").write_text("OTHER COURSE", encoding="utf-8")
        text = self.export()
        for phrase in ("return values", "2026-10-02", "café", "return vs print", "courses/python101/notes/lesson.md"):
            self.assertIn(phrase, text)
        self.assertNotIn("OTHER COURSE", text)

    def test_ingest_preserves_nested_names_and_reprocesses_changes(self):
        first = self.put("assignments/hw1/notes.md", "First homework")
        self.put("assignments/hw2/notes.md", "Second homework")
        self.assertEqual(sb.ingest(self.root), 0)
        result = self.course / "extracted/assignments/hw1/notes.md.txt"
        unchanged_time = result.stat().st_mtime_ns
        self.assertEqual(sb.ingest(self.root), 0)
        self.assertEqual(result.stat().st_mtime_ns, unchanged_time)
        first.write_text("Changed homework", encoding="utf-8")
        sb.ingest(self.root)
        self.assertEqual(result.read_text(), "Changed homework")
        self.assertEqual((self.course / "extracted/assignments/hw2/notes.md.txt").read_text(), "Second homework")
        result.unlink()
        sb.ingest(self.root)
        self.assertTrue(result.exists())

    def test_notebooks_are_read_without_execution_or_outputs(self):
        self.put("notes/example.ipynb", json.dumps({"cells": [
            {"cell_type": "markdown", "source": ["# Notebook notes"]},
            {"cell_type": "code", "source": ["raise RuntimeError('DO NOT EXECUTE')"], "outputs": [{"text": "HUGE OUTPUT"}]}
        ]}))
        self.assertEqual(sb.ingest(self.root), 0)
        text = self.export()
        self.assertIn("Notebook notes", text)
        self.assertIn("DO NOT EXECUTE", text)
        self.assertNotIn("HUGE OUTPUT", text)

    def test_changed_and_deleted_notebooks_do_not_export_stale_text(self):
        source = self.put("notes/old.ipynb", '{"cells":[{"cell_type":"markdown","source":["STALE CONTENT"]}]}')
        sb.ingest(self.root)
        source.write_text('{"cells":[]}', encoding="utf-8")
        text = self.export()
        self.assertNotIn("STALE CONTENT", text)
        self.assertIn("run ingest", text)
        source.unlink()
        self.assertNotIn("STALE CONTENT", self.export())

    def test_budget_reports_omitted_files_without_truncating_them(self):
        self.put("STATUS.md", "CURRENT PRIORITY")
        self.put("notes/large.txt", "LARGE CONTENT " * 2000)
        text = self.export(4000)
        self.assertLessEqual(len(text), 4000)
        self.assertIn("CURRENT PRIORITY", text)
        self.assertNotIn("LARGE CONTENT", text)
        report = (self.root / "exports/python101-omissions.md").read_text()
        self.assertIn("notes/large.txt", report)

    def test_bad_course_and_file_paths_fail(self):
        for cid in ("../outside", "CON", "bad/name", "has spaces"):
            with self.subTest(cid=cid), self.assertRaises(ValueError):
                sb.add_course(self.root, cid, None)
        with self.assertRaisesRegex(ValueError, "Unknown course"):
            sb.ingest(self.root, "missing")
        with self.assertRaisesRegex(ValueError, "inside"):
            sb.ingest(self.root, only="../outside.txt")
        with self.assertRaisesRegex(ValueError, "not found"):
            sb.ingest(self.root, only="courses/python101/notes/missing.txt")

    def test_failed_file_does_not_lose_successful_progress(self):
        self.put("notes/a-good.md", "Good content")
        self.put("notes/z-broken.ipynb", "not json")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(sb.ingest(self.root), 1)
        manifest = sb.read_json(self.root / "manifest.json")["processed_files"]
        self.assertIn("courses/python101/notes/a-good.md", manifest)
        self.assertNotIn("courses/python101/notes/z-broken.ipynb", manifest)

    def test_recordings_are_opt_in_resume_and_honor_model(self):
        self.put("recordings/one.MP4", "fake video bytes")
        self.put("recordings/two.ogg", "fake audio bytes")
        with patch.object(sb, "transcribe", return_value="[0.00 - 1.00] Loop lesson") as fake:
            sb.ingest(self.root)
            fake.assert_not_called()
            sb.ingest(self.root, recordings=True, model="tiny")
            self.assertEqual(fake.call_count, 2)
            self.assertEqual(fake.call_args.args[1], "tiny")
            sb.ingest(self.root, recordings=True, model="tiny")
            self.assertEqual(fake.call_count, 2)
            sb.ingest(self.root, recordings=True, model="small")
            self.assertEqual(fake.call_count, 4)
        self.assertIn("[0.00 - 1.00] Loop lesson", self.export())

    def test_transcription_model_loaded_once_and_timestamps_saved(self):
        fake_model = Mock()
        fake_model.transcribe.return_value = {"segments": [{"start": 0, "end": 2.5, "text": " Hello "}]}
        fake_whisper = Mock()
        fake_whisper.load_model.return_value = fake_model
        with patch.dict(sb.MODELS, {}, clear=True), patch.dict(sys.modules, {"whisper": fake_whisper}), patch.object(sb.shutil, "which", return_value="ffmpeg"):
            for name in ("first.mp3", "second.mp3"):
                self.assertEqual(sb.transcribe(Path(name), "tiny"), "[0.00 - 2.50] Hello")
            fake_whisper.load_model.assert_called_once_with("tiny")
            self.assertEqual(fake_model.transcribe.call_count, 2)

    def test_missing_ffmpeg_has_actionable_error(self):
        with patch.object(sb.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "FFmpeg on PATH"):
                sb.transcribe(Path("recording.mp3"), "base")

    def test_cli_works_from_another_directory_and_legacy_wrapper(self):
        command = [sys.executable, str(sb.PROJECT / "schoolbot.py"), "--workspace", str(self.root)]
        completed = subprocess.run([*command, "export", "python101"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        completed = subprocess.run([sys.executable, str(sb.PROJECT / "scripts/ingest.py"), "--workspace", str(self.root)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        completed = subprocess.run([*command, "export", "missing"], cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertNotIn("Traceback", completed.stderr)

    @unittest.skipUnless(importlib.util.find_spec("pymupdf"), "optional PyMuPDF not installed")
    def test_pdf_extraction_keeps_pages_and_assignment_paths(self):
        import pymupdf
        for name in ("hw1", "hw2"):
            folder = self.course / "assignments" / name
            folder.mkdir()
            with pymupdf.open() as doc:
                doc.new_page().insert_text((72, 72), f"Assignment {name}: Python loops")
                doc.save(folder / "instructions.PDF")
        self.assertEqual(sb.ingest(self.root), 0)
        text = self.export()
        self.assertIn("Assignment hw1", text)
        self.assertIn("Assignment hw2", text)
        self.assertIn("--- Page 1 ---", text)

    def test_starter_archive_excludes_personal_files_and_history(self):
        # Patch PROJECT to fixture with sentinel private data and only required files.
        project = self.root / "project"
        project.mkdir()
        for relative in ("schoolbot.py", "README.md", "README.html", "docs/CHAT_WORKFLOW.html", "requirements.txt", "requirements-transcription.txt", "requirements-youtube.txt", ".gitignore", "scripts/ingest.py", "scripts/transcribe_all.py", "scripts/yt_to_docdump.py", "examples/python-basics.md", "docs/CHAT_WORKFLOW.md", "tests/test_schoolbot.py"):
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("starter", encoding="utf-8")
        for relative in ("AI/private.pdf", "school/STUDENT.md", ".git/config", "COURSE_SUMMARY.md"):
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("PRIVATE", encoding="utf-8")
        with patch.object(sb, "PROJECT", project):
            sb.share_starter()
        with zipfile.ZipFile(project / "dist/schoolbot-starter.zip") as archive:
            self.assertEqual(len(archive.namelist()), 14)
            for name in archive.namelist():
                self.assertNotIn(b"PRIVATE", archive.read(name))

    def test_youtube_transcript_exports_and_rerun_skips_model_loading(self):
        from scripts import yt_to_docdump as yt
        output = self.course / "notes" / "youtube"
        fake_model = Mock()
        fake_model.transcribe.return_value = {"text": "Loops visit each item.", "segments": [{"start": 0, "end": 3, "text": "Loops visit each item."}]}
        fake_whisper = Mock()
        fake_whisper.load_model.return_value = fake_model
        fake_torch = Mock()
        fake_torch.cuda.is_available.return_value = False

        def download(video, audio_dir):
            path = audio_dir / "test-id.mp3"
            path.write_bytes(b"fixture audio")
            return path

        with patch.object(sys, "argv", ["yt_to_docdump.py", "--url", "https://youtube.com/watch?v=test-id", "--out", str(output)]), patch.object(yt.shutil, "which", return_value="available"), patch.object(yt.importlib.util, "find_spec", return_value=True), patch.object(yt, "expand_urls", return_value=[{"id": "test-id", "title": "Python loops", "url": "https://youtube.com/watch?v=test-id"}]), patch.object(yt, "download_audio", side_effect=download), patch.dict(sys.modules, {"torch": fake_torch, "whisper": fake_whisper}):
            self.assertEqual(yt.main(), 0)
            self.assertEqual(yt.main(), 0)
            fake_whisper.load_model.assert_called_once_with("base", device="cpu")
        self.assertIn("Loops visit each item.", self.export())
        self.assertIn("test-id", sb.read_json(output / "_transcribed.json"))
        self.assertFalse((output / "_audio/test-id.mp3").exists())

    def test_youtube_requires_explicit_urls(self):
        from scripts import yt_to_docdump as yt
        with patch.object(sys, "argv", ["yt_to_docdump.py"]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            yt.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
