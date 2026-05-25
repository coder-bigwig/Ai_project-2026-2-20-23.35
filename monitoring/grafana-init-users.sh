#!/bin/sh
set -eu

GRAFANA_URL="${GRAFANA_URL:-http://grafana:3000}"
ADMIN_LOGIN="${GRAFANA_ADMIN_LOGIN:-fit_admin}"
ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-fit350506}"
TEACHER_PASSWORD="${GRAFANA_TEACHER_PASSWORD:-fit350506}"
TEACHER_LOGINS="${GRAFANA_TEACHER_LOGINS:-teacher_001 teacher_002 teacher_003 teacher_004 teacher_005}"

api() {
  method="$1"
  path="$2"
  data="${3:-}"
  if [ -n "$data" ]; then
    curl -fsS -u "$AUTH" -H "Content-Type: application/json" -X "$method" -d "$data" "$GRAFANA_URL$path"
  else
    curl -fsS -u "$AUTH" -H "Content-Type: application/json" -X "$method" "$GRAFANA_URL$path"
  fi
}

json_user() {
  login="$1"
  password="$2"
  role="$3"
  printf '{"name":"%s","email":"%s@local","login":"%s","password":"%s","OrgId":1,"role":"%s"}' \
    "$login" "$login" "$login" "$password" "$role"
}

user_id() {
  login="$1"
  api GET "/api/users/lookup?loginOrEmail=$login" 2>/dev/null | sed -n 's/.*"id":[ ]*\([0-9][0-9]*\).*/\1/p'
}

ensure_user() {
  login="$1"
  password="$2"
  role="$3"
  is_admin="$4"

  id="$(user_id "$login" || true)"
  if [ -z "$id" ]; then
    api POST /api/admin/users "$(json_user "$login" "$password" "$role")" >/dev/null
    id="$(user_id "$login")"
  fi

  api PATCH "/api/org/users/$id" "{\"role\":\"$role\"}" >/dev/null
  api PUT "/api/admin/users/$id/permissions" "{\"isGrafanaAdmin\":$is_admin}" >/dev/null
}

for _ in $(seq 1 60); do
  if curl -fsS "$GRAFANA_URL/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

AUTH=""
for candidate in "$ADMIN_LOGIN" admin; do
  if curl -fsS -u "$candidate:$ADMIN_PASSWORD" "$GRAFANA_URL/api/org" >/dev/null 2>&1; then
    AUTH="$candidate:$ADMIN_PASSWORD"
    break
  fi
done

if [ -z "$AUTH" ]; then
  echo "Could not authenticate to Grafana with $ADMIN_LOGIN or admin." >&2
  exit 1
fi

ensure_user "$ADMIN_LOGIN" "$ADMIN_PASSWORD" Admin true

AUTH="$ADMIN_LOGIN:$ADMIN_PASSWORD"
if [ "$ADMIN_LOGIN" != "admin" ]; then
  legacy_admin_id="$(user_id admin || true)"
  if [ -n "$legacy_admin_id" ]; then
    api POST "/api/admin/users/$legacy_admin_id/disable" >/dev/null 2>&1 || true
  fi
fi

for teacher in $TEACHER_LOGINS; do
  ensure_user "$teacher" "$TEACHER_PASSWORD" Viewer false
done

echo "Grafana users are ready."
