@echo off
REM Windows: double-click to pick a crash scenario and play it in esmini (daylight view).
cd /d "%~dp0.."
set ESMINI=tools\esmini-demo\bin\esmini.exe
set MODELS=tools\esmini-demo\resources\models
:menu
echo.
echo === crash2sim scenarios in esmini ===
echo   1) CIREN_8392  Head-on, REAL case
echo   2) CISS_A1     Rear-end, distracted driver
echo   3) CISS_A2     Left turn at city intersection
echo   4) SGO_B1      Rear-end into stopped automated vehicle
echo   5) SGO_B2      Left turn vs automated vehicle
echo   q) quit
set /p c=Pick 1-5: 
if "%c%"=="q" exit /b
if "%c%"=="1" set F=CIREN_8392
if "%c%"=="2" set F=CISS_A1
if "%c%"=="3" set F=CISS_A2
if "%c%"=="4" set F=SGO_B1
if "%c%"=="5" set F=SGO_B2
%ESMINI% --window 60 60 1280 720 --path %MODELS% --osc scenarios\demo\%F%.xosc --hide_route_waypoints --info_text 1
goto menu
