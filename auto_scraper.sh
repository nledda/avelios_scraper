#!/bin/bash
# ============================================================
# LinkedIn Scraper — Lokaler Auto-Scheduler
# ============================================================
# Steuert den LinkedIn-Scraper:
#   - LinkedIn: 3x täglich (8, 13, 18 Uhr)
#
# Starten:   ./auto_scraper.sh start
# Stoppen:   ./auto_scraper.sh stop
# Status:    ./auto_scraper.sh status
# Einmalig:  ./auto_scraper.sh run [linkedin]
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv/bin/activate"
LOG_FILE="$SCRIPT_DIR/logs/auto_scraper.log"
PID_FILE="$SCRIPT_DIR/auto_scraper.pid"
STATE_FILE="$SCRIPT_DIR/data/state/auto_scraper_state.json"

# --- Konfiguration ---

# LinkedIn: Uhrzeiten (lokale Zeit)
LINKEDIN_RUN_HOURS=(8 13 18)

# Zufälliger Delay vor jedem Start (in Sekunden, 0 = deaktiviert)
MAX_RANDOM_DELAY=3600  # max 1 Stunde

# Scheduler-Intervall: wie oft geprüft wird ob ein Run fällig ist (Sekunden)
CHECK_INTERVAL=300  # alle 5 Minuten

# ============================================================

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

activate_venv() {
    if [ ! -f "$VENV" ]; then
        log "Virtuelle Umgebung nicht gefunden. Erstelle..."
        cd "$SCRIPT_DIR"
        uv venv
        source "$VENV"
        uv pip install -r requirements.txt
    else
        source "$VENV"
    fi
}

# --- State Management ---
# Speichert Zeitstempel der letzten Runs um Doppel-Ausführungen zu vermeiden

get_last_run() {
    local scraper="$1"
    if [ -f "$STATE_FILE" ]; then
        python3 -c "
import json, sys
with open('$STATE_FILE') as f:
    state = json.load(f)
print(state.get('${scraper}_last_run', ''))
" 2>/dev/null
    fi
}

set_last_run() {
    local scraper="$1"
    local timestamp="$2"
    python3 -c "
import json, os
state = {}
if os.path.exists('$STATE_FILE'):
    with open('$STATE_FILE') as f:
        state = json.load(f)
state['${scraper}_last_run'] = '${timestamp}'
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
"
}

# --- Scraper Runner ---

run_linkedin() {
    log "──── LinkedIn Scraper ────"
    python3 linkedin_scraper.py >> "$LOG_FILE" 2>&1
    return $?
}

run_scraper() {
    local scraper="$1"
    log "============================================"
    log "Starte $scraper Run..."

    if [ "$MAX_RANDOM_DELAY" -gt 0 ]; then
        DELAY=$((RANDOM % MAX_RANDOM_DELAY))
        log "Zufälliger Delay: ${DELAY}s ($(($DELAY / 60))min)"
        sleep "$DELAY"
    fi

    activate_venv
    cd "$SCRIPT_DIR"

    local EXIT_CODE
    case "$scraper" in
        linkedin)      run_linkedin;      EXIT_CODE=$? ;;
        *)
            log "Unbekannter Scraper: $scraper"
            return 1
            ;;
    esac

    if [ $EXIT_CODE -eq 0 ]; then
        log "$scraper Run erfolgreich beendet."
    else
        log "FEHLER: $scraper beendet mit Exit-Code $EXIT_CODE."
    fi

    set_last_run "$scraper" "$(date '+%Y-%m-%d %H:%M:%S')"
    log "============================================"
}

# --- Schedule Checks ---

is_linkedin_due() {
    local now_hour
    now_hour=$(date '+%H' | sed 's/^0//')
    now_hour=${now_hour:-0}

    for h in "${LINKEDIN_RUN_HOURS[@]}"; do
        if [ "$now_hour" -eq "$h" ]; then
            # Prüfe ob heute zu dieser Stunde schon gelaufen
            local last
            last=$(get_last_run linkedin)
            local today_key
            today_key="$(date '+%Y-%m-%d') ${h}:"
            if [[ "$last" != *"$today_key"* ]] && [[ "$(date '+%Y-%m-%d %H')" == "$(date '+%Y-%m-%d') $(printf '%02d' $h)" ]]; then
                # Noch nicht in dieser Stunde heute gelaufen
                local last_date="${last%% *}"
                local last_hour=""
                if [ -n "$last" ]; then
                    last_hour=$(echo "$last" | awk '{print $2}' | cut -d: -f1 | sed 's/^0//')
                fi
                if [ "$(date '+%Y-%m-%d')" != "$last_date" ] || [ "${last_hour:-99}" -ne "$h" ]; then
                    return 0
                fi
            fi
        fi
    done
    return 1
}

# --- Scheduler Loop ---

scheduler_loop() {
    log "Auto-Scheduler gestartet (PID: $$)"
    log "  LinkedIn:       täglich um ${LINKEDIN_RUN_HOURS[*]}:00 Uhr"
    log "  Check-Intervall: ${CHECK_INTERVAL}s"

    while true; do
        if is_linkedin_due; then
            run_scraper linkedin
        fi

        sleep "$CHECK_INTERVAL"
    done
}

# --- Commands ---

cmd_start() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Scheduler läuft bereits (PID $(cat "$PID_FILE"))."
        exit 1
    fi

    nohup bash "$0" _loop >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "Scheduler gestartet (PID $!)."
    echo "Logs: $LOG_FILE"
}

cmd_stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "Kein laufender Scheduler gefunden."
        exit 1
    fi

    PID=$(cat "$PID_FILE")
    if kill "$PID" 2>/dev/null; then
        rm -f "$PID_FILE"
        log "Scheduler gestoppt (PID $PID)."
        echo "Scheduler gestoppt."
    else
        echo "Prozess $PID nicht gefunden. PID-Datei wird entfernt."
        rm -f "$PID_FILE"
    fi
}

cmd_status() {
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "Scheduler läuft (PID $(cat "$PID_FILE"))."
    else
        echo "Scheduler läuft nicht."
        [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
    fi
    echo ""
    echo "Schedule:"
    echo "  LinkedIn:       täglich um ${LINKEDIN_RUN_HOURS[*]}:00 Uhr"
    echo ""
    echo "Letzte Runs:"
    for s in linkedin; do
        local last
        last=$(get_last_run "$s")
        echo "  $s: ${last:-noch nie}"
    done
}

cmd_run() {
    local target="${1:-linkedin}"
    activate_venv
    run_scraper "$target"
}

case "$1" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    run)     cmd_run "$2" ;;
    _loop)   scheduler_loop ;;
    *)
        echo "Verwendung: $0 {start|stop|status|run [scraper]}"
        echo ""
        echo "  start                — Scheduler im Hintergrund starten"
        echo "  stop                 — Scheduler stoppen"
        echo "  status               — Status + Schedule anzeigen"
        echo "  run [scraper]        — Scraper jetzt einmalig starten"
        echo "                         scraper: linkedin (default)"
        echo ""
        echo "Schedule:"
        echo "  LinkedIn:       3x täglich (${LINKEDIN_RUN_HOURS[*]}:00 Uhr)"
        exit 1
        ;;
esac
