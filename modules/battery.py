"""
modules/battery.py — Battery stats capture and parsing
"""

import subprocess, re, os, json, time


def capture_battery_stats(output_dir):
    """Capture full battery stats and bugreport."""
    stats_path = os.path.join(output_dir, "battery_stats.txt")

    print("  [Battery] Capturing battery stats...")
    out = subprocess.run(
        "adb shell dumpsys batterystats",
        shell=True, capture_output=True, text=True, timeout=30
    ).stdout
    with open(stats_path, "w") as f:
        f.write(out)
    print(f"  [Battery] Stats saved -> {stats_path}")
    return stats_path


def capture_bugreport(output_dir):
    """Capture full bugreport zip (takes 2-3 minutes)."""
    zip_path = os.path.join(output_dir, "bugreport.zip")
    print("  [Battery] Capturing bugreport (this takes 2-3 minutes)...")
    result = subprocess.run(
        f"adb bugreport {zip_path}",
        shell=True, capture_output=True, text=True, timeout=300
    )
    if os.path.exists(zip_path):
        print(f"  [Battery] Bugreport saved -> {zip_path}")
        return zip_path
    else:
        print(f"  [Battery] Bugreport failed: {result.stderr[:200]}")
        return None


def parse_battery_stats(stats_path):
    """Parse battery_stats.txt for camera, GPS, charging status, temperature."""
    try:
        with open(stats_path, "r", errors="replace") as f:
            content = f.read()
    except Exception:
        return {}

    result = {}

    # Session duration
    m = re.search(r"Total run time:\s*([\d\w\s]+)", content)
    result["session_duration"] = m.group(1).strip() if m else "unknown"

    # Charging status
    m = re.search(r"status=(\w+)", content)
    result["was_charging"] = (m.group(1) == "charging") if m else False

    # Battery capacity
    m = re.search(r"Estimated battery capacity:\s*([\d,]+)\s*mAh", content)
    result["battery_capacity_mah"] = int(m.group(1).replace(",", "")) if m else 0

    # Charge at start
    m = re.search(r"charge=(\d+)", content)
    result["charge_start_mah"] = int(m.group(1)) if m else 0

    # Temperature
    temps = re.findall(r"temp=(\d+)", content)
    if temps:
        result["temp_readings_c"] = [round(int(t) / 10, 1) for t in temps]
        result["temp_max_c"]  = max(result["temp_readings_c"])
        result["temp_min_c"]  = min(result["temp_readings_c"])
    else:
        result["temp_readings_c"] = []
        result["temp_max_c"] = 0
        result["temp_min_c"] = 0

    # Camera sessions
    camera_on_times  = re.findall(r"\+(\d+m\d+s\d+ms|\d+m\d+s|\d+s\d+ms|\d+ms|\d+s|\d+m).*?\+camera", content)
    camera_off_times = re.findall(r"\+(\d+m\d+s\d+ms|\d+m\d+s|\d+s\d+ms|\d+ms|\d+s|\d+m).*?-camera", content)
    result["camera_sessions"]     = len(camera_on_times)
    result["camera_off_sessions"] = len(camera_off_times)

    # GPS sessions
    gps_on_times  = [m for m in re.findall(r"\+\S+.*?\+gps", content)]
    gps_off_times = [m for m in re.findall(r"\+\S+.*?-gps", content)]
    result["gps_activations"] = len(gps_on_times)

    # Calculate total camera time
    result["camera_total_sec"] = _calculate_hardware_time(content, "camera")
    result["gps_total_sec"]    = _calculate_hardware_time(content, "gps")

    # WorkManager jobs
    wm_jobs = re.findall(r"\+job=.*?SystemJobService", content)
    result["workmanager_jobs"] = len(wm_jobs)

    # Firebase jobs
    fb_jobs = re.findall(r"\+job=.*?datatransport", content)
    result["firebase_jobs"] = len(fb_jobs)

    # WiFi radio wakeups by app
    wifi_wakeups = re.findall(r"wakeupap=.*?:", content)
    result["wifi_wakeups"] = len(wifi_wakeups)

    return result


def _time_to_sec(ts):
    total = 0
    d = re.search(r"(\d+)d", ts); total += int(d.group(1)) * 86400 if d else 0
    h = re.search(r"(\d+)h", ts); total += int(h.group(1)) * 3600  if h else 0
    m = re.search(r"(\d+)m", ts); total += int(m.group(1)) * 60    if m else 0
    s = re.search(r"(\d+)s", ts); total += int(s.group(1))          if s else 0
    return total


def _calculate_hardware_time(content, hw):
    """Calculate total seconds a hardware resource was active."""
    total = 0
    on_time = None
    lines = content.split("\n")
    for line in lines:
        t_match = re.match(r"\s+\+(\S+)", line)
        if t_match:
            current = _time_to_sec(t_match.group(1))
            if f"+{hw}" in line:
                on_time = current
            elif f"-{hw}" in line and on_time is not None:
                total += current - on_time
                on_time = None
    return total
