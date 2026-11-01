"""Ayarlar: ~/.config/tdk/config.toml; dosya yoksa varsayılanlar kullanılır."""

import os
import tomllib
from pathlib import Path

from .engines import LLMEngine, RuleEngine
from .pipeline import Pipeline

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tdk"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "tdk"

DEFAULTS = {
    # Zayıf makinede model geç kalırsa kural sonuçları ve bulut yedeği beklemeden kullanılır.
    "local": {"enabled": True, "url": "http://127.0.0.1:8091/v1", "model": "yerel", "timeout": 20},
    # extra istek gövdesine, headers başlıklara eklenir; OpenRouter dışı uçlar bunları config.toml'dan değiştirir.
    "cloud": {"enabled": True, "url": "https://openrouter.ai/api/v1", "model": "google/gemini-3.8-flash",
              "key_file": "~/.config/openrouter/key", "extra": {"reasoning": {"effort": "minimal"}}, "headers": {}},
    "apply_threshold": 0.5,
    # LoRA, yerelde koşan QAT q4_0 GGUF'un türetildiği ağırlıklar üzerinde eğitilir.
    "train": {"base_hf": "google/gemma-4-E4B-it-qat-q4_0-unquantized", "gecturk": 3000},
}


def load() -> dict:
    cfg = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    path = CONFIG_DIR / "config.toml"
    if path.exists():
        for k, v in tomllib.loads(path.read_text(encoding="utf-8")).items():
            if isinstance(v, dict):
                cfg.setdefault(k, {}).update(v)
            else:
                cfg[k] = v
    return cfg


def build_pipeline(local_model: str | None = None, local: bool | None = None,
                   cloud_model: str | None = None, rules: bool = True) -> Pipeline:
    cfg = load()
    lc, cc = cfg["local"], cfg["cloud"]
    llm = None
    if lc["enabled"] if local is None else local:
        # Tek başına yerel model eşiğin altında kalır; ölçümde yalnız başına yanlış alarmı artırdı.
        llm = LLMEngine("yerel", lc["url"], local_model or lc["model"], weight=0.45, timeout=lc["timeout"],
                        extra={"chat_template_kwargs": {"enable_thinking": False}})
    cloud = None
    kf = Path(cc["key_file"]).expanduser()
    if cloud_model and not kf.exists():
        raise SystemExit(f"bulut anahtarı yok: {kf}")
    if (cloud_model or cc["enabled"]) and kf.exists():
        key = kf.read_text().strip()
        cloud = LLMEngine("bulut", cc["url"], cloud_model or cc["model"], key, weight=0.8, timeout=60,
                          extra=cc["extra"], headers=cc["headers"], mask_pii=True)
    return Pipeline(RuleEngine((CONFIG_DIR / "lexicon.tsv",)) if rules else None, llm, cloud)
