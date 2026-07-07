#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass=0
fail=0

check() {
  local label="$1"
  shift
  if "$@"; then
    printf 'OK   %s\n' "$label"
    pass=$((pass + 1))
  else
    printf 'FAIL %s\n' "$label"
    fail=$((fail + 1))
  fi
}

echo "NetBackup cron diagnostics"
echo "Install root: $ROOT"
echo

check "logs directory exists" test -d "$ROOT/logs"
check "run_backup.sh exists" test -f "$ROOT/scripts/run_backup.sh"
check "run_backup.sh is executable" test -x "$ROOT/scripts/run_backup.sh"
check "run_backup.sh uses Unix line endings" bash -n "$ROOT/scripts/run_backup.sh"
check "python3 or python available" sh -c 'command -v python3 >/dev/null || command -v python >/dev/null'
check "inventory file exists" test -f "$ROOT/config/devices.yml"
check "can write cron.log" sh -c "echo test >> '$ROOT/logs/cron.log'"

if [ -d "$ROOT/.venv" ]; then
check ".venv python works" sh -c "PYTHONPATH='$ROOT/src' '$ROOT/.venv/bin/python' -c 'import netbackup'"
else
  check "system python can import netbackup" sh -c "PYTHONPATH='$ROOT/src' python3 -c 'import netbackup'"
fi

echo
if crontab -l >/dev/null 2>&1; then
  if crontab -l 2>/dev/null | grep -F "$ROOT" >/dev/null; then
    echo "OK   crontab contains an entry for this install path"
    crontab -l | grep -F "$ROOT" || true
  else
    echo "FAIL crontab has no entry pointing at $ROOT"
    echo "     Add the line from scripts/cron.example with your real path."
    fail=$((fail + 1))
  fi
else
  echo "FAIL no crontab for user $(whoami)"
  fail=$((fail + 1))
fi

echo
echo "Manual test (should append to logs/cron.log and logs/netbackup.log):"
echo "  $ROOT/scripts/run_backup.sh"
echo
printf 'Result: %s passed, %s failed\n' "$pass" "$fail"
exit "$fail"
