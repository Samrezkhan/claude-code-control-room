@echo off
rem Start the Control Room in the background and open it. Safe to run any number of times.
python "%~dp0server.py" --detach --open
