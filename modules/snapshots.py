"""
modules/snapshots.py — Snapshot engine
Supports:
  - Auto snapshots every N minutes
  - User-triggered snapshots via trigger file
    (user runs: echo "label" > /tmp/perf_snapshot_trigger  in another terminal)
"""

import subprocess, threading, time, os, json
from config import TRIGGER_FILE

class SnapshotEngine:
    def __init__(self, package, output_dir):
        self.package    = package
        self.output_dir = output_dir
        self.snapshots  = []          # list of {label, ts, meminfo, cpu}
        self._running   = False
        self._lock      = threading.Lock()

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────
    def start(self, auto_interval_min=None):
        """
        Start the snapshot watchers.
        auto_interval_min: None = disabled, else int (3/5/10/15)
        """
        self._running = True

        # Always watch for trigger file
        t_trigger = threading.Thread(target=self._trigger_watcher, daemon=True)
        t_trigger.start()

        # Optional auto-snapshot
        if auto_interval_min:
            t_auto = threading.Thread(
                target=self._auto_snapshots,
                args=(auto_interval_min * 60,),
                daemon=True
            )
            t_auto.start()

        print(f"  [SnapshotEngine] Watching for trigger file: {TRIGGER_FILE}")
        print(f"  [SnapshotEngine] To take a manual snapshot, in ANOTHER terminal run:")
        print(f'  [SnapshotEngine]   echo "your-label" > {TRIGGER_FILE}')
        if auto_interval_min:
            print(f"  [SnapshotEngine] Auto-snapshot every {auto_interval_min} minutes")

    def stop(self):
        self._running = False
        # Clean up trigger file
        if os.path.exists(TRIGGER_FILE):
            os.remove(TRIGGER_FILE)

    def take_snapshot(self, label):
        """Capture meminfo + cpu for the given label. Thread-safe."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n  [Snapshot] Capturing '{label}' at {ts} ...")

        # meminfo
        mem_raw = subprocess.run(
            f"adb shell dumpsys meminfo {self.package}",
            shell=True, capture_output=True, text=True, timeout=15
        ).stdout

        # cpu
        cpu_raw = subprocess.run(
            "adb shell top -n 1 -b",
            shell=True, capture_output=True, text=True, timeout=8
        ).stdout
        short = self.package.split(".")[-1]
        cpu_line = ""
        for line in cpu_raw.splitlines():
            if short in line or self.package[-20:] in line:
                cpu_line = line.strip()
                break

        snap = {
            "label":    label,
            "ts":       ts,
            "mem_raw":  mem_raw,
            "cpu_line": cpu_line,
            "parsed":   _parse_meminfo(mem_raw),
            "cpu_pct":  _parse_cpu_pct(cpu_line),
        }

        with self._lock:
            self.snapshots.append(snap)

        # Save individual file
        safe = label.replace(" ", "_").replace("/", "-")
        path = os.path.join(self.output_dir, f"snapshot_{safe}.txt")
        with open(path, "w") as f:
            f.write(f"=== Snapshot: {label} at {ts} ===\n\n")
            f.write("--- CPU ---\n")
            f.write(cpu_line + "\n\n")
            f.write("--- MEMINFO ---\n")
            f.write(mem_raw)

        print(f"  [Snapshot] '{label}' saved -> {path}")
        print(f"  [Snapshot] PSS Total: {snap['parsed'].get('total_pss_mb', '?')} MB  "
              f"| CPU: {snap['cpu_pct']}%  "
              f"| GL mtrack: {snap['parsed'].get('gl_mtrack_mb', '?')} MB")

    def save_summary(self):
        """Save all snapshots as JSON for the report generator."""
        path = os.path.join(self.output_dir, "snapshots_summary.json")
        exportable = []
        for s in self.snapshots:
            exportable.append({
                "label":    s["label"],
                "ts":       s["ts"],
                "parsed":   s["parsed"],
                "cpu_pct":  s["cpu_pct"],
            })
        with open(path, "w") as f:
            json.dump(exportable, f, indent=2)
        return path

    # ─────────────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────────────
    def _trigger_watcher(self):
        """Poll for trigger file every second."""
        while self._running:
            if os.path.exists(TRIGGER_FILE):
                try:
                    with open(TRIGGER_FILE, "r") as f:
                        label = f.read().strip() or "manual"
                    os.remove(TRIGGER_FILE)
                    self.take_snapshot(label)
                except Exception as e:
                    print(f"  [SnapshotEngine] Trigger error: {e}")
            time.sleep(1)

    def _auto_snapshots(self, interval_sec):
        """Periodically take auto-labelled snapshots."""
        count = 0
        while self._running:
            time.sleep(interval_sec)
            if self._running:
                count += 1
                self.take_snapshot(f"auto_{count}_at_{time.strftime('%H%M%S')}")


# ─────────────────────────────────────────────────────────────────────────────
# Parser helpers
# ─────────────────────────────────────────────────────────────────────────────
def _parse_meminfo(raw):
    result = {}
    for line in raw.splitlines():
        stripped = line.strip()

        def _kb(s):
            m = __import__("re").search(r"(\d+)", s.split(":")[0] if ":" in s else s.split()[1] if len(s.split()) > 1 else "0")
            return int(m.group(1)) if m else 0

        if stripped.startswith("Native Heap"):
            # Format: "Native Heap  PSS  PrivDirty  PrivClean  SwapDirty  HeapSize  HeapAlloc  HeapFree"
            # After split(): ['Native','Heap', pss, privDirty, privClean, swapDirty, size, alloc, free]
            parts = stripped.split()
            try:
                result["native_heap_pss_kb"]  = int(parts[2])
                result["native_heap_size_kb"]  = int(parts[6]) if len(parts) > 6 else 0
                result["native_heap_alloc_kb"] = int(parts[7]) if len(parts) > 7 else 0
                result["native_heap_free_kb"]  = int(parts[8]) if len(parts) > 8 else 0
            except Exception:
                pass

        elif stripped.startswith("Dalvik Heap"):
            # Same format: ['Dalvik','Heap', pss, privDirty, privClean, swapDirty, size, alloc, free]
            parts = stripped.split()
            try:
                result["dalvik_heap_pss_kb"]  = int(parts[2])
                result["dalvik_heap_size_kb"]  = int(parts[6]) if len(parts) > 6 else 0
                result["dalvik_heap_alloc_kb"] = int(parts[7]) if len(parts) > 7 else 0
                result["dalvik_heap_free_kb"]  = int(parts[8]) if len(parts) > 8 else 0
            except Exception:
                pass

        elif "GL mtrack" in stripped:
            # Format: "GL mtrack  PSS ..."
            parts = stripped.split()
            try:
                result["gl_mtrack_kb"] = int(parts[2])
                result["gl_mtrack_mb"] = round(int(parts[2]) / 1024, 1)
            except Exception:
                pass

        elif stripped.startswith("TOTAL") and "SWAP" not in stripped:
            # Format: "TOTAL  total_pss  privDirty  privClean  swapDirty  heapSize  heapAlloc  heapFree"
            parts = stripped.split()
            try:
                result["total_pss_kb"] = int(parts[1])
                result["total_pss_mb"] = round(int(parts[1]) / 1024, 1)
            except Exception:
                pass
            import re as _re
            m = _re.search(r"TOTAL SWAP PSS:\s*(\d+)", raw)
            result["swap_pss_kb"] = int(m.group(1)) if m else 0
            result["swap_pss_mb"] = round(result["swap_pss_kb"] / 1024, 1)

        elif "Native Heap:" in stripped:
            # App Summary section: "Native Heap:    31140"
            parts = stripped.split()
            try:
                result["native_heap_pss_kb"] = result.get("native_heap_pss_kb") or int(parts[-1])
            except Exception:
                pass

        elif stripped.startswith("Java Heap:"):
            parts = stripped.split()
            try:
                result["java_heap_kb"] = int(parts[-1])
            except Exception:
                pass

        elif stripped.startswith("Graphics:"):
            parts = stripped.split()
            try:
                result["graphics_kb"] = int(parts[-1])
                result["graphics_mb"] = round(int(parts[-1]) / 1024, 1)
            except Exception:
                pass

        elif stripped.startswith("Views:"):
            import re as _re
            mv = _re.search(r"Views:\s*(\d+)", stripped)
            result["views"] = int(mv.group(1)) if mv else 0

        elif "MEMORY_USED:" in stripped:
            import re as _re
            mm = _re.search(r"MEMORY_USED:\s*(\d+)", stripped)
            result["sql_memory_kb"] = int(mm.group(1)) if mm else 0

    # Native heap MB
    result["native_heap_mb"] = round(result.get("native_heap_pss_kb", 0) / 1024, 1)
    result["dalvik_heap_mb"] = round(result.get("dalvik_heap_pss_kb", 0) / 1024, 1)
    return result


def _parse_cpu_pct(cpu_line):
    if not cpu_line:
        return 0.0
    parts = cpu_line.split()
    # top output: PID USER PR NI VIRT RES SHR S CPU% MEM% TIME COMMAND
    try:
        return float(parts[8])
    except Exception:
        return 0.0
