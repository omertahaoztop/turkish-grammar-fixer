# Türkçe Yazım Düzeltici: sistem geneli, yerel öncelikli, öğrenen sürüm

## Amaç

Firefox eklentisini, Hyprland masaüstünün her yerinde (tarayıcı, Zulip, ZapZap, editör, terminal) çalışan bir araca dönüştürmek:

1. Metni seç, kısayola bas, hataları gör, istediğini uygula.
2. Kontrol önce yerelde, CPU üzerinde çalışsın; bulut (OpenRouter) yalnız isteğe bağlı yedek olsun.
3. Sistem, kullanıcının kabul/ret kararlarından öğrensin; zamanla yerel model kullanıcının yazısına uyum sağlasın.

## Bugünkü durum ve neden zayıf

- Her istekte `tdk_rules_clean.txt` (108 KB, yaklaşık 30-40 bin token) prompt'a gömülüyor: yavaş, pahalı, küçük modellerde bağlamı boğuyor.
- Kodda sabit duran ücretsiz modeller (`llama-3.3-70b:free` vb.) OpenRouter'da artık yok; bugünkü ücretsiz liste alakasız modellerden oluşuyor.
- Model tüm metni yeniden yazıyor ve "orijinal → düzeltilmiş" listesini kendisi üretiyor; konum (offset) yok, uydurma eşleşme denetlenmiyor, uygulama tek parça "hepsini değiştir".
- `max_tokens: 2048`: uzun metinde yanıt kesiliyor, JSON bozuluyor.
- Yalnız tarayıcıda, yalnız sağ tık menüsüyle çalışıyor.

## Yapılan keşif (bu oturumda ölçüldü)

- Makine: i7-12700K (20 çekirdek, AVX2), 31 GB RAM, Radeon RX 9060 XT. Hyprland 0.57 (Lua yapılandırma), `wl-paste`, `wl-copy`, `wtype`, `notify-send`, GTK4 4.24 + libadwaita 1.10 + gtk4-layer-shell Python bağları hazır.
- GTK4 kullanıcı teması `~/.config/gtk-4.0/noctalia.css` üzerinden Noctalia paletini veriyor; libadwaita ile yazılan pencere masaüstü renklerini kendiliğinden alır.
- OpenRouter anahtarı `~/.config/openrouter/key` içinde, ücretli hesap (kredi var).
- LanguageTool Türkçeyi desteklemiyor.
- `akana==0.6.0` (Rust + Python, MIT; GECTurk'ün 25 kural sınıfı, morfoloji, yazım, KVKK maskeleme) denendi:
  - Doğru buldu: `Hiç bir → Hiçbir`, `Geliyormusun → Geliyor musun`, `Yalnış → Yanlış`.
  - Yanlış düzeltti: `Bende geldim → Ben De geldim` (büyük harf hatası).
  - Kaçırdı: `herkez`, `gelicek`, `birşey`, `kitabıda`, `şuan`, `ankaraya`, `istanbulda`, `gitlab`, `ipsec`.
  - Yazım denetçisi `gelicek`, `birşey`, `şuan`, `yalnış` sözcüklerini doğru sayıyor.
  - Sonuç: kural motoru hızlı ve açıklamalı aday üretici olarak değerli, tek başına yeterli değil.
- Hazır Türkçe düzeltme modelleri var (denenmedi): `GGLab/gec-tr-seq-tagger` (BERTurk etiketleyici), `Alperens1/turna-gec-1` (TURNA 1B), `yeniguno/mbart50-turkish-grammar-corrector` (0.6B). Veri: GECTurk (138 bin cümle + elle işaretlenmiş film yorumu test seti), BOUN de/da veri seti.

## Mimari

```
seçim (wl-paste -p) ─┐
CLI / stdin ─────────┼─> tdkd (yerel servis, Unix soket) ──> öneri listesi (span + açıklama + güven)
tarayıcı eklentisi ──┘        │
                              ├─ 1. normalizasyon + korunan bölgeler (URL, kod, e-posta, @kişi)
                              ├─ 2. kural katmanı: akana + TDK "yanlış/doğru" sözlüğü + teknik terim sözlüğü
                              ├─ 3. yerel model: llama.cpp ile küçük LLM (veya seq2seq GEC modeli)
                              ├─ 4. isteğe bağlı bulut: OpenRouter (PII maskeli)
                              └─ 5. birleştirme: kelime düzeyi diff -> span, çakışma çözümü, güven puanı
                                        │
geri bildirim (kabul / ret / elle düzeltme) ──> SQLite ──> öğrenme katmanları
```

İlkeler:

- Model metni yeniden yazar, düzenlemeleri biz `difflib` ile kelime düzeyinde çıkarırız; modelin kendi "orijinal" iddiasına güvenmeyiz. Her öneri kaynak metindeki gerçek konuma bağlıdır.
- Kesinlik geri çağırmadan önce gelir: yalnız biçim, harf, ek ve bitişik/ayrı yazım düzenlemeleri önerilir; anlam değiştiren yeniden yazımlar (eşik üstü düzenleme mesafesi) elenir.
- Kural katmanı ile model aynı düzeltmede birleşirse güven yükselir; tek kaynaklı öneriler "emin değil" olarak işaretlenir. Akana'nın `Ben De` hatası bu doğrulamayla elenir.
- Prompt'a 108 KB kural metni girmez; yalnız ilgili kural maddeleri (akana bulgusunun sınıfına göre) ve kullanıcının benzer geçmiş düzeltmeleri eklenir.

## Öğrenme ("kendini eğitme") üç katmanda

1. Anında: kişisel sözlük (reddedilen yazım uyarısındaki sözcük eklenir, `SpellChecker.add_word`), kural başına kabul oranı; oranı düşen kural kendiliğinden susturulur.
2. Anında: geçmiş düzeltmelerden benzer örnekler (akana'nın gömülü Türkçe embedding modeliyle arama) yerel modelin prompt'una az örnekli (few-shot) olarak eklenir. Eğitim gerektirmez, ilk günden etkili.
3. Periyodik: biriken kabul edilmiş çiftler + GECTurk + (izin verilirse) bulut modelin "öğretmen" olarak etiketlediği kendi metinlerin ile yerel modele LoRA ince ayarı. `systemd --user` zamanlayıcısıyla gece koşar; yeni model ayrık değerlendirme setinde F0.5 ve temiz metinde yanlış alarm oranında eskisini geçmezse devreye alınmaz.

## Masaüstü akışı

- Kısayol (öneri: `SUPER + ALT + T`, `keybind.lua` içinde boş): seçili metni `wl-paste --primary` ile alır, imleç yanında GTK4 + layer-shell açılır pencere gösterir.
- Pencerede: değişen kısımlar renkli diff, her öneri için kabul/ret, "hepsini uygula", açıklama ve kural adı. Klavyeyle tam kullanım (Enter, Esc, sayı tuşları).
- Uygulama: düzeltilmiş metin `wl-copy` ile panoya, `wtype` ile yapıştırma; terminal sınıflarında `ctrl+shift+v`. Eski pano içeriği geri yüklenir.
- İkinci kısayol: açılır pencere olmadan yalnız yüksek güvenli düzeltmeleri uygula, `notify-send` ile özet ver.
- Kabul/ret kararları geri bildirim olarak servise gider.

## Değerlendirme seti

- GECTurk elle işaretlenmiş film yorumu test seti.
- Kullanıcının kendi yazı tarzından 100-200 cümlelik altın set: teknik terimler (GitLab, IPsec), hitaplar (Hocam, Bey), konuşma dili, Türkçe/İngilizce karışık metin, hatasız metinler (yanlış alarm ölçümü için).
- Ölçütler: F0.5, temiz metinde yanlış alarm oranı, 300 karakterlik metinde gecikme (hedef: CPU'da 3 saniyenin altı).

## Uygulama adımları

- [x] 1. Değerlendirme düzeneği: `eval/` altında altın set, M2 benzeri puanlayıcı, temel çizgiler (akana tek başına, mevcut OpenRouter prompt'u).
- [x] 2. Yerel model keşfi: Qwen3.5-4B, Gemma 4 E4B (CPU) ve Gemma 4 12B (GPU) aynı sette ölçüldü; varsayılan Gemma 4 E4B. GEC modelleri denenmedi.
- [x] 3. `tdkd` çekirdeği: katmanlı boru hattı, diff tabanlı span çıkarımı, birleştirme ve güven puanı, `tdk check` CLI.
- [x] 4. Servis: 127.0.0.1:8092 üzerinden JSON API, `systemd --user` birimleri (tdkd + llama-server, bellek sınırlı), model sıcak tutulur.
- [x] 5. Masaüstü: kısayol, GTK4/layer-shell açılır pencere (önce kurallar, sonra model), uygulama ve pano geri yükleme.
- [x] 6. Öğrenme katman 1 ve 2: SQLite geri bildirim deposu, kişisel sözlük, kural susturma, benzer örnek arama.
- [ ] 7. Öğrenme katman 3: LoRA eğitim betiği, değerlendirme kapısı, model değişimi, haftalık zamanlayıcı (yazıldı, gerçek eğitim denenmedi).
- [x] 8. Tarayıcı eklentisi: kaldırıldı; sistem geneli kısayol onun yerini alıyor.
- [x] 9. Paketleme ve belgeler: `install.sh`, README, MIT lisansı; eski eklenti dosyaları, `tdk_rules*.txt` ve `.xpi` kaldırıldı.

## Senin kararını bekleyen noktalar

1. GPU: "CPU ile çalışsın" dedin; RX 9060 XT Vulkan üzerinden llama.cpp'yi belirgin hızlandırır. Varsayılan CPU kalsın, GPU isteğe bağlı açılsın mı?
2. Bulut: OpenRouter yedek ve "öğretmen" olarak kullanılsın mı? Kullanılırsa metin gönderilmeden önce akana ile KVKK maskelemesi yapılır.
3. Tarayıcı eklentisi: kısayol tarayıcıda da çalıştığı için eklentiyi kaldırmak en sade yol. Eklenti yalnız "yazarken altını çiz" özelliği istenirse anlamlı. Kaldıralım mı?
4. Yazarken anlık denetim (her uygulamada, seçmeden): Wayland'de genel yolu yalnız Fcitx5 eklentisi. Bu sürümün kapsamı dışında bırakmayı öneriyorum.
5. Kısayol: `SUPER + ALT + T` uygun mu?
