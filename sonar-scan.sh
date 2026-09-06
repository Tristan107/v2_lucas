#!/usr/bin/env bash
set -euo pipefail

SONAR_HOST="${SONAR_HOST:-http://localhost:9000}"
SONAR_TOKEN="${SONAR_TOKEN:-sqa_b79b9054ff75dfea0341774492504d8573f46e22}"
PROJECT_KEY="v2_lucas"
MAX_WAIT=120

uv run pytest --cov=lucas_v2 --cov-report=xml:coverage.xml --cov-report=term-missing

uvx pysonar \
  --sonar-host-url="$SONAR_HOST" \
  --sonar-token="$SONAR_TOKEN" \
  --sonar-project-key="$PROJECT_KEY" \
  --sonar-python-coverage-report-paths=coverage.xml

TASK_ID="$(sed -n 's/^ceTaskId=//p' .sonar/report-task.txt)"
if [ -z "$TASK_ID" ]; then
  echo "ERROR: could not read ceTaskId from .sonar/report-task.txt" >&2
  exit 1
fi

echo "Waiting for analysis task $TASK_ID to complete..."
STATUS=""
for ((i = 0; i < MAX_WAIT; i++)); do
  STATUS="$(curl -s -u "$SONAR_TOKEN:" "$SONAR_HOST/api/ce/task?id=$TASK_ID" | jq -r '.task.status')"
  case "$STATUS" in
    SUCCESS) break ;;
    FAILED | CANCELED)
      echo "ERROR: analysis task ended with status $STATUS" >&2
      exit 1
      ;;
  esac
  sleep 2
done

if [ "$STATUS" != "SUCCESS" ]; then
  echo "ERROR: timed out waiting for analysis task" >&2
  exit 1
fi

curl -s -u "$SONAR_TOKEN:" \
  "$SONAR_HOST/api/issues/search?componentKeys=$PROJECT_KEY&resolved=false&ps=500" \
  | jq '[.issues[] | {file: .component, line: .line, message: .message, rule: .rule, severity: .severity, type: .type}]' \
  > sonar_issues.json

echo "Issues exported to sonar_issues.json"
