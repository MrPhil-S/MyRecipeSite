@echo off
echo Connecting to Raspberry Pi...
plink -ssh pi@192.168.1.13 -pw %pipw% "echo Running remote command...; cd /var/www/piapp && source  /var/www/piapp/venv/bin/activate && echo Activated virtual environment...; export FLASK_APP=app.py && echo Set FLASK_APP environment variable...; nohup flask run --host=0.0.0.0 &"
echo Completed remote command.

