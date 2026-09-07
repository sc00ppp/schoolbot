"""Transcribe recordings in any configured course; no machine-specific paths."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schoolbot import main


if __name__ == "__main__":
    args = sys.argv[1:]
    workspace = []
    if "--workspace" in args:
        index = args.index("--workspace")
        workspace = args[index:index + 2]
        del args[index:index + 2]
    sys.exit(main([*workspace, "ingest", "--recordings-only", *args]))
