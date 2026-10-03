"""Polling folder watcher (no inotify dependency) with debounce and 'file still being written' detection."""
from __future__ import annotations

import fnmatch
import hashlib
import logging
import os
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

log = logging.getLogger(__name__)

_TEMP_PREFIXES = ("~$", ".~lock", ".")
_TEMP_SUFFIXES = (".tmp", ".part", ".crdownload", ".partial", ".swp")


@dataclass
class _State:
    sig: tuple[int, int]            # (size, mtime_ns)
    since: float                    # clock time when this signature was first observed
    processed_hash: str = ""
    processed_sig: tuple[int, int] | None = None


def _is_temp(name: str) -> bool:
    n = name.lower()
    return name.startswith(_TEMP_PREFIXES) or n.endswith(_TEMP_SUFFIXES)


def _complete_zip(path: Path) -> bool:
    """A finished .xlsx/.xlsm is a valid zip with its central directory at the end."""
    try:
        if not zipfile.is_zipfile(path):
            return False
        with zipfile.ZipFile(path) as z:
            return "[Content_Types].xml" in z.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class FolderWatcher:
    """Call ``poll()`` periodically; it returns files that are new/changed AND stable.

    A file is reported once its (size, mtime) has not changed for ``debounce_s`` seconds, it is not
    a temp/lock file, it is a complete zip, and its content hash differs from the last reported one
    (so merely touching a file does not trigger a re-import). The watched files are only stat'ed,
    opened read-only for hashing, and never modified.
    """

    def __init__(self, directory: str | os.PathLike, patterns: Iterable[str] = ("*.xlsx", "*.xlsm"),
                 debounce_s: float = 2.0, clock: Callable[[], float] = time.monotonic):
        self.directory = Path(directory)
        self.patterns = tuple(patterns)
        self.debounce_s = debounce_s
        self._clock = clock
        self._state: dict[Path, _State] = {}

    def _candidates(self) -> list[Path]:
        try:
            names = os.listdir(self.directory)
        except OSError:
            return []
        out = []
        for n in sorted(names):
            if _is_temp(n) or not any(fnmatch.fnmatch(n.lower(), p.lower()) for p in self.patterns):
                continue
            p = self.directory / n
            if p.is_file():
                out.append(p)
        return out

    def poll(self) -> list[Path]:
        now = self._clock()
        ready: list[Path] = []
        present = set()
        for p in self._candidates():
            present.add(p)
            try:
                st = p.stat()
            except OSError:
                continue
            sig = (st.st_size, st.st_mtime_ns)
            state = self._state.get(p)
            if state is None or state.sig != sig:
                prev = state
                self._state[p] = _State(sig=sig, since=now,
                                        processed_hash=prev.processed_hash if prev else "",
                                        processed_sig=prev.processed_sig if prev else None)
                continue
            if state.processed_sig == sig or now - state.since < self.debounce_s:
                continue
            if st.st_size == 0 or not _complete_zip(p):
                continue
            try:
                digest = _sha256(p)
            except OSError:
                continue
            state.processed_sig = sig
            if digest == state.processed_hash:
                continue
            state.processed_hash = digest
            ready.append(p)
        for gone in set(self._state) - present:
            del self._state[gone]
        return ready

    def run(self, callback: Callable[[Path], None], stop: threading.Event, interval_s: float = 5.0) -> None:
        """Blocking loop; exceptions from *callback* are logged (path only) and never stop the watcher."""
        while not stop.is_set():
            for p in self.poll():
                try:
                    callback(p)
                except Exception as exc:  # noqa: BLE001
                    log.error("watch callback failed for %s: %s", p.name, type(exc).__name__)
            stop.wait(interval_s)
