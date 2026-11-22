@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: Construction Diary Creation Skill - Setup Script
:: ============================================================================
:: This script helps you set up the Construction Diary Creation skill and MCP server
:: ============================================================================

title Construction Diary Creation - Setup

echo.
echo ============================================================================
echo        CONSTRUCTION DIARY CREATION SKILL - SETUP WIZARD
echo ============================================================================
echo.
echo This script will help you set up the Construction Diary Creation skill.
echo.
echo PREREQUISITES (install these first if you haven't):
echo   1. Claude Desktop - https://claude.ai/download
echo   2. Python 3.11+ - https://www.python.org/downloads/
echo   3. OpenAI API key OR Azure OpenAI credentials (REQUIRED for transcription)
echo.
echo ============================================================================
echo.

pause

:: ============================================================================
:: Step 1: Check Python
:: ============================================================================
echo.
echo [Step 1/5] Checking Python installation...
echo ----------------------------------------------------------------------------

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python %PYTHON_VERSION% is too old: gaik needs Python 3.11 or later.
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)
echo [OK] Python %PYTHON_VERSION% found.

:: ============================================================================
:: Step 2: Install Python dependencies
:: ============================================================================
echo.
echo [Step 2/5] Installing Python dependencies...
echo ----------------------------------------------------------------------------
set "TRANSCRIPTION_MCP_PATH=%~dp0transcription-MCP"
set "VENV_DIR=%~dp0transcription-MCP\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
echo The transcriber gets its own virtual environment:
echo   %VENV_DIR%
echo Your own Python installation is not changed.
echo Installing into it: mcp==1.30.0, gaik[transcriber]==0.11.1, python-dotenv==1.2.4
echo This may take a few minutes...
echo.

if not exist "%VENV_PYTHON%" python -m venv "%VENV_DIR%"
if not exist "%VENV_PYTHON%" (
    echo [ERROR] Could not create the virtual environment in !VENV_DIR!.
    pause
    exit /b 1
)

"%VENV_PYTHON%" -m pip install mcp==1.30.0 "gaik[transcriber]==0.11.1" python-dotenv==1.2.4 --quiet

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    echo Please try running: "!VENV_PYTHON!" -m pip install mcp==1.30.0 "gaik[transcriber]==0.11.1" python-dotenv==1.2.4
    pause
    exit /b 1
)

echo [OK] Dependencies installed successfully.

:: ============================================================================
:: Step 3: Configure API Key (REQUIRED)
:: ============================================================================
echo.
echo [Step 3/5] Configuring API credentials for audio transcription...
echo ----------------------------------------------------------------------------
echo.
echo IMPORTANT: Audio transcription is REQUIRED for construction diary extraction.
echo You must provide an OpenAI or Azure OpenAI API key to use this skill.
echo.
echo Which API provider do you want to use?
echo.
echo   1. OpenAI (recommended)
echo   2. Azure OpenAI
echo.

set /p API_CHOICE="Enter your choice (1 or 2): "

if "%API_CHOICE%"=="1" (
    echo.
    echo You selected OpenAI.
    echo.
    echo Get your API key from: https://platform.openai.com/api-keys
    echo.
    set /p OPENAI_KEY="Enter your OpenAI API key: "

    if "!OPENAI_KEY!"=="" (
        echo [WARNING] No API key provided. Save it later as a user environment variable:
        echo   setx OPENAI_API_KEY "your-key"
        echo.
        echo NOTE: The skill will NOT work without an API key.
    ) else (
        setx OPENAI_API_KEY "!OPENAI_KEY!" >nul
        if !errorlevel! neq 0 (
            echo [ERROR] Could not save the key as a user environment variable.
            pause
            exit /b 1
        )
        echo [OK] The key is saved as your user environment variable OPENAI_API_KEY,
        echo      not in a file in this folder.
    )
    set "OPENAI_KEY="
    set API_TYPE=openai

) else if "%API_CHOICE%"=="2" (
    echo.
    echo You selected Azure OpenAI.
    echo.
    echo You'll need your Azure OpenAI credentials.
    echo.
    set /p AZURE_KEY="Enter your Azure API key: "
    set /p AZURE_ENDPOINT="Enter your Azure endpoint URL: "
    set /p AZURE_DEPLOYMENT="Enter your transcription deployment name, for example whisper or gpt-4o-transcribe: "

    if "!AZURE_KEY!"=="" (
        echo [WARNING] No API key provided. Save it later as a user environment variable:
        echo   setx AZURE_API_KEY "your-key"
        echo.
        echo NOTE: The skill will NOT work without an API key.
    ) else (
        setx AZURE_API_KEY "!AZURE_KEY!" >nul
        if !errorlevel! neq 0 (
            echo [ERROR] Could not save the key as a user environment variable.
            pause
            exit /b 1
        )
        echo [OK] The key is saved as your user environment variable AZURE_API_KEY,
        echo      not in a file in this folder. The endpoint and deployment go into
        echo      the Claude Desktop configuration.
    )
    set "AZURE_KEY="
    set API_TYPE=azure

) else (
    echo.
    echo [ERROR] Invalid choice. Please run the script again and select 1 or 2.
    pause
    exit /b 1
)


if exist "%TRANSCRIPTION_MCP_PATH%\.env" (
    echo.
    echo An older setup saved the API key in !TRANSCRIPTION_MCP_PATH!\.env.
    echo The transcriber now reads it from your user environment variables.
    set /p DELETE_ENV="Delete that file now? (Y/N): "
    if /i "!DELETE_ENV!"=="Y" (
        del "!TRANSCRIPTION_MCP_PATH!\.env"
        echo [OK] Deleted !TRANSCRIPTION_MCP_PATH!\.env
    ) else (
        echo [INFO] Kept it. The transcriber still reads it and warns in its log.
    )
)

:: ============================================================================
:: Step 4: Check FFmpeg (optional)
:: ============================================================================
echo.
echo [Step 4/5] Checking FFmpeg (optional, for large audio files)...
echo ----------------------------------------------------------------------------

ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] FFmpeg not found.
    echo.
    echo FFmpeg is optional but needed for audio files larger than 25 MB or longer than 20 minutes.
    echo Download from: https://ffmpeg.org/download.html
    echo.
) else (
    echo [OK] FFmpeg found.
)

:: ============================================================================
:: Step 5: Generate Claude Desktop Configuration
:: ============================================================================
echo.
echo [Step 5/5] Generating Claude Desktop configuration...
echo ----------------------------------------------------------------------------
echo.

:: Get the script directory and normalize the path for JSON
set "SCRIPT_DIR=%~dp0"
set "SERVER_PATH=%SCRIPT_DIR%transcription-MCP\server.py"

:: Convert backslashes to double backslashes for JSON
set "SERVER_PATH_JSON=%SERVER_PATH:\=\\%"

:: Remove trailing backslash if present
if "%SERVER_PATH_JSON:~-2%"=="\\" set "SERVER_PATH_JSON=%SERVER_PATH_JSON:~0,-2%"

:: Create the config file content
set "CONFIG_FILE=%SCRIPT_DIR%claude_desktop_config.json"


:: The folder Claude may work on. The transcriber transcribes audio and video files
:: only there and in its subfolders.
echo Which folder holds the recordings and materials Claude may work on?
echo Claude's tools are limited to this folder and its subfolders. A whole drive
echo (such as C:\) or your whole user folder is not accepted.
set "WORK_FOLDER=%USERPROFILE%\Documents\GAIK"
set /p WORK_FOLDER="Folder (Enter for %USERPROFILE%\Documents\GAIK): "
set "WORK_FOLDER=%WORK_FOLDER:"=%"
if "%WORK_FOLDER:~-1%"=="\" if not "%WORK_FOLDER:~-2%"==":\" set "WORK_FOLDER=%WORK_FOLDER:~0,-1%"
:: An absolute path goes into the configuration; the transcriber then checks the folder
:: as it will at run time.
for %%I in ("%WORK_FOLDER%") do set "WORK_FOLDER=%%~fI"
:: After that only a drive root such as C:\ still ends with a backslash. It is refused
:: here, because "C:\" would reach the transcriber as C: followed by a quote.
if "%WORK_FOLDER:~-1%"=="\" (
    echo [ERROR] "!WORK_FOLDER!" is a whole drive. Choose a folder on it,
    echo         for example %USERPROFILE%\Documents\GAIK.
    pause
    exit /b 1
)
if not exist "%WORK_FOLDER%\" mkdir "%WORK_FOLDER%"
"%VENV_PYTHON%" "%SERVER_PATH%" --check-folder "%WORK_FOLDER%" >nul
if %errorlevel% neq 0 (
    echo [ERROR] "!WORK_FOLDER!" is not a folder Claude can be limited to.
    echo         It must not be your whole user folder or hold this setup folder.
    echo         Choose a folder of its own, for example %USERPROFILE%\Documents\GAIK.
    pause
    exit /b 1
)
echo [OK] Claude's tools will work in "%WORK_FOLDER%"
set "WORK_FOLDER_JSON=%WORK_FOLDER:\=\\%"
if "%WORK_FOLDER_JSON:~-2%"=="\\" set "WORK_FOLDER_JSON=%WORK_FOLDER_JSON:~0,-2%"
set "VENV_PYTHON_JSON=%VENV_PYTHON:\=\\%"

(
echo {
echo   "mcpServers": {
echo     "gaik-transcriber": {
echo       "command": "!VENV_PYTHON_JSON!",
echo       "args": ["!SERVER_PATH_JSON!", "--folder", "!WORK_FOLDER_JSON!"],
if "!API_TYPE!"=="azure" echo       "env": {"OPENAI_API_TYPE": "azure", "AZURE_ENDPOINT": "!AZURE_ENDPOINT!", "AZURE_TRANSCRIPTION_MODEL": "!AZURE_DEPLOYMENT!"},
if "!API_TYPE!"=="openai" echo       "env": {"OPENAI_API_TYPE": "openai"},
echo       "timeout": 600000
echo     }
echo   }
echo }
) > "%CONFIG_FILE%"

echo [OK] Configuration file generated.

:: ============================================================================
:: Bonus: Create Skill ZIP file
:: ============================================================================
echo.
echo [Bonus] Creating skill ZIP file...
echo ----------------------------------------------------------------------------

:: Check if PowerShell can create zip
powershell -Command "Compress-Archive -Path '%SCRIPT_DIR%SKILL.md' -DestinationPath '%SCRIPT_DIR%construction-diary-creation.zip' -Force" >nul 2>&1

if %errorlevel% equ 0 (
    echo [OK] Created construction-diary-creation.zip
) else (
    echo [INFO] Could not create ZIP automatically.
    echo       Please manually zip SKILL.md.
)

:: ============================================================================
:: FINAL INSTRUCTIONS
:: ============================================================================
echo.
echo ============================================================================
echo                         SETUP COMPLETE
echo ============================================================================
echo.
echo NEXT STEPS - Please follow these instructions carefully:
echo.
echo ----------------------------------------------------------------------------
echo STEP A: Copy the MCP configuration to Claude Desktop
echo ----------------------------------------------------------------------------
echo.
echo    1. Open this file in Notepad:
echo       %APPDATA%\Claude\claude_desktop_config.json
echo.
echo    2. If it is missing or empty, paste the ENTIRE content of:
echo       %CONFIG_FILE%
echo.
echo    3. Otherwise add only the gaik-transcriber entry to its mcpServers section
echo       and keep everything else. Then SAVE.
echo.
echo    TIP: Press Win+R, paste the path above, and press Enter to open it.
echo.
echo ----------------------------------------------------------------------------
echo STEP B: Restart Claude Desktop
echo ----------------------------------------------------------------------------
echo.
echo    1. Close Claude Desktop completely (check the system tray)
echo    2. Open Task Manager and end any "Claude" processes
echo    3. Start Claude Desktop again
echo.
echo ----------------------------------------------------------------------------
echo STEP C: Install the Skill in Claude Desktop
echo ----------------------------------------------------------------------------
echo.
echo    1. Open Claude Desktop
echo    2. Go to Customize then Skills
echo    3. Click Add then Upload skill
echo    4. Upload: %SCRIPT_DIR%construction-diary-creation.zip
echo.
echo ----------------------------------------------------------------------------
echo STEP D: Test the Setup
echo ----------------------------------------------------------------------------
echo.
echo    In Claude Desktop, try:
echo    "Process construction diary from C:\path\to\your\audio-file.mp3"
echo.
echo    Example with sample data:
echo    Download a sample from https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/no-code-assets/samples/construction-diary-creation
echo    and try: "Process construction diary from C:\path\to\downloads\fin-example-1.mp3"
echo.
echo ============================================================================
echo.
echo Configuration file saved to:
echo    %CONFIG_FILE%
echo.
echo Open it now to copy the content? (Y/N)
set /p OPEN_CONFIG="Your choice: "

if /i "%OPEN_CONFIG%"=="Y" (
    notepad "%CONFIG_FILE%"
)

echo.
echo Also open the Claude Desktop config location? (Y/N)
set /p OPEN_CLAUDE="Your choice: "

if /i "%OPEN_CLAUDE%"=="Y" (
    :: Try to open the Claude config directory
    if exist "%APPDATA%\Claude\" (
        explorer "%APPDATA%\Claude\"
    ) else (
        echo.
        echo Claude config folder not found at %APPDATA%\Claude\
        echo Please create it manually or install Claude Desktop first.
    )
)

echo.
echo ============================================================================
echo Setup script finished. Thank you for using Construction Diary Creation.
echo ============================================================================
echo.

pause
