<<<<<<< HEAD
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

    def select_files(self):
        """Open native multi-file dialog for selecting multiple files."""
        try:
            if self.window is None:
                return {"ok": False, "error": "Window is not ready."}

            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG,
                directory=str(Path.home()),
                allow_multiple=True,
            )

            if not result:
                return {"ok": False, "cancelled": True}

            return {"ok": True, "paths": list(result)}

        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def start_scan(self, target):
        paths_to_scan: str | list[str]

        if isinstance(target, list):
            valid_paths = []
            for item in target:
                p = Path(item).expanduser()
                if p.exists() and not p.is_symlink() and p.is_file():
                    valid_paths.append(str(p))

            if not valid_paths:
                return {"ok": False, "error": "No valid files selected."}

            paths_to_scan = valid_paths

        elif isinstance(target, str) and target.strip():
            path = Path(target).expanduser()

            if not path.exists():
                return {"ok": False, "error": "The selected path does not exist."}

            if path.is_symlink():
                return {"ok": False, "error": "Symbolic links cannot be scan targets."}

            if not (path.is_file() or path.is_dir()):
                return {"ok": False, "error": "Select a regular file or folder."}

            paths_to_scan = str(path)

        else:
            return {"ok": False, "error": "Select valid file(s) or folder."}

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
                args=(paths_to_scan, self.cancel_event),
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

    # ---------- Quarantine Backend Features ----------

    def get_quarantine_list(self):
        """Kunin ang listahan ng mga naka-quarantine na files."""
        quarantine_dir = Path(__file__).resolve().parent / "quarantine"
        records = []
        
        if quarantine_dir.is_dir():
            for file_path in quarantine_dir.iterdir():
                if file_path.is_file():
                    records.append({
                        "id": file_path.name,
                        "path": str(file_path),
                        "name": file_path.name,
                        "size": file_path.stat().st_size,
                        "date": "Isolated"
                    })
                    
        return {"ok": True, "records": records}

    def quarantine_file(self, file_path_str):
        """Ilipat ang file sa isolated quarantine folder."""
        try:
            target_path = Path(file_path_str).expanduser()
            if not target_path.exists():
                return {"ok": False, "error": "File does not exist."}

            quarantine_dir = Path(__file__).resolve().parent / "quarantine"
            quarantine_dir.mkdir(exist_ok=True)

            dest_path = quarantine_dir / f"{target_path.name}.quarantined"
            target_path.rename(dest_path)

            return {"ok": True, "message": "File successfully quarantined."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def restore_file(self, file_name):
        """Ibalik ang file mula sa quarantine papuntang Desktop."""
        try:
            quarantine_dir = Path(__file__).resolve().parent / "quarantine"
            target_path = quarantine_dir / file_name
            
            if not target_path.exists():
                return {"ok": False, "error": "Quarantined record not found."}

            original_name = target_path.name.replace(".quarantined", "")
            restore_dir = Path.home() / "Desktop" / "PySentinel_Restored"
            restore_dir.mkdir(exist_ok=True)
            
            dest_path = restore_dir / original_name
            target_path.rename(dest_path)

            return {"ok": True, "message": "File restored to Desktop/PySentinel_Restored."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def delete_quarantined_file(self, file_name):
        """Permanenteng burahin ang naka-quarantine na file."""
        try:
            quarantine_dir = Path(__file__).resolve().parent / "quarantine"
            target_path = quarantine_dir / file_name
            
            if target_path.exists():
                target_path.unlink()
                
            return {"ok": True, "message": "File permanently deleted."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
=======
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
>>>>>>> 113abfb7e89e747a5927a33b4cb931806d6c83aa
