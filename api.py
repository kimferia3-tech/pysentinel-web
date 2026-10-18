from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import webview

from scanner import Scanner


class PySentinelAPI:
    def __init__(self):
        self.scanner = Scanner()
        self.events: Queue[dict[str, Any]] = Queue()
        self.window = None

        self.cancel_event = None
        self.scan_thread = None
        self.lock = threading.Lock()
        self.running = False
        self.last_summary = None

    def set_window(self, window):
        self.window = window

    def _emit(self, event):
        self.events.put(event)

    def get_version(self):
        return {
            "name": "PySentinel",
            "version": "0.1.0",
            "status": "development",
        }

    def get_default_scan_target(self):
        downloads = Path.home() / "Downloads"

        if downloads.is_dir():
            return {"ok": True, "path": str(downloads)}

        return {"ok": True, "path": str(Path.home())}

    def select_folder(self):
        """Open the native folder picker."""
        try:
            if self.window is None:
                return {"ok": False, "error": "Window is not ready."}

            result = self.window.create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=str(Path.home()),
            )

            if not result:
                return {"ok": False, "cancelled": True}

            return {"ok": True, "path": str(result[0])}

        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def start_scan(self, target):
        if not isinstance(target, str) or not target.strip():
            return {"ok": False, "error": "Select a valid file or folder."}

        path = Path(target).expanduser()

        if not path.exists():
            return {"ok": False, "error": "The selected path does not exist."}

        if path.is_symlink():
            return {"ok": False, "error": "Symbolic links cannot be scan targets."}

        if not (path.is_file() or path.is_dir()):
            return {"ok": False, "error": "Select a regular file or folder."}

        with self.lock:
            if self.running:
                return {"ok": False, "error": "A scan is already running."}

            self.running = True
            self.cancel_event = threading.Event()
            self.last_summary = None

            while True:
                try:
                    self.events.get_nowait()
                except Empty:
                    break

            self.scan_thread = threading.Thread(
                target=self._run_scan,
                args=(str(path), self.cancel_event),
                daemon=True,
                name="PySentinelScan",
            )
            self.scan_thread.start()

        return {"ok": True, "message": "Scan started."}

    def _run_scan(self, target, cancel_event):
        try:
            summary = self.scanner.scan(
                target,
                on_event=self._emit,
                cancel_event=cancel_event,
            )
            with self.lock:
                self.last_summary = summary

        except Exception as exc:
            self._emit({
                "type": "scan_error",
                "message": str(exc),
            })

        finally:
            with self.lock:
                self.running = False

    def cancel_scan(self):
        with self.lock:
            if not self.running or self.cancel_event is None:
                return {
                    "ok": False,
                    "error": "No scan is currently running.",
                }

            self.cancel_event.set()

        return {"ok": True, "message": "Cancellation requested."}

    def get_events(self):
        batch = []

        for _ in range(200):
            try:
                batch.append(self.events.get_nowait())
            except Empty:
                break

        return {"ok": True, "events": batch}

    def get_status(self):
        with self.lock:
            return {
                "ok": True,
                "running": self.running,
                "summary": self.last_summary,
            }