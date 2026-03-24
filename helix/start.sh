#!/bin/bash
# Start Helix PCEC server as sidecar
# Requires: npm install -g @helix-agent/core
echo "Starting Helix self-healing sidecar on :7842..."
npx @helix-agent/core serve --port 7842 --mode auto &
HELIX_PID=$!
echo "Helix PID: $HELIX_PID"
# Wait for server to be ready
for i in {1..10}; do
  curl -s http://localhost:7842/health > /dev/null && break
  sleep 1
done
echo "Helix ready. Run your MPP experiments normally."
echo "To stop: kill $HELIX_PID"
