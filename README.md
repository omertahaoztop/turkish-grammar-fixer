# Türkçe Yazım Düzeltici

TDK (Türk Dil Kurumu) yazım kurallarına göre Türkçe metinleri düzelten Firefox eklentisi. OpenRouter üzerindeki ücretsiz LLM modellerini kullanır.

## Özellikler

- **Sağ tıklama menüsü** ile seçili metni veya yazı alanının tamamını kontrol et
- Her hata için **TDK kural açıklaması**
- Düzeltilmiş metni **tek tıkla uygula** (input/textarea/contenteditable)
- Çalışmayan model için **otomatik fallback** sistemi
- **Ücretsiz** — OpenRouter free tier kullanır

## Desteklenen Modeller (Ücretsiz)

| Model | Sağlayıcı | Öncelik |
|-------|-----------|---------|
| Gemini 2.0 Flash Exp | Google | 1. (Önerilen) |
| Llama 3.3 70B Instruct | Meta | 2. |
| DeepSeek Chat | DeepSeek | 3. |
| Gemma 3 27B | Google | 4. |
| Mistral 7B Instruct | Mistral AI | 5. |

## Kurulum

### 1. OpenRouter API Anahtarı Al

1. [openrouter.ai](https://openrouter.ai) adresine git
2. Hesap oluştur (Google ile giriş yeterli)
3. [openrouter.ai/keys](https://openrouter.ai/keys) adresinden yeni API anahtarı oluştur
4. Anahtarı kopyala (`sk-or-v1-...`)

### 2. Firefox'a Yükle

**Geçici Yükleme (Geliştirme):**

1. Firefox'ta `about:debugging` adresine git
2. "Bu Firefox" → "Geçici Eklenti Yükle"
3. Bu klasördeki `manifest.json` dosyasını seç

**Kalıcı Yükleme (.xpi paketi):**

```bash
# Zip olarak paketle
zip -r turkish-grammar-fixer.xpi manifest.json background.js content.js content.css popup.html popup.css popup.js options.html options.css options.js icons/
```

Firefox'ta `about:addons` → Dişli ikon → "Dosyadan Eklenti Yükle" → `.xpi` dosyasını seç

### 3. API Anahtarını Gir

1. Eklenti ikonuna tıkla → "⚙️ Ayarlar"
2. API anahtarını gir
3. "Bağlantıyı Test Et" ile doğrula
4. "Kaydet"

## Kullanım

### Seçili Metin

1. Kontrol etmek istediğin metni seç
2. Sağ tıkla → **"Türkçe yazımı düzelt"**
3. Tooltip'te hataları gör ve düzeltilmiş metni kopyala

### Yazı Alanı (Input / Textarea)

1. Yazı alanına sağ tıkla
2. **"Bu alanın tamamını düzelt"**
3. Tooltip'te **"✅ Uygula"** butonuna tıkla → metin otomatik değiştirilir

## Kontrol Edilen Yazım Kuralları

- Büyük/küçük harf kullanımı
- Noktalama işaretleri (virgül, nokta, kesme işareti vb.)
- Bileşik sözcüklerin bitişik/ayrı yazımı
- Büyük ünlü uyumu ve ünsüz benzeşmesi
- ki / de / da / mi eklerinin doğru kullanımı
- Özel adlara eklenen kesme işareti
- Yabancı kökenli sözcüklerin Türkçe yazımı
- Anlatım bozuklukları

## Dosya Yapısı

```
turkish-grammar-fixer/
├── manifest.json        # Eklenti tanımı (MV2)
├── background.js        # OpenRouter API + context menu
├── content.js           # Sayfa etkileşimi + tooltip
├── content.css          # Tooltip stilleri
├── popup.html/css/js    # Toolbar popup
├── options.html/css/js  # Ayarlar sayfası
└── icons/               # PNG ikonlar
```
