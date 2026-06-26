@echo off
setlocal

REM ======================================
REM BRD Parser — Claude Sonnet 4.6
REM ======================================

if "%~1"=="" (
    echo Usage: %~nx0 ^<BRD_FILE_PATH^>
    exit /b 1
)

set "BRD_PATH=%~1"
if not exist "%BRD_PATH%" (
    echo ERROR: File not found - %BRD_PATH%
    exit /b 1
)

set "TMP_TXT=%TEMP%\brd_extracted.txt"
set "LOG_FILE=%~dp0brd_parser.log"

echo ======================================
echo BRD Parser Execution Started
echo File: %BRD_PATH%
echo ======================================

echo Extracting text from .docx...
python -c "import docx; doc=docx.Document(r'%BRD_PATH%'); print('\n'.join(p.text for p in doc.paragraphs if p.text.strip()))" > "%TMP_TXT%"
if %errorlevel% neq 0 (
    echo ERROR: Failed to extract text from .docx. Is python-docx installed?
    exit /b 1
)

echo Sending to Claude Sonnet 4.6...
python -c "import sys; brd=open(r'%TMP_TXT%',encoding='utf-8').read(); sys.stdout.write('Parse this BRD as a data modeler. Return ONLY a JSON object with two arrays: entities (each with: name, type from [dimension,fact,reference,bridge], attributes list of strings, description string) and relationships (each with: source entity name, target entity name, type from [MANY_TO_ONE,ONE_TO_MANY,ONE_TO_ONE,MANY_TO_MANY], name string). dimension=descriptive/classification such as Product/Customer/Location/Calendar. fact=measurable/transactional such as Sales/Orders/Profit/Inventory. reference=small lookup or code table. bridge=resolves many-to-many. Return JSON only, no explanation, no markdown.\n\nBRD:\n' + brd)" | claude --model claude-sonnet-4-6 -p > "%LOG_FILE%" 2>&1

if %errorlevel% neq 0 (
    echo ERROR: Claude processing failed. Check log: %LOG_FILE%
    del "%TMP_TXT%" 2>nul
    exit /b 1
)

echo.
echo ======================================
echo SUCCESS: BRD parsed successfully
echo ======================================
type "%LOG_FILE%"
echo.
echo Log saved to: %LOG_FILE%

del "%TMP_TXT%" 2>nul
endlocal
