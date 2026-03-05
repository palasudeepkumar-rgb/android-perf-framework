"""
config.py — Central configuration for the Mobile Performance Testing Framework
DP World Performance Engineering CoE
"""

import os

# ─────────────────────────────────────────────────────────────────────────────
# LLM Provider Configuration
# Set PERF_LLM_PROVIDER env var to switch providers: anthropic | gemini | openai
# ─────────────────────────────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("PERF_LLM_PROVIDER", "anthropic")

LLM_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "gemini":    "gemini-1.5-flash",
    "openai":    "gpt-4o",
}

API_KEYS = {
    "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
    "gemini":    os.environ.get("GEMINI_API_KEY", ""),
    "openai":    os.environ.get("OPENAI_API_KEY", ""),
}

# ─────────────────────────────────────────────────────────────────────────────
# Framework defaults
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_COLD_WARM_RUNS   = 3          # How many times to measure cold/warm start
PERF_LOOP_INTERVAL_SEC   = 10         # CPU+Mem capture interval in seconds
TRIGGER_FILE             = "/tmp/perf_snapshot_trigger"   # User-triggered snapshot signal file
OUTPUT_DIR               = os.path.join(os.path.expanduser("~"), "Desktop", "PerfFramework_Output")

# ─────────────────────────────────────────────────────────────────────────────
# Industry benchmark thresholds (Google / Android standards)
# ─────────────────────────────────────────────────────────────────────────────
BENCHMARKS = {
    "cold_start_ms":     {"excellent": 1000, "good": 2000, "acceptable": 5000},
    "warm_start_ms":     {"excellent": 200,  "good": 800,  "acceptable": 2000},
    "idle_pss_mb":       {"excellent": 50,   "good": 100,  "acceptable": 150},
    "active_pss_mb":     {"excellent": 100,  "good": 200,  "acceptable": 300},
    "idle_cpu_pct":      {"excellent": 2,    "good": 5,    "acceptable": 10},
    "active_cpu_pct":    {"excellent": 30,   "good": 50,   "acceptable": 80},
    "gl_mtrack_mb":      {"excellent": 10,   "good": 20,   "acceptable": 40},
    "swap_pss_mb":       {"excellent": 0,    "good": 10,   "acceptable": 30},
    "gps_activations_per_min": {"excellent": 2, "good": 6, "acceptable": 12},
    "camera_sessions_per_trip": {"excellent": 4, "good": 8, "acceptable": 14},
}

# Device RAM tiers for suitability scoring
RAM_TIERS = {
    "low":    (0,   3),    # 0-3 GB   — marginal
    "medium": (3,   6),    # 3-6 GB   — acceptable
    "high":   (6,   10),   # 6-10 GB  — good
    "ultra":  (10,  999),  # 10+ GB   — excellent
}

# Min recommended specs for business Android apps
MIN_RECOMMENDED = {
    "ram_gb":         4,
    "android_api":    26,   # Android 8.0+
    "cpu_cores":      4,
    "cpu_freq_ghz":   1.8,
}
