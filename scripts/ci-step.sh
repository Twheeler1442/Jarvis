#!/usr/bin/env bash
# Run one CI step and, if it fails, publish the tail of its output as a GitHub
# annotation.
#
# Why this exists: a failed step's annotation says only "Process completed with
# exit code N". The raw job logs need an authenticated token to fetch, and the
# job summary does not come back through the check-runs API either. Annotations
# do. So a failure that does not reach an annotation is a failure nobody outside
# the web UI can diagnose.
#
#   scripts/ci-step.sh "Install" pip install -e ".[dev,bridge]"
#
# Output still streams to the log as usual; the annotation is an addition, not a
# replacement.

set -uo pipefail

title="$1"
shift

log="$(mktemp)"
trap 'rm -f "$log"' EXIT

# Capture the status of the command itself. Reading $? after an `if` block
# gives the status of the `if`, which is 0 when the condition failed and there
# is no else branch: that swallows the real exit code and turns a failing step
# green.
"$@" >"$log" 2>&1
code=$?

cat "$log"

if [ "$code" -eq 0 ]; then
  exit 0
fi

# Annotations are one line. Fold newlines, and neutralise the `::` that would
# otherwise be read as another workflow command.
message="$(tail -c 900 "$log" | tr '\n\r' '  ' | sed 's/::/;;/g')"
printf '::error title=%s::exit %s | %s\n' "$title" "$code" "$message"
exit "$code"
