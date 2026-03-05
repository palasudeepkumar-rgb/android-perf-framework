"""
modules/start_time.py — Cold and warm start time measurement
"""

import subprocess, re, time
from config import DEFAULT_COLD_WARM_RUNS

def _run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout + r.stderr

def _parse_total_time(output):
    m = re.search(r"TotalTime:\s*(\d+)", output)
    return int(m.group(1)) if m else None

def measure_cold_start(package, activity, runs=DEFAULT_COLD_WARM_RUNS):
    """
    Force-stop the app, then launch it and measure start time.
    Repeats `runs` times and returns list of TotalTime values.
    """
    results = []
    print(f"\n  Measuring Cold Start ({runs} runs)...")
    for i in range(runs):
        # Force stop
        subprocess.run(f"adb shell am force-stop {package}",
                       shell=True, capture_output=True)
        time.sleep(1.5)   # Let OS settle after kill

        out = _run(f"adb shell am start -W -n {package}/{activity}")
        t   = _parse_total_time(out)
        if t:
            results.append(t)
            print(f"    Run {i+1}: {t} ms")
        else:
            print(f"    Run {i+1}: FAILED to parse output")
        time.sleep(1)

    return results

def measure_warm_start(package, activity, runs=DEFAULT_COLD_WARM_RUNS):
    """
    Launch app without force-stopping (app already in memory).
    Repeats `runs` times and returns list of TotalTime values.
    """
    results = []
    print(f"\n  Measuring Warm Start ({runs} runs)...")

    # Ensure app is already running first
    subprocess.run(f"adb shell am start -n {package}/{activity}",
                   shell=True, capture_output=True)
    time.sleep(3)

    for i in range(runs):
        out = _run(f"adb shell am start -W -n {package}/{activity}")
        t   = _parse_total_time(out)
        if t:
            results.append(t)
            print(f"    Run {i+1}: {t} ms")
        else:
            print(f"    Run {i+1}: FAILED to parse output")
        time.sleep(0.8)

    return results

def summarise(values):
    if not values:
        return {"min": 0, "max": 0, "avg": 0, "values": []}
    return {
        "min":    min(values),
        "max":    max(values),
        "avg":    round(sum(values) / len(values)),
        "values": values,
    }

def rate_start_time(ms, start_type="cold"):
    """Rate a start time against Google benchmarks."""
    if start_type == "cold":
        if ms <= 1000: return "EXCELLENT"
        if ms <= 2000: return "GOOD"
        if ms <= 5000: return "ACCEPTABLE"
        return "POOR"
    else:
        if ms <= 200:  return "EXCELLENT"
        if ms <= 800:  return "GOOD"
        if ms <= 2000: return "ACCEPTABLE"
        return "POOR"
