#!/usr/bin/env bash
set -euo pipefail

BASE_GW="http://127.0.0.1:8080"
COOKIE_GW="/tmp/ase_bench_cookie.txt"

email_for_auth="bench_$(date +%s)@example.com"
password_for_auth="BenchPass!123"

measure() {
  local name="$1"; shift
  local cmd=("$@")
  local start end dur
  start=$(date +%s%3N)
  if "${cmd[@]}" >/dev/null 2>&1; then
    end=$(date +%s%3N)
    dur=$((end-start))
    echo "$name: ${dur} ms"
  else
    echo "$name: FAILED"
  fi
}

# Ensure we have a session (register then login through form on gateway)
echo "== Setup session =="
curl -sS --http1.1 -m 10 --connect-timeout 5 -X POST \
  "$BASE_GW/register" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "firstName=Bench&lastName=User&email=${email_for_auth}&phone=1&country=PL&password=${password_for_auth}&terms=true" \
  -c "$COOKIE_GW" -o /dev/null || true
curl -sS --http1.1 -m 10 --connect-timeout 5 -X POST \
  "$BASE_GW/login" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "email=${email_for_auth}&password=${password_for_auth}" \
  -b "$COOKIE_GW" -c "$COOKIE_GW" -o /dev/null || true

# Warmup
curl -sS --http1.1 -m 10 "$BASE_GW/health" -o /dev/null || true
curl -sS --http1.1 -m 10 "$BASE_GW/api/dashboard-data" -b "$COOKIE_GW" -o /dev/null || true

# Measurements
runs=5
health_times=()
dash_times=()
analysis_times=()

for i in $(seq 1 $runs); do
  t=$(date +%s%3N); measure "health#$i" curl -sS --http1.1 -m 10 "$BASE_GW/health" -o /dev/null | tee /tmp/bench_health.txt; 
  h=$(tail -n1 /tmp/bench_health.txt | awk '{print $2}')
  health_times+=("${h}")

  measure "dashboard-data#$i" curl -sS --http1.1 -m 15 "$BASE_GW/api/dashboard-data" -b "$COOKIE_GW" -o /dev/null | tee /tmp/bench_dash.txt
  d=$(tail -n1 /tmp/bench_dash.txt | awk '{print $2}')
  dash_times+=("${d}")

  measure "analysis#$i" curl -sS --http1.1 -m 60 -X POST "$BASE_GW/api/analysis/market" -H 'Content-Type: application/json' --data '{"symbol":"BTCUSDT","timeframe":"1h","lookback":200}' -o /dev/null | tee /tmp/bench_an.txt
  a=$(tail -n1 /tmp/bench_an.txt | awk '{print $2}')
  analysis_times+=("${a}")
done

avg() {
  arr=("$@"); total=0; count=0; for v in "${arr[@]}"; do [[ -n "$v" ]] && total=$((total+v)) && count=$((count+1)); done; 
  if [[ $count -gt 0 ]]; then echo $((total/count)); else echo 0; fi
}

minv() { arr=("$@"); min=; for v in "${arr[@]}"; do if [[ -z "$min" || ( -n "$v" && v -lt min ) ]]; then min=$v; fi; done; echo ${min:-0}; }
maxv() { arr=("$@"); max=0; for v in "${arr[@]}"; do if [[ -n "$v" && v -gt max ]]; then max=$v; fi; done; echo $max; }

echo
echo "== Benchmark summary (ms) =="
echo "health:   avg=$(avg "${health_times[@]}") min=$(minv "${health_times[@]}") max=$(maxv "${health_times[@]}")"
echo "dashboard:avg=$(avg "${dash_times[@]}")   min=$(minv "${dash_times[@]}")   max=$(maxv "${dash_times[@]}")"
echo "analysis: avg=$(avg "${analysis_times[@]}") min=$(minv "${analysis_times[@]}") max=$(maxv "${analysis_times[@]}")"

