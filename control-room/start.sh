#!/bin/sh
# Start the Control Room in the background and open it. Safe to run any number of times.
python3 "$(dirname "$0")/server.py" --detach --open
