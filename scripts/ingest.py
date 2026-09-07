"""Compatibility entry point. Prefer `python schoolbot.py ingest`."""
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
    if "--transcribe" in args:
        args[args.index("--transcribe")] = "--file"
        args.append("--recordings-only")
    sys.exit(main([*workspace, "ingest", *args]))
