"""
modules/device.py — Device detection, profiling and suitability assessment
"""

import subprocess, re
from config import MIN_RECOMMENDED, RAM_TIERS

def _adb(cmd):
    try:
        r = subprocess.run(f"adb shell {cmd}", shell=True,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""

def _adb_host(cmd):
    try:
        r = subprocess.run(cmd, shell=True,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""

def get_connected_devices():
    """Return list of connected device serials."""
    out = _adb_host("adb devices")
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) == 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices

def get_device_info():
    """Collect full device profile via adb getprop and other commands."""
    props = {
        "model":        _adb("getprop ro.product.model"),
        "brand":        _adb("getprop ro.product.brand"),
        "manufacturer": _adb("getprop ro.product.manufacturer"),
        "android_ver":  _adb("getprop ro.build.version.release"),
        "api_level":    _adb("getprop ro.build.version.sdk"),
        "cpu_abi":      _adb("getprop ro.product.cpu.abi"),
        "hardware":     _adb("getprop ro.hardware"),
        "device_name":  _adb("getprop ro.product.device"),
        "serial":       _adb_host("adb get-serialno"),
    }

    # RAM
    meminfo = _adb("cat /proc/meminfo")
    ram_kb = 0
    for line in meminfo.splitlines():
        if line.startswith("MemTotal"):
            m = re.search(r"(\d+)", line)
            if m:
                ram_kb = int(m.group(1))
    props["ram_total_kb"] = ram_kb
    props["ram_total_gb"] = round(ram_kb / (1024 * 1024), 1)

    # CPU cores and frequency
    cpu_cores = _adb("nproc")
    props["cpu_cores"] = int(cpu_cores) if cpu_cores.isdigit() else 0

    max_freq = _adb("cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
    props["cpu_max_freq_ghz"] = round(int(max_freq) / 1_000_000, 2) if max_freq.isdigit() else 0.0

    # Storage
    df_out = _adb("df /data")
    props["storage_raw"] = df_out

    # Screen
    wm_size = _adb("wm size")
    props["screen_size"] = wm_size.replace("Physical size:", "").strip()
    wm_density = _adb("wm density")
    props["screen_density"] = wm_density.replace("Physical density:", "").strip()

    # Battery capacity
    bat_cap = _adb("cat /sys/class/power_supply/battery/charge_full_design 2>/dev/null || echo 0")
    try:
        props["battery_mah"] = int(bat_cap) // 1000
    except Exception:
        props["battery_mah"] = 0

    return props


def assess_suitability(device_info):
    """
    Score the device suitability for running a business Android app.
    Returns: dict with score (0-100), tier, issues, and per-metric breakdown.
    """
    score   = 100
    issues  = []
    details = {}

    ram_gb  = device_info.get("ram_total_gb", 0)
    api     = int(device_info.get("api_level", 0))
    cores   = device_info.get("cpu_cores", 0)
    freq    = device_info.get("cpu_max_freq_ghz", 0.0)

    # RAM check
    if ram_gb < 2:
        score -= 40
        issues.append(f"RAM {ram_gb} GB is critically low (min recommended: {MIN_RECOMMENDED['ram_gb']} GB)")
        details["ram"] = {"value": ram_gb, "status": "CRITICAL"}
    elif ram_gb < MIN_RECOMMENDED["ram_gb"]:
        score -= 20
        issues.append(f"RAM {ram_gb} GB is below recommended {MIN_RECOMMENDED['ram_gb']} GB")
        details["ram"] = {"value": ram_gb, "status": "LOW"}
    else:
        details["ram"] = {"value": ram_gb, "status": "GOOD"}

    # API level
    if api < MIN_RECOMMENDED["android_api"]:
        score -= 20
        issues.append(f"Android API {api} is below min recommended API {MIN_RECOMMENDED['android_api']} (Android 8.0)")
        details["api"] = {"value": api, "status": "LOW"}
    elif api < 28:
        score -= 5
        details["api"] = {"value": api, "status": "ACCEPTABLE"}
    else:
        details["api"] = {"value": api, "status": "GOOD"}

    # CPU cores
    if cores < MIN_RECOMMENDED["cpu_cores"]:
        score -= 15
        issues.append(f"Only {cores} CPU cores — min recommended is {MIN_RECOMMENDED['cpu_cores']}")
        details["cores"] = {"value": cores, "status": "LOW"}
    else:
        details["cores"] = {"value": cores, "status": "GOOD"}

    # CPU frequency
    if 0 < freq < MIN_RECOMMENDED["cpu_freq_ghz"]:
        score -= 15
        issues.append(f"CPU max frequency {freq} GHz is below recommended {MIN_RECOMMENDED['cpu_freq_ghz']} GHz")
        details["cpu_freq"] = {"value": freq, "status": "LOW"}
    else:
        details["cpu_freq"] = {"value": freq, "status": "GOOD"}

    # Determine tier
    if score >= 85:
        tier = "EXCELLENT"
    elif score >= 70:
        tier = "GOOD"
    elif score >= 50:
        tier = "ACCEPTABLE"
    else:
        tier = "NOT RECOMMENDED"

    # RAM tier label
    ram_tier = "unknown"
    for t, (lo, hi) in RAM_TIERS.items():
        if lo <= ram_gb < hi:
            ram_tier = t
            break

    return {
        "score":    score,
        "tier":     tier,
        "ram_tier": ram_tier,
        "issues":   issues,
        "details":  details,
    }
