@echo off
cd /d "%~dp0"
if not exist "%~dp0logs" mkdir "%~dp0logs"
echo ==== V20 Qwen Chat session %date% %time% ====>> "%~dp0logs\v20-qwen-chat.log"
uv run --locked vesper-agent --runtime ollama-qwen chat --role v20-development --model qwen:64k --workspace "TUI testing" --skill knowledge/skills/v20-engineering.md --allow-write 2>> "%~dp0logs\v20-qwen-chat.log"
set "exit_code=%ERRORLEVEL%"
echo ==== V20 Qwen Chat exited with code %exit_code% ====>> "%~dp0logs\v20-qwen-chat.log"
if not "%exit_code%"=="0" (
  echo V20 Qwen Chat exited with code %exit_code%.
  echo Log: %~dp0logs\v20-qwen-chat.log
  pause
)
exit /b %exit_code%
