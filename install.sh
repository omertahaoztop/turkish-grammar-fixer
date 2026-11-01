#!/usr/bin/env bash
# tdk'yi kurar (venv, ~/.local/bin/tdk, systemd --user birimleri, Hyprland kısayolu); --train eğitim ortamını da kurar.
set -euo pipefail
cd "$(dirname "$0")"
d=~/.local/share/tdk

deps=(llama-cpp ggml ggml-vulkan wl-clipboard wtype libnotify gtk4-layer-shell libadwaita python-gobject)
pacman -T "${deps[@]}" >/dev/null || sudo pacman -S --needed --noconfirm "${deps[@]}"
uv venv --allow-existing --python /usr/bin/python3 --system-site-packages
uv sync --quiet
mkdir -p ~/.local/bin ~/.config/systemd/user ~/.config/tdk "$d/models"
ln -sf "$PWD/.venv/bin/tdk" ~/.local/bin/tdk
cp systemd/*.service systemd/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload

ram=$(awk '/MemTotal/ {print int($2 / 1048576)}' /proc/meminfo)
# Model ~7 GB ister; küçük RAM'de masaüstünü boğmamak için yalnız kurallar + bulut kullanılır.
(( ram >= 12 )) || [[ -f ~/.config/tdk/config.toml ]] || printf '[local]\nenabled = false\n' >~/.config/tdk/config.toml
if .venv/bin/python -c 'import sys; from tdk.config import load; sys.exit(not load()["local"]["enabled"])'; then
  model=$d/models/gemma-4-E4B_q4_0-it.gguf
  [[ -f $model ]] || curl -L --fail -o "$model" \
    https://huggingface.co/google/gemma-4-E4B-it-qat-q4_0-gguf/resolve/main/gemma-4-E4B_q4_0-it.gguf
  systemctl --user enable --now tdk-llama.service
else
  systemctl --user disable --now tdk-llama.service 2>/dev/null || true
  echo "Yerel model kapalı (RAM ${ram} GB, ~/.config/tdk/config.toml): yalnız kurallar ve bulut kullanılacak."
fi
systemctl --user enable tdkd.service
# Güncellemede çalışan servis eski kodla kalmasın.
systemctl --user restart tdkd.service

if [[ ${1:-} == --train ]]; then
  # shortcut: yalnız AMD (ROCm) torch kurulur; NVIDIA için index-url cu12x olmalı.
  uv venv --allow-existing --python 3.13 "$d/train-venv"
  uv pip install --python "$d/train-venv/bin/python" --index-url https://download.pytorch.org/whl/rocm7.1 torch==2.13.0+rocm7.1
  uv pip install --python "$d/train-venv/bin/python" transformers==5.22.1 peft==0.21.2 accelerate==1.15.0 gguf
  if [[ ! -d $d/llama.cpp-src ]]; then
    git clone --quiet --filter=blob:none --no-checkout https://github.com/ggml-org/llama.cpp "$d/llama.cpp-src"
    git -C "$d/llama.cpp-src" sparse-checkout set --no-cone /convert_lora_to_gguf.py /convert_hf_to_gguf.py /gguf-py /conversion
    git -C "$d/llama.cpp-src" checkout --quiet d812350493
  fi
  systemctl --user enable --now tdk-train.timer
fi

bind=~/.config/hypr/keybind.lua
if [[ -f $bind ]] && ! grep -q "tdk popup" "$bind"; then
  # Hyprland'in PATH'inde ~/.local/bin yok; tam yol verilir.
  binds='hl.bind("SUPER + ALT + T", hl.dsp.exec_cmd("~/.local/bin/tdk popup"), { description = "Türkçe yazım denetimi" })
hl.bind("SUPER + ALT + SHIFT + T", hl.dsp.exec_cmd("~/.local/bin/tdk popup --auto"), { description = "Türkçe yazım hızlı düzeltme" })'
  # Modül "return" ile bitiyor; ondan sonra eklenen satır Lua hatası verip Hyprland'i acil moda düşürür.
  awk -v add="$binds" '/^return/ && !done {print add; done=1} {print} END {if (!done) print add}' "$bind" >"$bind.tmp"
  mv "$bind.tmp" "$bind"
  hyprctl reload >/dev/null
fi
echo "Kuruldu. GPU için: echo 'TDK_DEVICE=Vulkan0 TDK_NGL=99' > ~/.config/tdk/llama.env && systemctl --user restart tdk-llama"
