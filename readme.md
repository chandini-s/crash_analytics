# Crash Analytics
A cross-platform (Windows & macOS) Jenkins-driven test runner that:
- picks the DUT (device) from Jenkins/job parameters,
- detects the **focused app** on the DUT and automatically selects the right test suite,
- runs `pytest` and produces an **HTML** report *per build*,
---
#### Repository layout
    ├─ extracted_bugreports/   -> extracted bugreport contents
    ├─ downloaded_bugreports/ -> Downloaded & extracted bugreports
    ├─ modules/    -> Re-usable helpers used by tests & runner
    │ ├─ events.py  
    │ ├─ extraction.py 
    │ ├─ generate_download.py 
    │ ├─ mode.py 
    │ └─ version.py 
    ├─ reports/ -> Local-only reports dir (Jenkins uses workspace)
    ├─ testcases/ -> Pytest suites
    │ ├─ tests_devicemode.py -> Device mode tests
    │ ├─ tests_mtr.py -> Microsoft Teams / MTR tests
    │ └─ tests_zoom.py -> Zoom tests
    ├─ Jenkinsfile -> Cross-platform pipeline (Windows/macOS)
    ├─ requirements.txt -> Python dependencies
    ├─ tests_runner.py -> Entry point: selects device, picks suite, runs pytest
    ├─ utils.py -> General utilities (ADB Helpers, Build headers etc)
---
### Requirements 
- **Python** 
- **ADB** on PATH  
  - Windows: install the Android **platform-tools** and add to PATH  
  - macOS: `brew install android-platform-tools`
- **7-Zip / 7zz** (used when bugreport archives are zipped)  
  - Windows: install **7-Zip**   
  - macOS: `brew install sevenzip` (provides `7zz`) or `brew install p7zip`
- Jenkins (optional, for CI)
The pipeline will auto-detect `7z`/`7zz` and won’t fail if it’s missing (only needed when extracting archives). 
---
### Flow
1. Resolve DEVICE 
   - Reads from Jenkins params
   - If IP is given, ensures `:5555`, runs `adb connect`
   - We end up with a single serial to use for ADB
2. Detect focused app
   - Runs `adb shell dumpsys window windows | grep -E 'mCurrentFocus'`
   - Maps to a test target (Zoom, Teams, Device Mode, or all tests)
3. Run Pytest and write reports
    - Runs `pytest` with `--html` and `--junitxml` options
    - Reports are written to `${REPORTS_DIR}/${BUILD_NUMBER}` in Jenkins or `./reports` locally
---
### Jenkins CI 
This repo includes a `Jenkinsfile` that runs on **Windows or macOS** agents.
 
#### Configure the job
 
1. Create a Pipeline job pointing to this repository branch.
2. Check **“This project is parameterized”** and add three **String Parameter** entries (these values are saved with the job and editable later):
   - `DEVICE` – serial or `ip[:port]` (example: `10.91.231.25` or `10.91.231.25:5555`)
   - `AUTH` – full HTTP `Authorization` header value (paste exact; optional)
   - `COOKIE` – full HTTP `Cookie` header value (paste exact; optional)
3. Pin the job to a label/agent (e.g., `lab-windows` / `lab-mac`) via the job’s **“Restrict where this project can be run”**.
 
#### What the pipeline does
 
- Creates a fresh **venv** in the workspace and installs `requirements.txt`.
- Exports report paths:
REPORTS_DIR=$WORKSPACE/reports/${BUILD_NUMBER}
REPORT_FILE=index.html
- Runs `python tests_runner.py`.
- Publishes the HTML report with:
- `keepAll: true` → each build gets its **own** report
- Archives artifacts:
    - `reports/${BUILD_NUMBER}/**/*.html`
    - `downloaded_bugreports/**/*.zip`
    - any generated `debugarchive_*.zip`
- Feeds JUnit XML (`reports/**/results.xml`) into Jenkins test trends. 
After a build, you’ll see a sidebar link like **“Report #<build>”** that opens the frozen HTML for that specific build.

#### How selection works
 
- The runner resolves the DUT in this order:
1. `DEVICE` env (single serial or IP[:port])
2. If an IP is given, runner ensures `:5555`, runs `adb connect`, and picks the serial.

- The runner uses ADB to detect the **focused app** and maps it to a test target:
- “zoom”   → `testcases/tests_zoom.py`
- “teams”  → `testcases/tests_mtr.py`
- “teams”  → `testcases/tests_devicemode.py`
- default  → `testcases` all testcases (if no focused app or no match)
---
#### Reports
- **HTML**: `${REPORTS_DIR}/${REPORT_FILE}` (self-contained HTML)  
- **JUnit XML**: `${REPORTS_DIR}/results.xml`
- In Jenkins, `${REPORTS_DIR}` is `workspace/reports/${BUILD_NUMBER}`, so each build’s report is isolated and permanent.
---
 
#### Environment variables
 
- `DEVICE` – device selector
- `AUTH` / `COOKIE` – full header values used by utilities that call APIs
- `REPORTS_DIR` – report output root
- `REPORT_FILE` – HTML file name (default `index.html`)
- `SEVEN_ZIP` (optional) – full path to `7z`/`7zz` if auto-detect should be overridden 
---

> **Note:** `.venv/` is intentionally not in the repo (created locally/CI).  
> `reports/` is used for **local runs**; Jenkins writes reports under `$WORKSPACE/reports/<BUILD_NUMBER>/`.
 