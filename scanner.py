from __future__ import annotations

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Any


EventCallback = Callable[[dict[str, Any]], None]


class Scanner:
    """
    Read-only file scanner.

    Detection methods:
      1. SHA-256 hashes from a local hash database.
      2. Optional YARA rules stored in the rules directory.

    This is a foundational scanner, not a complete antivirus engine.
    """

    def __init__(
        self,
        rules_dir: str | Path | None = None,
        hash_db: dict[str, str] | None = None,
        workers: int = 4,
        max_file_size: int | None = None,
    ):
        self.rules_dir = (
            Path(rules_dir)
            if rules_dir is not None
            else Path(__file__).resolve().parent / "rules"
        )

        # SHA-256 digest -> detection name
        self.hash_db = {
            digest.lower(): name
            for digest, name in (hash_db or {}).items()
        }

        self.workers = max(1, min(workers, 8))
        self.max_file_size = max_file_size
        self._yara_rules = None
        self._yara_error = None

        self._load_yara_rules()

    def _emit(
        self,
        callback: EventCallback | None,
        event_type: str,
        **details: Any,
    ) -> None:
        if callback is None:
            return

        try:
            callback({"type": event_type, **details})
        except Exception:
            # A UI callback failure must not crash the scanning worker.
            pass

    def _load_yara_rules(self) -> None:
        """Load local .yar/.yara files if yara-python is available."""
        if not self.rules_dir.is_dir():
            return

        rule_files = [
            str(path)
            for path in self.rules_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in {".yar", ".yara"}
        ]

        if not rule_files:
            return

        try:
            import yara

            self._yara_rules = yara.compile(filepaths={
                f"rule_{index}": filename
                for index, filename in enumerate(rule_files)
            })
        except ImportError:
            self._yara_error = "yara-python is not installed."
        except Exception as exc:
            self._yara_error = f"Could not load YARA rules: {exc}"

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()

    def _scan_file(self, path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "path": str(path),
            "status": "clean",
            "sha256": None,
            "detections": [],
        }

        try:
            # Avoid following symlinks and scanning non-regular files.
            if path.is_symlink() or not path.is_file():
                result["status"] = "skipped"
                result["reason"] = "Not a regular file or is a symbolic link."
                return result

            if self.max_file_size is not None:
                if path.stat().st_size > self.max_file_size:
                    result["status"] = "skipped"
                    result["reason"] = "File exceeds configured size limit."
                    return result

            digest = self._sha256_file(path)
            result["sha256"] = digest

            known_detection = self.hash_db.get(digest)
            if known_detection:
                result["detections"].append({
                    "name": known_detection,
                    "method": "sha256",
                })

            if self._yara_rules is not None:
                matches = self._yara_rules.match(str(path))
                for match in matches:
                    result["detections"].append({
                        "name": str(match.rule),
                        "method": "yara",
                    })

            if result["detections"]:
                result["status"] = "threat"

        except PermissionError:
            result["status"] = "error"
            result["reason"] = "Permission denied."
        except (OSError, ValueError) as exc:
            result["status"] = "error"
            result["reason"] = str(exc)

        return result

    def scan(
        self,
        target: str | Path,
        on_event: EventCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        """
        Scan a file or recursively scan a directory.

        on_event receives dictionaries with event types:
        start, finding, progress, error, complete, cancelled.
        """
        target_path = Path(target).expanduser()

        if not target_path.exists():
            raise FileNotFoundError(f"Path does not exist: {target_path}")

        if target_path.is_symlink():
            raise ValueError("Refusing to scan a symbolic link as the target.")

        if not target_path.is_file() and not target_path.is_dir():
            raise ValueError("Target must be a regular file or directory.")

        if cancel_event is None:
            cancel_event = threading.Event()

        if target_path.is_file():
            files = [target_path]
        else:
            files = []
            for root, directories, filenames in os.walk(
                target_path,
                followlinks=False,
                onerror=lambda error: self._emit(
                    on_event, "error",
                    path=getattr(error, "filename", str(target_path)),
                    message=str(error),
                ),
            ):
                if cancel_event.is_set():
                    break

                # Don't descend into directory symlinks.
                directories[:] = [
                    name for name in directories
                    if not (Path(root) / name).is_symlink()
                ]

                for filename in filenames:
                    candidate = Path(root) / filename
                    if not candidate.is_symlink():
                        files.append(candidate)

        total = len(files)
        scanned = 0
        threats = 0
        errors = 0
        skipped = 0
        findings: list[dict[str, Any]] = []

        self._emit(
            on_event,
            "start",
            target=str(target_path),
            total=total,
        )

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            for result in executor.map(self._scan_file, files):
                if cancel_event.is_set():
                    break

                scanned += 1

                if result["status"] == "threat":
                    threats += 1
                    findings.append(result)
                    self._emit(on_event, "finding", result=result)
                elif result["status"] == "error":
                    errors += 1
                    self._emit(
                        on_event,
                        "error",
                        path=result["path"],
                        message=result.get("reason", "Unknown error"),
                    )
                elif result["status"] == "skipped":
                    skipped += 1

                self._emit(
                    on_event,
                    "progress",
                    scanned=scanned,
                    total=total,
                    threats=threats,
                    errors=errors,
                    skipped=skipped,
                    current_file=result["path"],
                )

        cancelled = cancel_event.is_set()

        summary = {
            "target": str(target_path),
            "total": total,
            "scanned": scanned,
            "threats": threats,
            "errors": errors,
            "skipped": skipped,
            "cancelled": cancelled,
            "findings": findings,
            "yara_error": self._yara_error,
        }

        self._emit(
            on_event,
            "cancelled" if cancelled else "complete",
            summary=summary,
        )

        return summary