# tdk — Türkçe yazım denetleyici

Linux masaüstünde (Wayland/Hyprland) her uygulamada çalışan Türkçe yazım ve dilbilgisi denetleyicisi. Metni seç, kısayola bas, hataları gör, istediğin düzeltmeleri uygula.

Denetim üç katmanlıdır:

1. **Kurallar** (akana + `tdk/data/lexicon.tsv` + `tdk/data/deascii.tsv`): milisaniyeler içinde sonuç verir, model gerektirmez. `cok`, `calisiyor` gibi Türkçe karakteri eksik kelimeleri de düzeltir.
2. **Yerel model** (Gemma 4 E4B, llama.cpp): kuralların kaçırdıklarını yakalar. İşlemcide birkaç saniye sürer, en fazla 20 sn beklenir.
3. **Bulut** (OpenRouter, `google/gemini-3.8-flash`): isteğe bağlı. Yerel model çökerse yedek, eğitimde öğretmen olarak kullanılır. Gönderilmeden önce kişisel veriler maskelenir.

Açılır pencere önce kural sonucunu gösterir; model sonucu geldiğinde liste güncellenir. Acil durumda modeli beklemeden uygulayabilirsin.

## Kurulum

```bash
./install.sh            # denetleyici, servisler, kısayollar
./install.sh --train    # ek olarak haftalık LoRA eğitim ortamı (AMD GPU, ~30 GB disk)
```

- RAM 12 GB'ın altındaysa yerel model kurulmaz; yalnız kurallar ve bulut kullanılır. Güçlü makinede de bunu istiyorsan kurulumdan önce `~/.config/tdk/config.toml` dosyasına `[local]` altında `enabled = false` yaz. Bu durumda bulut her denetimde birincil model olur.
- Bulut için OpenRouter anahtarını `~/.config/openrouter/key` dosyasına yaz ya da aşağıdaki OpenCode Go ayarını kullan.
- Yerel modeli GPU'da çalıştırmak için:

```bash
echo 'TDK_DEVICE=Vulkan0 TDK_NGL=99' > ~/.config/tdk/llama.env
systemctl --user restart tdk-llama
```

Servisler: `tdk-llama` (model, :8091, en fazla 8 GB RAM), `tdkd` (denetim, :8092), `tdk-train.timer` (pazar 03:30).

## Kullanım

| Kısayol | İş |
|---|---|
| `SUPER + ALT + T` | Seçili metni denetle, açılır pencerede göster |
| `SUPER + ALT + SHIFT + T` | Pencere açmadan, yalnız kurallarla yüksek güvenli düzeltmeleri uygula |

Açılır pencerede `1`-`9` öneriyi seçer/bırakır, `Enter` uygular, `Esc` kapatır. Terminallerde düzeltilmiş metin yalnız panoya kopyalanır.

Komut satırı:

```bash
tdk check "metin"          # öneriler
tdk check -f "metin"       # yalnız kurallar, beklemesiz
tdk check -c --fix <dosya.txt   # bulutla, yalnız düzeltilmiş metin
tdk stats                  # öğrenme istatistikleri
tdk train --dry-run        # eğitim verisini hazırla, eğitme
```

## Ayarlar

`~/.config/tdk/config.toml` (yalnız değiştirmek istediğin alanlar):

```toml
apply_threshold = 0.5

[local]
enabled = true
timeout = 20

[cloud]
enabled = true
model = "google/gemini-3.8-flash"
```

OpenCode Go aboneliğiyle bulut (anahtar `~/.config/opencode-go/key`):

```toml
[cloud]
url = "https://opencode.ai/inference/go/v1"
model = "glm-5.3-flash"
key_file = "~/.config/opencode-go/key"
extra = {}
headers = { "x-opencode-session" = "tdk" }
```

`extra = {}` OpenRouter'a özgü `reasoning` alanını kaldırır; OpenCode Go oturum başlığı olmayan isteği reddeder.

Kendi kelime düzeltmelerin için `~/.config/tdk/lexicon.tsv` (`yanlış<TAB>doğru`; `herkez*` gibi sonda `*` çekimli biçimleri de kapsar).

## Öğrenme

- Aynı öneriyi iki kez reddedersen o düzeltme bir daha gösterilmez.
- Kabul ettiğin düzeltmeler örnek olarak saklanır; benzer metinlerde modele örnek verilir.
- Haftada bir LoRA ince ayarı yapılır: senin kararların, bulut öğretmenin etiketleri ve GECTurk verisi. Yeni adaptör yalnız ölçümde eskisinden kötü değilse devreye alınır, yoksa geri dönülür. Eğitim 14 GB RAM ile sınırlıdır; aşarsa yalnız eğitim durur.

## Ölçümler

`eval/gold.jsonl` (104 cümle, 44'ü hatasız), eşik 0,4:

| Kurulum | Kesinlik | Duyarlılık | F0.5 | Tam doğru | Yanlış alarm | Gecikme |
|---|---|---|---|---|---|---|
| Yalnız kurallar | 0,857 | 0,529 | 0,763 | 71 | 3/44 | ms |
| + Qwen3.5-4B (CPU) | 0,707 | 0,853 | 0,732 | 79 | 10/44 | 3,1 sn |
| + Gemma 4 E4B (CPU) | 0,800 | 0,882 | 0,815 | 89 | 6/44 | 3,0 sn |
| + Gemma 4 12B (GPU) | 0,831 | 0,941 | 0,851 | 91 | 8/44 | 2,4 sn |
| + Gemini 3.8 Flash (bulut) | 0,878 | 0,956 | 0,893 | 97 | 3/44 | 2,6 sn |

Yeniden ölçmek için: `uv run python eval/run.py --threshold 0.4`.

## Lisans

MIT. `eval/movie_reviews.jsonl`, eğitimde indirilen veri ve `lexicon.tsv`'deki istisna sözlükleri [GECTurk](https://github.com/GGLAB-KU/gecturk) (Apache-2.0) kaynaklıdır. `deascii.tsv`, [FrequencyWords](https://github.com/hermitdave/FrequencyWords) (MIT) Türkçe sıklık listesinden üretilmiştir.
