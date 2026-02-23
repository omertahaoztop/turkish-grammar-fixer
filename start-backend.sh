#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV" ]; then
  echo "Sanal ortam oluşturuluyor..."
  uv venv --python 3.13 "$VENV"
fi

echo "Bağımlılıklar yükleniyor..."
uv pip install -r "$SCRIPT_DIR/backend/requirements.txt" --quiet

echo "NLTK punkt_tab indiriliyor (sadece ilk seferde)..."
"$VENV/bin/python" -c "import nltk; nltk.download('punkt_tab', quiet=True)"

echo ""
echo "Backend başlatılıyor: http://127.0.0.1:5858"
echo "Durdurmak için Ctrl+C"
echo ""

cd "$SCRIPT_DIR/backend"
"$VENV/bin/python" app.py
