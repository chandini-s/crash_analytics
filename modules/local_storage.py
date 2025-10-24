
"""
CrashAnalytics: DOWN -> broadcast -> on-device poll -> UP Ethernet

Flow
1) Baseline (optional): list CrashAnalytics cache.
2) Launch ONE background chain on the DUT (runs under `nohup sh -c '...' &`):
      - auto-detect an Ethernet-ish iface (eth*/en*/usb*, fallback eth0)
      - ip link set IFACE down
      - sleep 5
      - send CrashAnalytics GENERATE_BUG_REPORT broadcast
      - poll cache every 3 minutes (5 tries = 15 minutes) for android-bugreport*.mar
      - IF found => write status=found, path=..., bring IFACE up, exit 0
      - IF timeout => write status=timeout, bring IFACE up, exit non-zero
   All actions log to /data/local/tmp/ca_chain.log and a short result to
   /data/local/tmp/ca_chain.status .
3) Because this is ADB over TCP/IP, the host reconnects and simply reads the status/log.

You asked to avoid 'su': this script uses only plain `adb shell`.
"""

# ---------------------------------

import os
import shlex
import subprocess
import sys
import time
import utils


DEVICE = utils.get_selected_device() # adb tcp/ip serial (IP:PORT)
#DEVICE = "10.91.208.243"
CACHE_PATH = "/data/data/com.logitech.crashanalytics/cache"
MAR_GLOB = "android-bugreport*.mar"
BROADCAST_CMD = ("am broadcast -a com.logitech.intent.action.GENERATE_BUG_REPORT "
                 "-n com.logitech.crashanalytics/com.memfault.bort.receivers.ControlReceiver")

STATUS_FILE = "/data/local/tmp/crashanalytics_chain.status"
LOG_FILE = "/data/local/tmp/crashanalytics_chain.log"


def run(cmd, check=True, timeout=120):
    """ Run a command and return its stdout. Raise RuntimeError on failure if check=True."""
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"cmd failed ({p.returncode}): {' '.join(cmd)}\n{p.stderr}")
    return p.stdout.strip()


def adb(args, check=True, timeout=120):
    """ Run an adb command targeting DEVICE and return its stdout."""
    return run(["adb", "-s", DEVICE] + (args if isinstance(args, list) else shlex.split(args)),
               check=check, timeout=timeout)


def adb_shell(shell_cmd, check=True, timeout=120):
    """ Run an adb shell command targeting DEVICE and return its stdout."""
    if isinstance(shell_cmd, str):
        return adb(["shell", shell_cmd], check=check, timeout=timeout)
    return adb(["shell"] + shell_cmd, check=check, timeout=timeout)


def ensure_online():
    """Check if the device is online."""
    try:
        out = adb(["get-state"], check=False, timeout=5)
        return "device" in out
    except Exception:
        return False


def ensure_adbd_root():
    """Ensure adbd is running as root (best-effort)."""
    try:
        root_cmd = (f'adb -s {DEVICE} root')
        subprocess.run(root_cmd, shell=True, check=True)
    except Exception as e:
        print(f"[WARN] Could not restart adbd as root: {e}", file=sys.stderr)


def adb_connect_loop(total_seconds=240):
    """Reconnect to the TCP/IP device and wait-for-device within total_seconds."""
    deadline = time.time() + total_seconds
    while time.time() < deadline:
        try:
            run(["adb", "connect", DEVICE], check=False, timeout=10)
            adb(["wait-for-device"], check=False, timeout=30)
            if ensure_online():
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def clear_ca_cache():
    """
    Best-effort cleanup of CrashAnalytics cache before the test.
    Removes only android-bugreport*.mar so other app files stay intact.
    Also clears previous status/log files so results aren't stale.
    """
    # primary cache
    adb_shell(f'mkdir -p {CACHE_PATH} 2>/dev/null || true', check=False)
    adb_shell(f'rm -f {CACHE_PATH}/{MAR_GLOB} 2>/dev/null || true', check=False)

    # fallback cache (if the app uses user_de)
    fallback = "/data/user_de/0/com.logitech.crashanalytics/cache"
    adb_shell('mkdir -p ' + fallback + ' 2>/dev/null || true', check=False)
    adb_shell(f'rm -f {fallback}/{MAR_GLOB} 2>/dev/null || true', check=False)

    # clear previous run artifacts
    adb_shell(f'rm -f {STATUS_FILE} {LOG_FILE} 2>/dev/null || true', check=False)


def list_cache(path=CACHE_PATH):
    """List files in the CrashAnalytics cache path."""
    return adb_shell(f"ls -la {path} 2>/dev/null || true", check=False)


def read_status():
    """Read the status file from the device."""
    return adb_shell(f"cat {STATUS_FILE} 2>/dev/null || true", check=False)


def read_log_tail(n=60):
    """Read the last n lines of the log file from the device."""
    return adb_shell(f"tail -n {n} {LOG_FILE} 2>/dev/null || true", check=False)


def launch_background_chain(iface, broadcast_cmd=BROADCAST_CMD):
    """
    Start ONE background job on the DUT that does the following:
      1) iface DOWN
      2) broadcast CrashAnalytics intent
      3) poll cache every 3 min (5 tries = 15 min) for android-bugreport*.mar
      4) IF found -> iface UP; IF timeout -> iface UP
      5) write status to /data/local/tmp/ca_chain.status and logs to /data/local/tmp/crashanalytics_chain.log
    """
    chained = f"""nohup sh -c '
    LOG={LOG_FILE}
    ST={STATUS_FILE}
    : >"$LOG"; : >"$ST"

    # If iface not provided, best-effort autodetect (no su)
    IFACE="{iface}"
    if [ -z "$IFACE" ]; then
      IFACE=$(ip -o -br link | awk "\\$1!=\\"lo\\" && \\$1 ~ /^(eth|en|usb)/ {{print \\$1; exit}}")
    fi
    echo "IFACE=$IFACE" >>"$LOG"

    CACHE1={CACHE_PATH}
    CACHE2=/data/user_de/0/com.logitech.crashanalytics/cache
    GLOB={MAR_GLOB}

    baseline() {{
      ls -t "$CACHE1"/$GLOB 2>/dev/null | head -n 1 || ls -t "$CACHE2"/$GLOB 2>/dev/null | head -n 1
    }}

    BASE=$(baseline)
    echo "BASE=${{BASE:-none}}" >>"$LOG"

    # --- DOWN -> broadcast -> poll ---
    echo "Bringing $IFACE DOWN..." >>"$LOG"

    # kill any IP so connectivity dies even if carrier flips up
    (ip addr flush dev "$IFACE" 2>>"$LOG" || true)
    (ifconfig "$IFACE" down 2>>"$LOG" || true)
    (ip link set "$IFACE" down 2>>"$LOG" || true)
    (ndc interface setcfg "$IFACE" 0.0.0.0 0 down 2>>"$LOG" || true)  # if ndc exists

    # confirm DOWN (no single quotes; parse with shell)
    for i in 1 2 3 4 5; do
      LINE="$(ip -br link show "$IFACE" 2>/dev/null)"
      STATE="${{LINE#* }}"; STATE="${{STATE%% *}}"
      echo "$IFACE  $STATE" >>"$LOG"
      [ "$STATE" = "DOWN" ] && break
      sleep 2
    done

    # always log the final state
    ip -br link show "$IFACE" >>"$LOG"

    # capture trigger time
    sleep 5
    TRIG_EPOCH="$(date +%s)"
    TRIG_ISO="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    echo "broadcasting intent..." >>"$LOG"
    echo "cmd={broadcast_cmd}" >>"$LOG"
    which am >>"$LOG" 2>&1 || true
    id >>"$LOG" 2>&1 || true

    # TRY 1
    eval {broadcast_cmd} >>"$LOG" 2>&1
    RC1=$?
    # TRY 2 fallback
    if [ $RC1 -ne 0 ]; then
      echo "am broadcast failed rc=$RC1, trying cmd activity broadcast..." >>"$LOG"
      cmd activity broadcast -a com.logitech.intent.action.GENERATE_BUG_REPORT \\
        -n com.logitech.crashanalytics/com.memfault.bort.receivers.ControlReceiver \\
        >>"$LOG" 2>&1
      RC2=$?
    else
      RC2=0
    fi
    echo "broadcast_rc1=$RC1 broadcast_rc2=$RC2" >>"$LOG"

    # always append trigger time
    {{
      echo "trigger_epoch=${{TRIG_EPOCH}}"
      echo "trigger_utc=${{TRIG_ISO}}"
    }} >>"$ST"

    # fail fast if both broadcasts failed
    if [ $RC1 -ne 0 ] && [ $RC2 -ne 0 ]; then
      echo "status=broadcast_failed" >>"$ST"
      exit 2
    fi

    NEW=
    i=1
    while [ $i -le 5 ]; do
      sleep 180
      C=$(baseline)
      echo "poll $i -> ${{C:-none}}" >>"$LOG"
      if [ -n "$C" ] && [ "$C" != "$BASE" ]; then
        NEW=$C
        echo "FOUND=$NEW" >>"$LOG"
        echo "status=found" >"$ST"
        echo "path=$NEW" >>"$ST"
        echo "trigger_epoch=${{TRIG_EPOCH}}" >>"$ST"
        echo "trigger_utc=${{TRIG_ISO}}" >>"$ST"
        (ip link set "$IFACE" up || ifconfig "$IFACE" up || true) 2>>"$LOG"
        ip -br link show "$IFACE" >>"$LOG"
        exit 0
      fi
      i=$((i+1))
    done

    # timeout: still bring link UP
    echo "status=timeout" >"$ST"
    echo "path=" >>"$ST"
    echo "trigger_epoch=${{TRIG_EPOCH}}" >>"$ST"
    echo "trigger_utc=${{TRIG_ISO}}" >>"$ST"
    (ip link set "$IFACE" up || ifconfig "$IFACE" up || true) 2>>"$LOG"
    ip -br link show "$IFACE" >>"$LOG"
    exit 1
    ' >/data/local/tmp/ca_chain.out 2>&1 &"""
    adb_shell(chained, check=False, timeout=5)
    print(f">> background chain (poll; up on success/timeout) started (iface={iface or 'auto'})")


def parse_status_field(text_or_map: str | dict, key: str) -> str:
    """
    Returns the value for a given key from the chain status.
    Accepts either the raw status *string* or a pre-parsed *dict*.
    """
    # If we've already got a dict, just read it.
    if isinstance(text_or_map, dict):
        return (text_or_map or {}).get(key, "") or ""

    # Original string parsing path (your current logic)
    text = text_or_map or ""
    prefix = key + "="
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""

def status_to_dict(text_or_map: str | dict) -> dict:
    """Normalize status to a dict with the usual keys."""
    if isinstance(text_or_map, dict):
        return text_or_map
    return {
        "status":        parse_status_field(text_or_map, "status")        or "",
        "path":          parse_status_field(text_or_map, "path")          or "",
        "trigger_epoch": parse_status_field(text_or_map, "trigger_epoch") or "",
        "trigger_utc":   parse_status_field(text_or_map, "trigger_utc")   or "",
    }


def filebase(p: str) -> str:
    """Returns the base filename from a given path, or empty string if path is empty."""
    return os.path.basename(p) if p else ""


def extract_portal_path(report):
    """
    Normalizes whatever your poller returns into a path string.
    Supports:
      - {"path": "..."}
      - {"details": {"path": "..."}}
      - {"report": {"path": "..."}}
      - plain string "..."
    """
    if isinstance(report, str):
        return report
    if isinstance(report, dict):
        if "path" in report and report["path"]:
            return report["path"]
        if "details" in report and isinstance(report["details"], dict) and report["details"].get("path"):
            return report["details"]["path"]
        if "report" in report and isinstance(report["report"], dict) and report["report"].get("path"):
            return report["report"]["path"]
    return ""


def bugreport_without_internet(iface) :
    """
    End-to-end check (single on-demand bugreport while the device is offline):
      1) Make sure ADB over TCP is online and adbd is root
      2) Clear CrashAnalytics cache/status/log on the device
      3) Record a baseline cache listing for visibility
      4) Start the on-device chain:
           - bring IFACE DOWN
           - fire the on-demand broadcast
           - poll CrashAnalytics cache every 3 minutes (max 15 minutes)
           - IF FOUND: write status+path and bring IFACE UP immediately
           - IF TIMEOUT: write status=timeout and still bring IFACE UP
      5) From the host, monitor the status file and log until the chain finished
      Returns a dict parsed from /data/local/tmp/ca_chain.status with keys
    """
    print("=== chain command (DOWN -> broadcast -> poll for .mar file -> UP after getting .mar file) ===")
    if not ensure_online():
        print("Connecting to device...")
        if not adb_connect_loop(60):
            print("[ERROR] Could not connect to device.", file=sys.stderr)
            sys.exit(1)
    print(">> Device online:", DEVICE)
    ensure_adbd_root()
    print("\n[0] Clearing previous CrashAnalytics cache, status, and log…")
    clear_ca_cache()
    # baseline (optional)
    print("\n[1] Baseline cache listing:")
    print(list_cache() or "(no access or empty)")

    # launch chain
    # iface = detect_iface()
    #iface = "eth0"
    print(f"\n[2] Launch chain on DUT (iface={iface})")
    launch_background_chain(iface)
    print("\n[3] Monitoring for .mar file in local (device may drop ADB briefly)...")
    deadline = time.time() + (15 * 60) + 5 * 60  # extra 5 min for buffer after wait_time
    while time.time() < deadline:
        adb_connect_loop(15)
        st = read_status().strip()
        if st:
            print("\n--- STATUS ---")
            print(st)
            print("\n--- LIST OF FOUND .mar FILES ---")
            print(adb_shell("cat /data/local/tmp/ca_chain.list 2>/dev/null || true", check=False))
            print("\n--- LAST LOG ---")
            print(read_log_tail(80))
            break
        time.sleep(30)
    else:
        print("\n[WARN] No status yet. Recent log:")
        print(read_log_tail(120))
        print("\nRaw nohup stdout (if any):")
        print(adb_shell("cat /data/local/tmp/ca_chain.out 2>/dev/null || true", check=False))

    st = adb_shell(f"cat {STATUS_FILE} 2>/dev/null || true", check=False)
    print("\n--- STATUS ---")
    print(st)
    return status_to_dict(st)

