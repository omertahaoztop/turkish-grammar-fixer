# Türkçe Yazım Düzeltici

Firefox eklentisi + Python backend. Seçili metinde Türkçe yazım hatalarını sağ tık menüsü ile tek tıkla düzeltir.

Zeyrek morfoloji analizi kullanarak bağlaç/hal eki ayrımını doğru yapar.

## Desteklenen Kurallar

| Kural | Hata örneği | Düzeltme |
|---|---|---|
| Bağlaç `da/de` uyumu | `o de geldi`, `o ta geldi` | `o da geldi` |
| Hal eki uyumu (sesli uyum) | `masade`, `kitapda` | `masada`, `kitapta` |
| Soru eki ayrı yazım + uyum | `geldimi`, `geldinmi` | `geldi mi`, `geldin mi` |
| Bağlaç `ki` ayrı yazım | `biliyorumki`, `diyorki` | `biliyorum ki`, `diyor ki` |
| Ünlü daralması (-yor önce) | `başlayor`, `söyleyor` | `başlıyor`, `söylüyor` |
| `-ile` eki ünlü uyumu | `arkadaşle`, `çiçekla` | `arkadaşla`, `çiçekle` |
| Büyük harf (cümle/metin başı) | `merhaba. nasılsın` | `Merhaba. Nasılsın` |

## Kurulum

### 1. Backend (Python)

```bash
# Gereksinim: Python 3.13+, uv
./start-backend.sh
```

İlk çalıştırmada sanal ortam kurulur ve NLTK verisi indirilir (~10 saniye).
Sonraki çalıştırmalarda direkt başlar.

Backend `http://127.0.0.1:5858` adresinde çalışır.

### 2. Firefox Eklentisi

1. Firefox'ta `about:debugging` adresine git
2. **This Firefox** → **Load Temporary Add-on**
3. `extension/manifest.json` dosyasını seç

## Kullanım

1. Backend çalışıyor olmalı (`./start-backend.sh`)
2. Herhangi bir sayfada metni **seç**
3. Sağ tıkla → **"Türkçe yazımı düzelt"**
4. Metin yerinde düzeltilir, sağ altta değişiklik özeti gösterilir

## Dosya Yapısı

```
├── backend/
│   ├── app.py          — Flask REST API (POST /correct, GET /health)
│   ├── corrector.py    — Zeyrek ile Türkçe yazım düzeltme motoru
│   └── requirements.txt
├── extension/
│   ├── manifest.json   — Eklenti tanımı ve izinler
│   ├── background.js   — Sağ tık menüsü
│   ├── content.js      — Metin seçimi, backend isteği, metin değiştirme
│   └── content.css     — Toast bildirimi stili
└── start-backend.sh    — Backend başlatma scripti
```

## Gereksinimler

- Python 3.10+ (3.13 önerilir)
- [uv](https://docs.astral.sh/uv/) paket yöneticisi
- Firefox 57+
