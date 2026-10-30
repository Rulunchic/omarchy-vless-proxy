#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check python3
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ Ошибка: python3 не установлен. Пожалуйста, установите python3."
    exit 1
fi

chmod +x "$DIR/setup.py" 2>/dev/null || true
chmod +x "$DIR/core/proxy.sh" 2>/dev/null || true
chmod +x "$DIR/core/sysproxy.sh" 2>/dev/null || true
chmod +x "$DIR/bin/"* 2>/dev/null || true

if [ -n "$1" ]; then
    python3 "$DIR/setup.py" --subscription "$1"
else
    python3 "$DIR/setup.py"
fi
