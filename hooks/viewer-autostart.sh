#!/usr/bin/env bash
# wikiforge — auto-start the read-only Viewer UI on SessionStart.
# Idempotent, non-blocking, fail-safe: never delays session start, never fails the hook.
#   port busy -> no-op · jar present -> launch · jar missing (+java+npm) -> one-time bg build -> launch
# Opt out: WIKIFORGE_VIEWER_AUTOSTART=0 · Port: WIKIFORGE_VIEWER_PORT (default 8080).
set -u

[ "${WIKIFORGE_VIEWER_AUTOSTART:-1}" = "0" ] && exit 0

root="${CLAUDE_PLUGIN_ROOT:-}"
[ -n "$root" ] || root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
viewer="$root/viewer"
jar="$viewer/build/libs/wikiforge-viewer.jar"
port="${WIKIFORGE_VIEWER_PORT:-8080}"
log="${TMPDIR:-/tmp}/wikiforge-viewer.log"

# Already something on the port? Assume the viewer is up.
if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then exec 3>&- 3<&-; exit 0; fi

# Need a JVM to run anything.
command -v java >/dev/null 2>&1 || exit 0

launch() { nohup java -jar "$jar" --server.port="$port" >"$log" 2>&1 & disown 2>/dev/null || true; }

# Jar present -> launch.
if [ -f "$jar" ]; then launch; exit 0; fi

# No jar -> one-time background build (the SPA build needs system npm).
command -v npm >/dev/null 2>&1 || exit 0

lock="$viewer/.autostart-build.lock"
# Reap a stale lock (build died before its EXIT trap ran) so we never wedge.
# NB: `find -mmin +30` exits 0 regardless of matches — test its OUTPUT, else fresh locks get reaped.
[ -d "$lock" ] && [ -n "$(find "$lock" -maxdepth 0 -mmin +30 2>/dev/null)" ] && rmdir "$lock" 2>/dev/null
mkdir "$lock" 2>/dev/null || exit 0     # someone else is already building

# shellcheck disable=SC2016  # $1..$5 are positional args to the inner bash, expanded there, not here.
nohup bash -c '
  trap "rmdir \"$1\" 2>/dev/null || true" EXIT
  cd "$2" || exit 0
  ./gradlew --quiet bootJar >"$5" 2>&1 || exit 0
  [ -f "$3" ] && java -jar "$3" --server.port="$4" >>"$5" 2>&1 &
' _ "$lock" "$viewer" "$jar" "$port" "$log" >/dev/null 2>&1 &
disown 2>/dev/null || true
exit 0
