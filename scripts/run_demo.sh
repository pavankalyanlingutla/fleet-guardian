#!/usr/bin/env bash
# run_demo.sh
# Starts the simulated device fleet + control API, then triggers one
# closed-loop automation cycle against them and prints the result.

set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Installing dependencies =="
pip install -q -r requirements.txt

echo "== Starting device fleet + control API on :7000 =="
python3 -m app.api &
API_PID=$!
trap "kill $API_PID" EXIT

sleep 1

echo "== Device status before automation run =="
curl -s http://127.0.0.1:7000/devices | python3 -m json.tool

echo "== Triggering automation cycle =="
curl -s -X POST http://127.0.0.1:7000/automation/run | python3 -m json.tool

echo "== Run history =="
curl -s http://127.0.0.1:7000/automation/history | python3 -m json.tool

wait $API_PID
