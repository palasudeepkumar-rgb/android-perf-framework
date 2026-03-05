"""
modules/capture.py — Background continuous capture engine
Runs CPU+Memory loop, GPS/Camera logcat, Network logcat, App logs
all in parallel background threads.
"""

import subprocess, threading, time, os
from config import PERF_LOOP_INTERVAL_SEC

class CaptureEngine:
    def __init__(self, package, output_dir):
        self.package    = package
        self.output_dir = output_dir
        self._procs     = []       # logcat subprocesses
        self._threads   = []       # perf loop threads
        self._running   = False

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────
    def start(self, interval_sec=PERF_LOOP_INTERVAL_SEC):
        """Start all background captures."""
        self._running = True

        # 1. CPU + Memory loop (threaded Python)
        t = threading.Thread(target=self._perf_loop,
                             args=(interval_sec,), daemon=True)
        t.start()
        self._threads.append(t)

        # 2. GPS + Camera logcat
        self._start_logcat(
            label="gps_camera",
            grep='camera|gps|location|GPS_PROVIDER|fused|LocationManager',
        )

        # 3. Network + API logcat
        self._start_logcat(
            label="network",
            grep='okhttp|retrofit|http|api|WorkManager|PlayCore|Firebase|JobScheduler',
        )

        # 4. Full app logcat
        self._start_logcat(
            label="app_logs",
            grep=None,           # No filter — capture everything
            extra_args="-v threadtime",
        )

        print("  [CaptureEngine] All captures started.")

    def stop(self):
        """Stop all background captures gracefully."""
        self._running = False
        for proc in self._procs:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                pass
        print("  [CaptureEngine] All captures stopped.")

    def output_files(self):
        """Return dict of label -> filepath for all captured files."""
        return {
            "perf_stats":      os.path.join(self.output_dir, "perf_stats.txt"),
            "gps_camera_logs": os.path.join(self.output_dir, "gps_camera_logs.txt"),
            "network_calls":   os.path.join(self.output_dir, "network_calls.txt"),
            "app_logs":        os.path.join(self.output_dir, "app_logs.txt"),
        }

    # ─────────────────────────────────────────────────────────────────────
    # Internal methods
    # ─────────────────────────────────────────────────────────────────────
    def _perf_loop(self, interval_sec):
        filepath = os.path.join(self.output_dir, "perf_stats.txt")
        pkg = self.package
        while self._running:
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            try:
                # CPU
                cpu_out = subprocess.run(
                    f"adb shell top -n 1 -b",
                    shell=True, capture_output=True, text=True, timeout=8
                ).stdout
                cpu_line = ""
                for line in cpu_out.splitlines():
                    # Match package name fragment (last 15 chars of package)
                    short = pkg.split(".")[-1]
                    if short in line or pkg[-20:] in line:
                        cpu_line = line.strip()
                        break

                # Memory
                mem_out = subprocess.run(
                    f'adb shell dumpsys meminfo {pkg}',
                    shell=True, capture_output=True, text=True, timeout=8
                ).stdout
                mem_lines = []
                for line in mem_out.splitlines():
                    if any(k in line for k in ["TOTAL", "Native Heap", "Dalvik Heap",
                                                "GL mtrack", "Java Heap", "Graphics",
                                                "EGL mtrack"]):
                        mem_lines.append(line.strip())

                with open(filepath, "a") as f:
                    f.write(f"\n=== {ts} ===\n")
                    f.write("--- CPU ---\n")
                    f.write(cpu_line + "\n" if cpu_line else "  (app not running)\n")
                    f.write("--- MEMORY ---\n")
                    f.write("\n".join(mem_lines) + "\n")

            except Exception as e:
                with open(filepath, "a") as f:
                    f.write(f"=== {ts} === ERROR: {e}\n")

            time.sleep(interval_sec)

    def _start_logcat(self, label, grep, extra_args=""):
        filepath = os.path.join(self.output_dir, f"{label}.txt")
        if grep:
            cmd = f'adb logcat {extra_args} | grep -iE "{grep}"'
        else:
            cmd = f"adb logcat {extra_args}"

        with open(filepath, "w") as f_out:
            proc = subprocess.Popen(
                cmd, shell=True,
                stdout=f_out, stderr=subprocess.DEVNULL
            )
        self._procs.append(proc)
