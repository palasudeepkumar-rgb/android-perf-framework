# Android Mobile Performance Testing Framework
## Performance Engineering CoE

### Quick Start

```bash
# 1. Install dependency
pip3 install python-docx --break-system-packages

# 2. Set your LLM API key (choose one)
export ANTHROPIC_API_KEY=sk-ant-your-key-here
export PERF_LLM_PROVIDER=anthropic          # default

# OR use Gemini
export GEMINI_API_KEY=your-key-here
export PERF_LLM_PROVIDER=gemini

# OR use OpenAI
export OPENAI_API_KEY=your-key-here
export PERF_LLM_PROVIDER=openai

# 3. Connect Android device via USB with USB Debugging enabled

# 4. Run
cd perf_framework
python3 framework.py
```

### Manual Snapshot Trigger
While the test is running, open a NEW terminal and run:
```bash
echo "after-login"   > /tmp/perf_snapshot_trigger
echo "camera-open"   > /tmp/perf_snapshot_trigger
echo "after-trip-1"  > /tmp/perf_snapshot_trigger
```

### Output
All files saved to: `~/Desktop/PerfFramework_Output/<app>_<timestamp>/`

### Switching LLM Provider
```bash
export PERF_LLM_PROVIDER=anthropic   # Claude Sonnet 4.6 (default)
export PERF_LLM_PROVIDER=gemini      # Gemini Flash
export PERF_LLM_PROVIDER=openai      # GPT-4o
```

### AI-Powered Colour-Coded Recommendations (Section 8)

After each test, the framework makes **two LLM API calls**:

| Call | Function | Output | Used In |
|------|----------|--------|---------|
| 14a — Narrative | `analyse_with_llm()` | Free-text analysis | Section 7 |
| 14b — Structured | `analyse_with_llm_structured()` | JSON with priority labels | Section 8 |

The structured call instructs the LLM to return a JSON object:
```json
{
  "overall_risk": "CRITICAL",
  "recommendations": [
    {
      "priority": "CRITICAL",
      "area": "GPS",
      "issue": "3.3 polls/sec is 33x too fast",
      "fix": "Use FusedLocation minInterval=10000ms",
      "benchmark_context": "3.3/s vs 0.1/s standard",
      "estimated_impact": "40-50% battery improvement"
    }
  ],
  "area_findings": { ... }
}
```

These LLM recommendations are then **merged** with rule-based checks from `_build_recommendations()`:
- LLM recs take precedence (more comprehensive, context-aware)
- Rule-based recs fill any gaps the LLM missed
- Duplicates are detected by area and suppressed

The final merged table in Section 8 is **colour-coded**:

| Badge | Colour | When to Use |
|-------|--------|-------------|
| 🔴 CRITICAL — MUST FIX | Red background | Affects every driver every shift |
| 🟠 HIGH — Should Fix | Orange background | Noticeable user impact |
| 🟡 MEDIUM — Nice to Fix | Amber background | Minor impact, fix when capacity allows |
| 🟢 LOW — Backlog | Green background | Cleanup item, minimal real-world impact |

**If no LLM key is set**, Section 8 falls back gracefully to rule-based recommendations only — the report still generates successfully.

### File Structure
```
perf_framework/
├── framework.py              ← Main orchestrator
├── config.py                 ← LLM provider, benchmarks, defaults
├── README.md
├── analysis/
│   ├── llm_analyser.py       ← LLM calls (narrative + structured JSON)
│   └── benchmarks.py         ← Google Android Vitals standards
├── modules/
│   ├── battery.py            ← Battery stats capture & parsing
│   ├── capture.py            ← CPU/memory/GPS/network logcat capture
│   ├── device.py             ← Device profile & suitability scoring
│   ├── network.py            ← SDK detection & redundancy analysis
│   ├── snapshots.py          ← Memory snapshot engine
│   └── start_time.py         ← Cold/warm start measurement
└── report/
    └── generator.py          ← Word report builder (10 sections)
```
