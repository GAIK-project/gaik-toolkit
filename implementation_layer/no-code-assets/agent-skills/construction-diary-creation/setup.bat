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
echo   2. Python 3.8+ - https://www.python.org/downloads/
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
    echo Please install Python 3.8+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found.

:: ============================================================================
:: Step 2: Install Python dependencies
:: ============================================================================
echo.
echo [Step 2/5] Installing Python dependencies...
echo ----------------------------------------------------------------------------
echo Installing: fastmcp, gaik[transcriber], python-dotenv
echo This may take a few minutes...
echo.

pip install fastmcp "gaik[transcriber]" python-dotenv --quiet

if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    echo Please try running: pip install fastmcp "gaik[transcriber]" python-dotenv
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

set "TRANSCRIPTION_MCP_PATH=%~dp0transcription-MCP"

if "%API_CHOICE%"=="1" (
    echo.
    echo You selected OpenAI.
    echo.
    echo Get your API key from: https://platform.openai.com/api-keys
    echo.
    set /p OPENAI_KEY="Enter your OpenAI API key: "

    if "!OPENAI_KEY!"=="" (
        echo [WARNING] No API key provided. You can add it later to:
        echo %TRANSCRIPTION_MCP_PATH%\.env
        echo.
        echo NOTE: The skill will NOT work without an API key.
    ) else (
        echo.
        echo Creating .env file...
        (
            echo # OpenAI Configuration
            echo OPENAI_API_KEY=!OPENAI_KEY!
            echo OPENAI_API_TYPE=openai
        ) > "%TRANSCRIPTION_MCP_PATH%\.env"
        echo [OK] .env file created at %TRANSCRIPTION_MCP_PATH%\.env
    )
    set API_TYPE=openai

) else if "%API_CHOICE%"=="2" (
    echo.
    echo You selected Azure OpenAI.
    echo.
    echo You'll need your Azure OpenAI credentials.
    echo.
    set /p AZURE_KEY="Enter your Azure API key: "
    set /p AZURE_ENDPOINT="Enter your Azure endpoint URL: "
    set /p AZURE_DEPLOYMENT="Enter your Whisper deployment name: "

    if "!AZURE_KEY!"=="" (
        echo [WARNING] No API key provided. You can add it later to:
        echo %TRANSCRIPTION_MCP_PATH%\.env
        echo.
        echo NOTE: The skill will NOT work without an API key.
    ) else (
        echo.
        echo Creating .env file...
        (
            echo # Azure OpenAI Configuration
            echo AZURE_API_KEY=!AZURE_KEY!
            echo AZURE_ENDPOINT=!AZURE_ENDPOINT!
            echo AZURE_DEPLOYMENT=!AZURE_DEPLOYMENT!
            echo OPENAI_API_TYPE=azure
        ) > "%TRANSCRIPTION_MCP_PATH%\.env"
        echo [OK] .env file created at %TRANSCRIPTION_MCP_PATH%\.env
    )
    set API_TYPE=azure

) else (
    echo.
    echo [ERROR] Invalid choice. Please run the script again and select 1 or 2.
    pause
    exit /b 1
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
    echo FFmpeg is optional but recommended for audio files larger than 25MB.
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

(
echo {
echo   "mcpServers": {
echo     "gaik-transcriber": {
echo       "command": "python",
echo       "args": ["%SERVER_PATH_JSON%"],
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
powershell -Command "Compress-Archive -Path '%SCRIPT_DIR%construction-diary-creation\*' -DestinationPath '%SCRIPT_DIR%construction-diary-creation.zip' -Force" >nul 2>&1

if %errorlevel% equ 0 (
    echo [OK] Created construction-diary-creation.zip
) else (
    echo [INFO] Could not create ZIP automatically.
    echo       Please manually zip the 'construction-diary-creation' folder.
)

:: ============================================================================
:: FINAL INSTRUCTIONS
:: ============================================================================
echo.
echo ============================================================================
echo                         SETUP COMPLETE!
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
echo    2. If the file doesn't exist, create it.
echo.
echo    3. Copy the ENTIRE content from:
echo       %CONFIG_FILE%
echo.
echo    4. Paste it into claude_desktop_config.json and SAVE.
echo.
echo    TIP: Press Win+R, paste the path above, and press Enter to open it.
echo.
echo ----------------------------------------------------------------------------
echo STEP B: Restart Claude Desktop
echo ----------------------------------------------------------------------------
echo.
echo    1. Close Claude Desktop completely (check system tray!)
echo    2. Open Task Manager and end any "Claude" processes
echo    3. Start Claude Desktop again
echo.
echo ----------------------------------------------------------------------------
echo STEP C: Install the Skill in Claude Desktop
echo ----------------------------------------------------------------------------
echo.
echo    1. Open Claude Desktop
echo    2. Go to Settings (gear icon) then Capabilities
echo    3. Click "+ Add"
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
echo    "Process construction diary from %SCRIPT_DIR%data\fin-example-1.mp3"
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
echo Setup script finished. Thank you for using Construction Diary Creation!
echo ============================================================================
echo.

pause
