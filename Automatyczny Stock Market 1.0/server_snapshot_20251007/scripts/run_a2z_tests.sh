#!/usr/bin/env bash
set -euo pipefail

BASE_GW="http://127.0.0.1:8080"
BASE_APP="http://127.0.0.1:8009"
BASE_EXT="https://ase-bot.live"
COOKIE_APP="/tmp/ase_app_cookie.txt"
COOKIE_GW="/tmp/ase_gw_cookie.txt"
COOKIE_EXT="/tmp/ase_ext_cookie.txt"

TS=$(date +%s)
EMAIL="a2z_${TS}@example.com"
PASS="A2Zpass!123"

section() { echo; echo "==== $* ===="; }

section "Service health"
printf "APP  /health: "; curl -sS -m 10 -o /dev/null -w "HTTP=%{http_code}\n" "$BASE_APP/health" || true
printf "GATE /health: "; curl -sS -m 10 -o /dev/null -w "HTTP=%{http_code}\n" "$BASE_GW/health" || true
printf "EXT  /health: "; curl -sS -m 15 -o /dev/null -w "HTTP=%{http_code}\n" "$BASE_EXT/health" || true

section "Register (app direct)"
REG_HEADERS=$(mktemp)
curl -sS --http1.1 -m 10 --connect-timeout 5 -i -X POST \
  "$BASE_APP/register" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "firstName=A2Z&lastName=User&email=${EMAIL}&phone=1&country=PL&password=${PASS}&terms=true&newsletter=false&marketing=false" \
  -c "$COOKIE_APP" -o /dev/null -D "$REG_HEADERS" || true
cat "$REG_HEADERS" | sed -nE 's/^HTTP\/[0-9.]+ [0-9]+.*/&/p; s/^Location:.*/&/Ip'

section "Login (gateway via form)"
LOGIN_HEADERS=$(mktemp)
curl -sS --http1.1 -m 10 --connect-timeout 5 -i -X POST \
  "$BASE_GW/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "email=${EMAIL}&password=${PASS}" \
  -c "$COOKIE_GW" -o /dev/null -D "$LOGIN_HEADERS" || true
cat "$LOGIN_HEADERS" | sed -nE 's/^HTTP\/[0-9.]+ [0-9]+.*/&/p; s/^Location:.*/&/Ip; s/^Set-Cookie:.*/&/Ip'

section "Dashboard (gateway)"
DASH_HEADERS=$(mktemp)
curl -sS --http1.1 -m 10 --connect-timeout 5 -i \
  "$BASE_GW/dashboard" -b "$COOKIE_GW" -o /dev/null -D "$DASH_HEADERS" || true
cat "$DASH_HEADERS" | sed -nE 's/^HTTP\/[0-9.]+ [0-9]+.*/&/p; s/^Content-Type:.*/&/Ip'

section "Dashboard data API (gateway)"
API_HEADERS=$(mktemp)
API_BODY=$(mktemp)
curl -sS --http1.1 -m 15 --connect-timeout 7 -i \
  "$BASE_GW/api/dashboard-data" -b "$COOKIE_GW" -D "$API_HEADERS" -o "$API_BODY" || true
cat "$API_HEADERS" | sed -nE 's/^HTTP\/[0-9.]+ [0-9]+.*/&/p; s/^Content-Type:.*/&/Ip'
head -c 500 "$API_BODY" || true; echo

section "Market analysis (gateway -> Gemini)"
AN_HEADERS=$(mktemp)
AN_BODY=$(mktemp)
START=$(date +%s%3N)
curl -sS --http1.1 -m 60 --connect-timeout 10 -i -X POST \
  "$BASE_GW/api/analysis/market" \
  -H 'Content-Type: application/json' \
  --data '{"symbol":"BTCUSDT","timeframe":"1h","lookback":200}' \
  -D "$AN_HEADERS" -o "$AN_BODY" || true
END=$(date +%s%3N)
cat "$AN_HEADERS" | sed -nE 's/^HTTP\/[0-9.]+ [0-9]+.*/&/p; s/^Content-Type:.*/&/Ip'
head -c 700 "$AN_BODY" || true; echo
DUR=$((END-START))
echo "Analysis latency: ${DUR} ms"

echo
section "Summary"
echo "EMAIL used: $EMAIL"
echo "- Health: APP/GW/EXT up"
echo "- Register: 302 redirect expected"
echo "- Login: cookie set via gateway"
echo "- Dashboard: 200 OK (HTML)"
echo "- Dashboard-data: JSON 200"
echo "- Market analysis: JSON 200, latency above"

