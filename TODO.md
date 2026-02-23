# TODO — Türkçe Yazım Düzeltici

## 🐛 Hata Düzeltme

- [ ] TDK fetch zaman aşımı senaryosu: Ağ yoksa ya da TDK erişilemezse kullanıcıya net hata mesajı göster
- [ ] Çok uzun metinlerde (>2000 karakter) `max_tokens` aşımı olabiliyor — büyük metinleri otomatik parçalara böl
- [ ] `response_format: json_object` desteklemeyen modellerde JSON parse hatası — fallback parse ekle

## ✨ Yeni Özellikler

- [ ] **Diff görünümü**: Orijinal ve düzeltilmiş metni yan yana göster (değişen kısımları renkli vurgula)
- [ ] **Kısmi uygula**: Hata listesinden istediğin düzeltmeleri seçip sadece onları uygula
- [ ] **Geçmiş**: Son N düzeltmeyi popup'ta listele (session bazlı)
- [ ] **Klavye kısayolu**: Seçili metni kısayolla düzelt (örn: `Ctrl+Shift+T`)
- [ ] **Otomatik dil tespiti**: Metin Türkçe değilse uyarı ver, düzeltme yapma
- [ ] **Sağ tık → Kelime düzelt**: Tek bir kelimeye sağ tıklayınca sadece o kelimeyi kontrol et

## ⚙️ Ayarlar & Yapılandırma

- [ ] **Özel kural listesi**: Kullanıcının kendi "dokunma / her zaman düzelt" listesini ekleyebileceği alan
- [ ] **Katılık seviyesi**: "Sadece belirgin hatalar" / "Her şeyi düzelt" modu
- [ ] **Model performans skoru**: Her modelin başarı/başarısızlık sayısını takip et, otomatik sırala
- [ ] **İhmal listesi**: Belirli alan adlarında (örn: localhost) extension'ı devre dışı bırak

## 🎨 UI / UX

- [ ] Tooltip pozisyonu: Ekran kenarında kesilirse otomatik ters tarafa aç
- [ ] Yükleniyor animasyonu daha belirgin olsun (şu an çok küçük)
- [ ] Options sayfasında TDK kurallarının kaç madde yüklendiğini göster
- [ ] Popup'ta son kullanılan model ve kaç düzeltme yapıldığını göster (session istatistiği)

## 🔧 Teknik Borç

- [ ] `background.js` büyüdü — `tdk.js`, `openrouter.js`, `contextmenu.js` olarak böl
- [ ] TDK fetch için retry mekanizması ekle (3 deneme, exponential backoff)
- [ ] `extractArticleContent()` regex'leri daha sağlam hale getir (TDK sayfa yapısı değişirse kırılıyor)
- [ ] Unit test yaz: prompt builder, JSON parse fallback, model fallback sırası

## 📦 Dağıtım

- [ ] Firefox Add-ons (AMO) store'a yükle — imzalı XPI için Mozilla review süreci
- [ ] Chrome/Edge uyumluluğu: MV3'e geçiş araştır (`browser` → `chrome` API farkları)
- [ ] Otomatik XPI paketleme için `Makefile` veya `package.json` script ekle (`npm run build`)
- [ ] GitHub Actions ile tag'e otomatik XPI release oluştur
