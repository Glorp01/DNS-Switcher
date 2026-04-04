@echo off
setlocal
cd /d "%~dp0"
pyw "%~dp0dns_switcher.pyw"
if errorlevel 1 pythonw "%~dp0dns_switcher.pyw"
