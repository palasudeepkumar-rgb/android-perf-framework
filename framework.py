#!/usr/bin/env python3
"""
framework.py — Android Mobile Performance Testing Framework
Usage:
    python3 framework.py

Supports any Android app. Set provider via env var:
    export PERF_LLM_PROVIDER=anthropic   (default)
    export PERF_LLM_PROVIDER=gemini
    export PERF_LLM_PROVIDER=openai
    export ANTHROPIC_API_KEY=sk-ant-...
"""

import sys, os, json, time, subprocess, threading

# ── Path setup ───────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "modules"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "analysis"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "report"))

from config import OUTPUT_DIR, TRIGGER_FILE, LLM_PROVIDER

# ── Colours for terminal output ───────────────────────────────────────────────
class C:
    BLUE   = "\033[94m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BOLD   = "\033[1m"
    END    = "\033[0m"
    CYAN   = "\033[96m"

def banner():
    print(f"""
{C.BLUE}{C.BOLD}╔══════════════════════════════════════════════════════════════╗
║     Android Mobile Performance Testing Framework v1.0        ║
║     Performance Engineering CoE                               ║
╚══════════════════════════════════════════════════════════════╝{C.END}
""")

def step(n, text):
    print(f"\n{C.BOLD}{C.CYAN}── Step {n}: {text} ──{C.END}")

def ok(text):    print(f"  {C.GREEN}✔  {text}{C.END}")
def warn(text):  print(f"  {C.YELLOW}⚠  {text}{C.END}")
def err(text):   print(f"  {C.RED}✖  {text}{C.END}")
def info(text):  print(f"  {C.BLUE}ℹ  {text}{C.END}")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _adb(cmd):
    r = subprocess.run(f"adb shell {cmd}", shell=True,
                       capture_output=True, text=True, timeout=15)
    return r.stdout.strip()

def _ask(prompt, choices=None, default=None):
    """Prompt user for input with optional choices."""
    if choices:
        opts = " / ".join([f"[{c}]" for c in choices])
        prompt = f"{prompt} {opts}: "
    else:
        prompt = f"{prompt}: "
    while True:
        ans = input(f"  {C.BOLD}{prompt}{C.END}").strip()
        if not ans and default is not None:
            return default
        if choices and ans not in choices:
            print(f"  {C.YELLOW}Please enter one of: {', '.join(choices)}{C.END}")
            continue
        return ans

def _ask_int(prompt, choices_int, default=None):
    choices = [str(c) for c in choices_int]
    ans = _ask(prompt, choices=choices, default=str(default) if default else None)
    return int(ans)

def check_adb():
    r = subprocess.run("adb devices", shell=True, capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines()[1:] if "device" in l]
    return len(lines) > 0

def get_app_info(package):
    """Get version and app name from device."""
    dumpsys = _adb(f"dumpsys package {package}")
    info = {"package": package}
    import re
    m = re.search(r"versionName=([^\s]+)", dumpsys)
    info["version"] = m.group(1) if m else "N/A"
    m = re.search(r"versionCode=([^\s]+)", dumpsys)
    info["version_code"] = m.group(1) if m else "N/A"
    # Try to get a friendly name from label
    label = _adb(f"pm list packages -f {package}").split("=")[0].replace("package:", "").strip()
    info["app_name"] = package.split(".")[-1].capitalize()
    return info

def get_main_activity(package):
    """Auto-detect the main launcher activity."""
    out = _adb(f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {package}")
    for line in out.splitlines():
        if "/" in line and not line.startswith("No"):
            return line.strip().split("/")[-1]
    # Fallback
    out2 = _adb(f"dumpsys package {package} | grep 'android.intent.action.MAIN' -A 1")
    import re
    m = re.search(r"([A-Za-z.]+Activity)", out2)
    return m.group(1) if m else "MainActivity"


# ── Main orchestration ────────────────────────────────────────────────────────
def main():
    banner()

    # ── 1. Check adb ─────────────────────────────────────────────────────
    step(1, "Device Connection Check")
    if not check_adb():
        err("No device detected. Connect device via USB and enable USB Debugging.")
        sys.exit(1)
    ok("Device connected and authorised.")

    # ── 2. App & Activity ────────────────────────────────────────────────
    step(2, "App Configuration")
    package = _ask("Enter app package name (e.g. com.example.app)")
    if not package:
        err("Package name is required.")
        sys.exit(1)

    # Verify app installed
    installed = _adb(f"pm list packages | grep {package}")
    if package not in installed:
        err(f"Package '{package}' not found on device.")
        sys.exit(1)
    ok(f"App found: {package}")

    activity_auto = get_main_activity(package)
    activity = _ask(
        f"Main activity (detected: {activity_auto}, press Enter to use it)",
        default=activity_auto
    ) or activity_auto
    ok(f"Activity: {activity}")

    app_info = get_app_info(package)
    ok(f"Version: {app_info.get('version','N/A')}")

    # ── 3. Session Configuration ─────────────────────────────────────────
    step(3, "Session Configuration")

    # Snapshot mode
    print(f"\n  {C.BOLD}Snapshot options:{C.END}")
    print("    [1] Auto snapshots at fixed intervals")
    print("    [2] User-triggered snapshots only (manual control)")
    print("    [3] Both (auto + manual trigger)")
    snap_mode = _ask_int("Choose snapshot mode", [1, 2, 3], default=3)

    auto_interval = None
    if snap_mode in (1, 3):
        auto_interval = _ask_int(
            "Auto-snapshot interval (minutes)", [3, 5, 10, 15], default=5
        )
        ok(f"Auto-snapshot every {auto_interval} minutes")

    if snap_mode in (2, 3):
        print(f"\n  {C.BOLD}Manual snapshot trigger:{C.END}")
        print(f"    During the test, open a NEW terminal and run:")
        print(f"{C.CYAN}      echo \"your-label\" > {TRIGGER_FILE}{C.END}")
        print("    Examples:")
        print(f"{C.CYAN}      echo \"after-login\" > {TRIGGER_FILE}{C.END}")
        print(f"{C.CYAN}      echo \"camera-open\" > {TRIGGER_FILE}{C.END}")
        print(f"{C.CYAN}      echo \"after-trip-1\" > {TRIGGER_FILE}{C.END}")
        input(f"\n  {C.BOLD}Press Enter when you understand the trigger method...{C.END}")

    # LLM provider
    print(f"\n  {C.BOLD}LLM Analysis provider (current: {LLM_PROVIDER}):{C.END}")
    print("    Set via env var: export PERF_LLM_PROVIDER=anthropic|gemini|openai")
    print("    Set API key:     export ANTHROPIC_API_KEY=your_key")
    use_llm = _ask("Run LLM analysis after test?", ["yes", "no"], default="yes")

    # Output dir
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session_dir = os.path.join(OUTPUT_DIR, f"{package.split('.')[-1]}_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(session_dir, exist_ok=True)
    ok(f"Output directory: {session_dir}")

    # ── 4. Device Info ───────────────────────────────────────────────────
    step(4, "Collecting Device Profile")
    from modules.device import get_device_info, assess_suitability
    device_info = get_device_info()
    suitability = assess_suitability(device_info)

    ok(f"Device: {device_info.get('brand','')} {device_info.get('model','')}")
    ok(f"RAM: {device_info.get('ram_total_gb','')} GB  |  CPU: {device_info.get('cpu_cores','')} cores @ {device_info.get('cpu_max_freq_ghz','')} GHz")
    ok(f"Android: {device_info.get('android_ver','')} (API {device_info.get('api_level','')})")
    ok(f"Suitability: {suitability['score']}/100 — {suitability['tier']}")
    for iss in suitability.get("issues", []):
        warn(iss)

    # ── 5. Reset Stats ───────────────────────────────────────────────────
    step(5, "Reset Battery Stats")
    subprocess.run("adb shell dumpsys batterystats --reset",
                   shell=True, capture_output=True)
    ok("Battery stats reset.")

    # ── 6. Cold & Warm Start ─────────────────────────────────────────────
    step(6, "Cold & Warm Start Measurements")
    from modules.start_time import measure_cold_start, measure_warm_start, summarise, rate_start_time

    cold_results = measure_cold_start(package, activity)
    cold_summary = summarise(cold_results)
    ok(f"Cold Start avg: {cold_summary['avg']} ms  [{rate_start_time(cold_summary['avg'],'cold')}]")

    warm_results = measure_warm_start(package, activity)
    warm_summary = summarise(warm_results)
    ok(f"Warm Start avg: {warm_summary['avg']} ms  [{rate_start_time(warm_summary['avg'],'warm')}]")

    # ── 7. Baseline Snapshot ─────────────────────────────────────────────
    step(7, "Baseline Snapshot (Before User Interaction)")
    info("Launching app to idle state...")
    subprocess.run(f"adb shell am start -n {package}/{activity}",
                   shell=True, capture_output=True)
    time.sleep(5)

    from modules.snapshots import SnapshotEngine
    snap_engine = SnapshotEngine(package, session_dir)
    snap_engine.take_snapshot("baseline-idle")
    ok("Baseline captured.")

    # ── 8. Start All Captures ────────────────────────────────────────────
    step(8, "Starting Background Captures")
    from modules.capture import CaptureEngine
    cap_engine = CaptureEngine(package, session_dir)
    cap_engine.start(interval_sec=10)
    ok("CPU + Memory loop started (every 10s)")
    ok("GPS/Camera logcat started")
    ok("Network/API logcat started")
    ok("Full app logcat started")

    # ── 9. Start Snapshot Engine ─────────────────────────────────────────
    step(9, "Starting Snapshot Engine")
    snap_engine.start(auto_interval_min=auto_interval)
    ok("Snapshot engine ready.")

    # ── 10. Test Session ─────────────────────────────────────────────────
    print(f"""
{C.GREEN}{C.BOLD}
╔══════════════════════════════════════════════════════════════╗
║              ALL CAPTURES ARE NOW RUNNING                    ║
║                                                              ║
║  Go ahead and use the app on your device.                   ║
║                                                              ║
║  Manual snapshot (in a new terminal):                       ║
║    echo "label" > {TRIGGER_FILE:<36}║
║                                                              ║
║  When DONE, come back here and press Enter.                 ║
╚══════════════════════════════════════════════════════════════╝
{C.END}""")
    input(f"  {C.BOLD}Press Enter when your test session is complete...{C.END}")

    session_end = time.strftime("%Y-%m-%d %H:%M:%S")
    session_duration_min = max(1, round(
        (time.time() - os.path.getmtime(session_dir)) / 60
    ))

    # ── 11. Final Snapshot ───────────────────────────────────────────────
    step(11, "Capturing Final Snapshot")
    snap_engine.take_snapshot("session-end")
    time.sleep(2)
    snap_engine.stop()
    cap_engine.stop()
    snaps_path = snap_engine.save_summary()
    ok(f"All snapshots saved ({len(snap_engine.snapshots)} total)")

    # ── 12. Battery Capture ──────────────────────────────────────────────
    step(12, "Battery & Hardware Data Capture")
    from modules.battery import capture_battery_stats, capture_bugreport, parse_battery_stats
    stats_path  = capture_battery_stats(session_dir)
    battery_data = parse_battery_stats(stats_path)
    ok(f"Camera sessions: {battery_data.get('camera_sessions',0)}")
    ok(f"GPS activations: {battery_data.get('gps_activations',0)}")
    ok(f"Was charging: {battery_data.get('was_charging',False)}")
    if battery_data.get("was_charging"):
        warn("Device was charging — battery drain figures unavailable. Re-run with USB unplugged.")

    do_bugreport = _ask("Capture bugreport.zip? (takes 2-3 mins)", ["yes","no"], default="yes")
    if do_bugreport == "yes":
        capture_bugreport(session_dir)

    # ── 13. Network Analysis ─────────────────────────────────────────────
    step(13, "Analysing Network & SDK Data")
    from modules.network import analyse_network_logs
    files = cap_engine.output_files()
    network_data = analyse_network_logs(
        files.get("network_calls"), files.get("app_logs"), package
    )
    ok(f"SDKs detected: {', '.join(network_data.get('sdks_detected',[]) or ['None'])}")
    ok(f"Redundant calls found: {len(network_data.get('redundant_calls',[]))}")
    ok(f"Total background jobs: {network_data.get('total_jobs',0)}")

    # ── 14. LLM Analysis ─────────────────────────────────────────────────
    llm_text       = ""
    llm_structured = {}
    if use_llm == "yes":
        step(14, f"LLM Analysis via {LLM_PROVIDER.capitalize()}")
        from analysis.llm_analyser import analyse_with_llm, analyse_with_llm_structured
        all_data_for_llm = {
            "device":      device_info,
            "suitability": suitability,
            "cold_start":  cold_summary,
            "warm_start":  warm_summary,
            "snapshots":   snap_engine.snapshots,
            "battery":     battery_data,
            "network":     network_data,
            "app_info":    app_info,
        }

        # 14a — Free-text narrative (Section 7 of report)
        info(f"Sending data to {LLM_PROVIDER} for narrative analysis...")
        llm_text = analyse_with_llm(all_data_for_llm)
        ok("LLM narrative analysis complete.")
        print(f"\n{C.CYAN}── LLM Analysis Preview (first 300 chars) ──{C.END}")
        print(llm_text[:300] + "...")

        # 14b — Structured JSON recommendations (Section 8 of report)
        info(f"Sending data to {LLM_PROVIDER} for structured recommendations...")
        llm_structured = analyse_with_llm_structured(all_data_for_llm)
        rec_count = len(llm_structured.get("recommendations", []))
        if rec_count:
            ok(f"Structured LLM recommendations: {rec_count} findings "
               f"(overall risk: {llm_structured.get('overall_risk','?')})")
            # Show priority breakdown in terminal
            from collections import Counter
            p_counts = Counter(r.get("priority","?") for r in llm_structured["recommendations"])
            for lvl in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if p_counts.get(lvl, 0):
                    colour = {"CRITICAL": C.RED, "HIGH": C.YELLOW,
                              "MEDIUM": C.YELLOW, "LOW": C.GREEN}.get(lvl, C.END)
                    print(f"    {colour}{lvl}: {p_counts[lvl]}{C.END}")
        else:
            warn("Structured LLM call returned no recommendations — falling back to rule-based only.")

    # ── 15. Build Report ─────────────────────────────────────────────────
    step(15, "Building Word Report")
    # Install python-docx if needed
    try:
        import docx
    except ImportError:
        info("Installing python-docx...")
        subprocess.run("pip3 install python-docx --break-system-packages -q", shell=True)

    from report.generator import build_report
    all_data = {
        "device":                device_info,
        "suitability":           suitability,
        "cold_start":            cold_summary,
        "warm_start":            warm_summary,
        "snapshots":             snap_engine.snapshots,
        "battery":               battery_data,
        "network":               network_data,
        "app_info":              app_info,
        "session_duration_min":  f"{session_duration_min} minutes",
    }

    report_path = build_report(all_data, llm_text, session_dir, llm_structured=llm_structured)
    ok(f"Report saved: {report_path}")

    # ── 16. Save raw JSON ─────────────────────────────────────────────────
    raw_path = os.path.join(session_dir, "raw_data.json")
    try:
        with open(raw_path, "w") as f:
            json.dump({k: v for k, v in all_data.items() if k != "snapshots"}, f, indent=2, default=str)
    except Exception:
        pass

    # ── Done ─────────────────────────────────────────────────────────────
    print(f"""
{C.GREEN}{C.BOLD}
╔══════════════════════════════════════════════════════════════╗
║                  TEST SESSION COMPLETE                       ║
╚══════════════════════════════════════════════════════════════╝{C.END}

  {C.BOLD}Output directory:{C.END}  {session_dir}

  {C.BOLD}Files created:{C.END}
    📄 {os.path.basename(report_path)}   ← Word report
    📊 perf_stats.txt                    ← CPU + Memory timeline
    📡 gps_camera_logs.txt               ← GPS / Camera events
    🌐 network_calls.txt                 ← Network / API calls
    📱 app_logs.txt                      ← Full app logs
    🔋 battery_stats.txt                 ← Battery hardware data
    📸 snapshot_*.txt                    ← Individual snapshots
    📋 snapshots_summary.json            ← Structured snapshot data
    💾 raw_data.json                     ← All collected data (JSON)
""")

    print(f"  {C.CYAN}Open the report:{C.END}  open \"{report_path}\"\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}Test interrupted by user. Partial data may have been saved.{C.END}\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n{C.RED}Fatal error: {e}{C.END}")
        import traceback; traceback.print_exc()
        sys.exit(1)
