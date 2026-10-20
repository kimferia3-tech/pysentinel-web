"use strict";

document.addEventListener("DOMContentLoaded", () => {
    const $ = (selector) => document.querySelector(selector);

    const el = {
        filesScanned: $("#files-scanned"),
        threatCount: $("#threat-count"),
        activityLog: $("#activity-log"),
        scanLog: $("#scan-log"),
        scanStatus: $("#scan-status"),
        scanPercent: $("#scan-percent"),
        scanProgress: $("#scan-progress"),
        scanDetail: $("#scan-detail"),
        cancelScan: $("#cancel-scan"),
        themeButtons: [
            $("#theme-toggle"),
            $("#settings-theme-toggle")
        ].filter(Boolean),
        settingsMessage: $("#settings-message")
    };

    let scanRunning = false;
    let pollingTimer = null;
    let lastHandledSummary = null;

    // ---------- Navigation ----------

    function navigateToScanner() {
        const navItems = [...document.querySelectorAll(".nav-item")];

        const scannerNav = navItems.find((item) => {
            const label = item.textContent.trim().toLowerCase();
            const view = (item.dataset.view || "").toLowerCase();

            return label.includes("scanner") ||
                label.includes("scan") ||
                view === "scanner" ||
                view === "scan";
        });

        if (!scannerNav) {
            console.error("PySentinel: Scanner navigation item not found.");
            logActivity("Navigation error: Scanner tab was not found.");
            return;
        }

        const viewId = scannerNav.dataset.view;

        const scannerView =
            document.getElementById(viewId) ||
            document.getElementById("scanner") ||
            document.getElementById("scan");

        if (!scannerView) {
            console.error("PySentinel: Scanner content section not found.");
            logActivity("Navigation error: Scanner content section was not found.");
            return;
        }

        navItems.forEach((item) => {
            item.classList.toggle("active", item === scannerNav);
        });

        document.querySelectorAll(".view").forEach((view) => {
            view.classList.toggle("active", view === scannerView);
        });

        console.log("PySentinel: Navigated to Scanner tab.");
    }

    // ---------- Theme ----------

    function applyTheme(theme) {
        const selected = theme === "light" ? "light" : "dark";
        const root = document.documentElement;
        const body = document.body;

        root.dataset.theme = selected;
        body.dataset.theme = selected;

        root.classList.toggle("light-theme", selected === "light");
        body.classList.toggle("light-theme", selected === "light");
        root.classList.toggle("dark-theme", selected === "dark");
        body.classList.toggle("dark-theme", selected === "dark");

        el.themeButtons.forEach((button) => {
            button.setAttribute(
                "aria-pressed",
                String(selected === "light")
            );
            button.title = `Switch to ${selected === "dark" ? "light" : "dark"} theme`;
        });

        try {
            localStorage.setItem("pysentinel-theme", selected);
        } catch (error) {
            console.warn("Theme preference could not be saved.", error);
        }

        if (el.settingsMessage) {
            el.settingsMessage.textContent =
                `Theme set to ${selected}.`;
        }
    }

    function initializeTheme() {
        let savedTheme = "dark";

        try {
            savedTheme = localStorage.getItem("pysentinel-theme") || "dark";
        } catch (error) {
            console.warn("Saved theme could not be read.", error);
        }

        applyTheme(savedTheme);

        el.themeButtons.forEach((button) => {
            button.addEventListener("click", () => {
                const current =
                    document.documentElement.dataset.theme || "dark";

                applyTheme(current === "dark" ? "light" : "dark");
            });
        });
    }

    // ---------- Activity log ----------

    function logActivity(message) {
        if (!el.activityLog) return;

        const entry = document.createElement("div");
        entry.className = "activity-entry";
        entry.textContent =
            `[${new Date().toLocaleTimeString()}] ${message}`;

        el.activityLog.prepend(entry);

        while (el.activityLog.children.length > 100) {
            el.activityLog.lastElementChild.remove();
        }
    }

    function setText(element, value) {
        if (element) element.textContent = String(value);
    }

    function setProgress(scanned, total) {
        const percentage = total > 0
            ? Math.min(100, Math.round((scanned / total) * 100))
            : 0;

        setText(el.filesScanned, scanned);
        setText(el.scanPercent, `${percentage}%`);

        if (el.scanProgress) {
            el.scanProgress.style.width = `${percentage}%`;
            el.scanProgress.setAttribute(
                "aria-valuenow",
                String(percentage)
            );
        }
    }

    function setScanState(running, status) {
        scanRunning = running;
        setText(el.scanStatus, status);

        if (el.cancelScan) {
            el.cancelScan.disabled = !running;
        }

        document.querySelectorAll(".scan-action").forEach((button) => {
            button.disabled = running;
        });
    }

    // ---------- Results ----------

    function showFinding(result) {
        const detections = (result.detections || [])
            .map((detection) =>
                `${detection.name} [${detection.method}]`
            )
            .join(", ");

        logActivity(`Detection reported: ${result.path}`);

        if (!el.scanLog) return;

        const row = document.createElement("div");
        row.className = "scan-result threat-result";

        const path = document.createElement("div");
        path.textContent = result.path;

        const details = document.createElement("div");
        details.textContent = detections || "Detection details unavailable";

        row.append(path, details);
        el.scanLog.prepend(row);
    }

    function finishScan(summary, cancelled = false) {
        if (!summary) {
            setScanState(false, cancelled ? "Cancelled" : "Scan stopped");
            return;
        }

        const summaryKey = JSON.stringify([
            summary.target,
            summary.scanned,
            summary.threats,
            summary.cancelled
        ]);

        if (lastHandledSummary === summaryKey) return;
        lastHandledSummary = summaryKey;

        setProgress(summary.scanned, summary.total);
        setText(el.threatCount, summary.threats);

        let resultMessage;

        if (cancelled || summary.cancelled) {
            resultMessage =
                `Scan cancelled. ${summary.scanned} file(s) checked; ` +
                `${summary.threats} detection(s) reported.`;
        } else if (summary.threats > 0) {
            resultMessage =
                `Scan complete. ${summary.threats} detection(s) reported.`;
        } else if (summary.errors > 0 || summary.skipped > 0) {
            resultMessage =
                `Scan finished with limitations. ${summary.scanned} file(s) ` +
                `checked; no matches reported by configured checks; ` +
                `${summary.errors} error(s), ${summary.skipped} skipped.`;
        } else {
            resultMessage =
                `Scan complete. ${summary.scanned} file(s) checked; ` +
                `no matches reported by configured checks. This does not ` +
                `guarantee the files are malware-free.`;
        }

        setText(el.scanDetail, resultMessage);
        setScanState(false, cancelled || summary.cancelled
            ? "Scan cancelled"
            : "Scan complete");

        logActivity(resultMessage);

        if (summary.yara_error) {
            logActivity(`YARA notice: ${summary.yara_error}`);
        }

        stopPolling();
    }

    function stopPolling() {
        if (pollingTimer !== null) {
            clearInterval(pollingTimer);
            pollingTimer = null;
        }
    }

    // ---------- Backend communication ----------

    async function pollEvents() {
        const api = window.pywebview?.api;
        if (!api) return;

        try {
            const response = await api.get_events();

            if (response.ok) {
                for (const event of response.events) {
                    handleEvent(event);
                }
            }

            const status = await api.get_status();

            if (!status.running && scanRunning) {
                if (status.summary) {
                    finishScan(
                        status.summary,
                        Boolean(status.summary.cancelled)
                    );
                } else {
                    setScanState(false, "Scan stopped unexpectedly");
                    stopPolling();
                }
            }
        } catch (error) {
            console.error("Polling error:", error);
        }
    }

    function handleEvent(event) {
        switch (event.type) {
            case "start":
                setScanState(true, "Scanning");
                setText(el.scanDetail, `Target: ${event.target}`);
                setProgress(0, event.total);
                logActivity(`Scan started: ${event.target}`);
                break;

            case "progress":
                setProgress(event.scanned, event.total);
                setText(el.threatCount, event.threats);

                setText(
                    el.scanDetail,
                    `Checked ${event.scanned} of ${event.total} file(s).`
                );
                break;

            case "finding":
                showFinding(event.result);
                break;

            case "error":
                logActivity(
                    `Could not scan ${event.path || "file"}: ` +
                    `${event.message || "Unknown error"}`
                );
                break;

            case "scan_error":
                logActivity(`Scanner error: ${event.message}`);
                setScanState(false, "Scan failed");
                stopPolling();
                break;

            case "cancelled":
                finishScan(event.summary, true);
                break;

            case "complete":
                finishScan(event.summary, false);
                break;
        }
    }

    async function startScan(target, label) {
        const api = window.pywebview?.api;

        if (!api) {
            logActivity("Backend is not ready. Restart PySentinel.");
            return;
        }

        if (scanRunning) {
            logActivity("A scan is already running.");
            return;
        }

        navigateToScanner();
        lastHandledSummary = null;

        setScanState(true, "Starting scan...");
        setText(el.scanDetail, `Preparing ${label}...`);
        setProgress(0, 0);

        if (el.scanLog) el.scanLog.replaceChildren();

        try {
            const response = await api.start_scan(target);

            if (!response.ok) {
                setScanState(false, "Could not start scan");
                setText(el.scanDetail, response.error || "Unknown error");
                logActivity(response.error || "Could not start scan.");
                return;
            }

            logActivity(`${label} requested.`);

            stopPolling();
            pollingTimer = setInterval(pollEvents, 250);
            await pollEvents();
        } catch (error) {
            setScanState(false, "Scan failed to start");
            logActivity(`Unable to start scan: ${error.message || error}`);
            stopPolling();
        }
    }

    async function quickScan() {
        navigateToScanner();

        const api = window.pywebview?.api;
        if (!api) {
            logActivity("Backend is not ready.");
            return;
        }

        try {
            const response = await api.get_default_scan_target();

            if (!response.ok || !response.path) {
                logActivity(
                    response.error || "Could not determine the scan location."
                );
                return;
            }

            await startScan(response.path, "Quick Scan (default folder)");
        } catch (error) {
            logActivity(`Quick Scan failed: ${error.message || error}`);
        }
    }

    async function customScan() {
        navigateToScanner();

        const api = window.pywebview?.api;
        if (!api) {
            logActivity("Backend is not ready.");
            return;
        }

        try {
            // Gumagamit na ngayon ng select_files para makapili ng multiple files nang sabay-sabay
            const response = await api.select_files();

            if (response.ok && response.paths) {
                await startScan(response.paths, "Multiple Files Custom Scan");
            } else if (!response.cancelled) {
                logActivity(
                    response.error || "File selection was cancelled."
                );
            } else {
                logActivity("File selection cancelled. No scan started.");
                setText(el.scanStatus, "Ready");
            }
        } catch (error) {
            logActivity(`File selection failed: ${error.message || error}`);
        }
    }

    document.querySelectorAll(".scan-action").forEach((button) => {
        button.addEventListener("click", async () => {
            if (scanRunning) return;

            const type = button.dataset.scan;

            if (type === "custom") {
                await customScan();
            } else {
                await quickScan();
            }
        });
    });

    if (el.cancelScan) {
        el.cancelScan.disabled = true;

        el.cancelScan.addEventListener("click", async () => {
            const api = window.pywebview?.api;

            if (!api || !scanRunning) return;

            el.cancelScan.disabled = true;
            setText(el.scanStatus, "Cancelling...");
            setText(el.scanDetail, "Waiting for the current scan operation to stop...");
            logActivity("Cancellation requested.");

            try {
                const response = await api.cancel_scan();

                if (!response.ok) {
                    logActivity(response.error || "Could not cancel scan.");
                    el.cancelScan.disabled = false;
                }
            } catch (error) {
                logActivity(`Cancellation failed: ${error.message || error}`);
                el.cancelScan.disabled = false;
            }
        });
    }

    document.querySelectorAll(".nav-item").forEach((item) => {
        item.addEventListener("click", () => {
            document.querySelectorAll(".nav-item").forEach((nav) => {
                nav.classList.toggle("active", nav === item);
            });

            const viewId = item.dataset.view;

            document.querySelectorAll(".view").forEach((view) => {
                view.classList.toggle("active", view.id === viewId);
            });
        });
    });

    initializeTheme();

    window.addEventListener("pywebviewready", () => {
        logActivity("PySentinel backend connected.");
    });

    logActivity("PySentinel initialized.");
});