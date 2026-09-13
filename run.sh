#!/bin/bash
# Start the CNB Stock Finder at http://127.0.0.1:8765/
cd "$(dirname "$0")"
exec python3 server.py "${1:-8765}" --open
