@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "SCRIPT=%~dp0detect_and_crop.py"

:: ============================================================
::  VERIFICACOES
:: ============================================================
cls
echo.
echo  🎬 fnkRecortador — Corte Automatico de Videos
echo  ════════════════════════════════════════════════════════════
echo.

python --version >nul 2>&1
if errorlevel 1 ( echo ERRO: Python nao encontrado! & pause & exit /b )
python -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 ( pip install opencv-python-headless numpy pytesseract Pillow )
ffmpeg -version >nul 2>&1
if errorlevel 1 ( echo ERRO: ffmpeg nao encontrado! & pause & exit /b )

set "BLUR=--sem-blur"
for %%P in ("C:\Program Files\Tesseract-OCR\tesseract.exe" "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe") do (
    if exist %%P set "BLUR="
)
where tesseract >nul 2>&1
if not errorlevel 1 set "BLUR="

:: ============================================================
::  SELECIONA PASTA COM O MOUSE
:: ============================================================
:SELECIONAR
cls
echo.
echo  ════════════════════════════════════════════════════════════
echo  🎬 fnkRecortador — Corte Automatico de Videos
echo  ════════════════════════════════════════════════════════════
echo.
echo  Selecione a pasta com os videos a processar.
echo.

for /f "delims=" %%A in ('python -c "import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',1); p=filedialog.askdirectory(title='Selecione a pasta com os videos',initialdir='D:\\fnkSocialMidia\\fnkPerfis'); print(p if p else '')"') do set "PASTA=%%A"

if "!PASTA!"=="" ( echo  Cancelado. & pause & exit /b )
set "PASTA=!PASTA:/=\!"

:: ============================================================
::  SELECIONA O PERFIL DE DESTINO (fnkPerfis\Nicho\Perfil)
:: ============================================================
echo.
echo  Agora selecione a pasta do PERFIL de destino
echo  (ex: fnkPerfis\Pets\MAXTHEGOLDENBR).
echo.

for /f "delims=" %%A in ('python -c "import tkinter as tk; from tkinter import filedialog; root=tk.Tk(); root.withdraw(); root.wm_attributes('-topmost',1); p=filedialog.askdirectory(title='Selecione o PERFIL de destino (fnkPerfis\\Nicho\\Perfil)',initialdir='D:\\fnkSocialMidia\\fnkPerfis'); print(p if p else '')"') do set "DESTINO=%%A"

if "!DESTINO!"=="" ( echo  Cancelado. & pause & exit /b )
set "DESTINO=!DESTINO:/=\!"

:: Conta videos
set "TOTAL=0"
for %%F in ("!PASTA!\*.mp4" "!PASTA!\*.mov" "!PASTA!\*.avi" "!PASTA!\*.mkv" "!PASTA!\*.m4v" "!PASTA!\*.webm") do (
    if exist "%%F" set /a TOTAL+=1
)

cls
echo.
echo  ════════════════════════════════════════════════════════════
echo  Pasta   : !PASTA!
echo  Videos  : !TOTAL!
echo  Perfil  : !DESTINO!
echo.
echo  Saida   : !DESTINO!\VIDEOS RECORTADOS\^<perfil^>\1por1
echo            !DESTINO!\VIDEOS RECORTADOS\^<perfil^>\4por5
echo            !DESTINO!\VIDEOS RECORTADOS\^<perfil^>\9por16
echo  ════════════════════════════════════════════════════════════
echo.

if !TOTAL!==0 (
    echo  Nenhum video encontrado nesta pasta.
    echo.
    echo   1 - Selecionar outra pasta
    echo   0 - Sair
    echo.
    set /p "R=  Escolha: "
    if "!R!"=="1" goto SELECIONAR
    exit /b
)

echo   1 - Processar agora
echo   2 - Dry-run (testar sem executar)
echo   3 - Selecionar outra pasta
echo   0 - Sair
echo.
set /p "R=  Escolha: "
if "!R!"=="0" exit /b
if "!R!"=="3" goto SELECIONAR
if "!R!"=="1" set "DRY=" & goto EXECUTAR
if "!R!"=="2" set "DRY=--dry-run" & goto EXECUTAR
goto SELECIONAR

:EXECUTAR
cls
echo.
echo  Processando: !PASTA!
echo.
python "!SCRIPT!" --pasta "!PASTA!" --destino "!DESTINO!" !DRY! !BLUR!

echo.
echo  ════════════════════════════════════════════════════════════
echo  Concluido! Os videos cortados estao em:
echo  !DESTINO!\VIDEOS RECORTADOS\^<perfil^>\1por1
echo  !DESTINO!\VIDEOS RECORTADOS\^<perfil^>\4por5
echo  !DESTINO!\VIDEOS RECORTADOS\^<perfil^>\9por16
echo  ════════════════════════════════════════════════════════════
echo.
echo   1 - Processar outra pasta
echo   0 - Sair
echo.
set /p "R=  Escolha: "
if "!R!"=="1" goto SELECIONAR
exit /b
