"""Seçili metni denetler; imleç yanında açılan pencerede önerileri gösterir ve seçilenleri yerine yapıştırır."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from html import escape

from .cli import call

LAYER_SHELL = "/usr/lib/libgtk4-layer-shell.so"
TERMINALS = {"kitty", "foot", "alacritty", "org.wezfurlong.wezterm", "com.mitchellh.ghostty", "quickterm"}
WIDTH = 560


# Katman kabuğu kütüphanesi alt süreçlere geçerse notify-send gibi araçlar sembol hatasıyla düşüyor.
ENV = {k: v for k, v in os.environ.items() if k != "LD_PRELOAD"}


def sh(*cmd: str, input: str | None = None) -> str:
    return subprocess.run(cmd, input=input, capture_output=True, text=True, env=ENV, check=False).stdout


def copy(text: str):
    # wl-copy arka planda kalır; çıktısı yakalanırsa boru kapanmadığı için run() geri dönmez.
    subprocess.run(["wl-copy"], input=text, text=True, env=ENV, check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def hypr(what: str) -> dict | list:
    return json.loads(sh("hyprctl", what, "-j") or "{}")


def notify(title: str, body: str = ""):
    subprocess.Popen(["notify-send", "-a", "Türkçe Yazım", title, body], env=ENV)


def apply_edits(text: str, edits: list[dict]) -> str:
    out, pos = [], 0
    for e in sorted(edits, key=lambda e: e["start"]):
        out += [text[pos:e["start"]], e["replacement"]]
        pos = e["end"]
    return "".join(out) + text[pos:]


def paste(text: str, window_class: str) -> bool:
    """Metni seçimin yerine yapıştırır; terminalde yalnız panoya kopyalar. Önceki pano geri yüklenir."""
    if window_class.lower() in TERMINALS:
        copy(text)
        return False
    old = subprocess.run(["wl-paste", "--no-newline", "--type", "text/plain"], capture_output=True, text=True,
                         env=ENV, check=False)
    copy(text)
    time.sleep(0.15)
    sh("wtype", "-M", "ctrl", "v", "-m", "ctrl")
    time.sleep(0.4)
    if old.returncode == 0:
        copy(old.stdout)
    return True


def feedback(cid: int, accepted: list[int]):
    try:
        call("/feedback", {"id": cid, "accepted": accepted}, timeout=10)
    except urllib.error.URLError:
        pass


def run(auto: bool = False):
    text = sh("wl-paste", "--primary", "--no-newline")
    if not text.strip():
        notify("Seçili metin yok", "Önce denetlenecek metni seç.")
        return
    win = hypr("activewindow")
    if auto:
        try:
            # Hızlı düzeltme beklememeli: yalnız kurallar, modelsiz.
            res = call("/check", {"text": text, "fast": True})
        except urllib.error.URLError:
            notify("tdkd çalışmıyor", "systemctl --user start tdkd")
            return
        picked = [i for i, e in enumerate(res["edits"]) if e["confidence"] >= res["threshold"]]
        if not picked:
            notify("Hata bulunmadı")
            return
        pasted = paste(apply_edits(text, [res["edits"][i] for i in picked]), win.get("class", ""))
        feedback(res["id"], picked)
        notify(f"{len(picked)} düzeltme uygulandı" if pasted else f"{len(picked)} düzeltme panoya kopyalandı")
        return
    if os.environ.get("LD_PRELOAD", "").find("layer-shell") < 0 and os.path.exists(LAYER_SHELL):
        # gtk4-layer-shell, libwayland'den önce yüklenmek zorunda; bu yüzden süreç yeniden başlatılır.
        os.environ["LD_PRELOAD"] = LAYER_SHELL
        os.execv(sys.executable, [sys.executable, "-m", "tdk.popup"])
    Popup(text, win).run()


class Popup:
    def __init__(self, text: str, win: dict):
        self.text, self.win = text, win
        self.res: dict | None = None
        self.checks = []
        self.gen, self.final, self.overrides = 0, False, {}

    def run(self):
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw
        self.app = Adw.Application(application_id="tr.tdk.Popup")
        self.app.connect("activate", self._build)
        self.app.run([])
        if self.after:
            self.after()

    after = None

    def _build(self, app):
        from gi.repository import Adw, Gdk, GLib, Gtk
        self.Gtk, self.GLib = Gtk, GLib
        w = self.window = Adw.ApplicationWindow(application=app, title="Türkçe Yazım", default_width=WIDTH)
        w.add_css_class("tdk-popup")
        css = Gtk.CssProvider()
        # Katman yüzeyinde masaüstü teması pencere zeminini saydam bırakıyor; zemin temanın renginden verilir.
        css.load_from_string(".tdk-popup { background: @window_bg_color; border: 1px solid alpha(@accent_bg_color, .5);"
                             " border-radius: 14px; } .tdk-preview { font-size: 1.05em; }")
        Gtk.StyleContext.add_provider_for_display(w.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._place(w, Gdk)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        self.preview = Gtk.Label(wrap=True, xalign=0, selectable=True, max_width_chars=60)
        self.preview.add_css_class("tdk-preview")
        self.status = Gtk.Label(label="Denetleniyor…", xalign=0)
        self.status.add_css_class("dim-label")
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.scroll = scroll = Gtk.ScrolledWindow(child=self.listbox, max_content_height=340,
                                                  hscrollbar_policy=Gtk.PolicyType.NEVER)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        self.cloud_btn = Gtk.Button(label="Bulutla dene")
        self.cloud_btn.connect("clicked", lambda *_: self._start(cloud=True))
        copy_btn = Gtk.Button(label="Kopyala")
        copy_btn.connect("clicked", lambda *_: self._finish(paste_it=False))
        self.apply_btn = Gtk.Button(label="Uygula", sensitive=False)
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.connect("clicked", lambda *_: self._finish(paste_it=True))
        for b in (self.cloud_btn, copy_btn, self.apply_btn):
            buttons.append(b)
        for child in (self.status, self.preview, scroll, buttons):
            root.append(child)
        w.set_content(root)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        w.add_controller(keys)
        self.preview.set_text(self.text)
        w.present()
        self._start(cloud=False)

    def _place(self, w, Gdk):
        try:
            gi_ls = __import__("gi")
            gi_ls.require_version("Gtk4LayerShell", "1.0")
            from gi.repository import Gtk4LayerShell as LS
        except (ValueError, ImportError):
            return
        if not LS.is_supported():
            return
        LS.init_for_window(w)
        LS.set_namespace(w, "tdk-popup")
        LS.set_layer(w, LS.Layer.OVERLAY)
        LS.set_keyboard_mode(w, LS.KeyboardMode.EXCLUSIVE)
        cur = hypr("cursorpos") or {"x": 0, "y": 0}
        mons = hypr("monitors")
        mon = next((m for m in mons if m["x"] <= cur.get("x", 0) < m["x"] + m["width"] / m["scale"]
                    and m["y"] <= cur.get("y", 0) < m["y"] + m["height"] / m["scale"]), mons[0] if mons else None)
        if not mon:
            return
        gmons = w.get_display().get_monitors()
        for i in range(gmons.get_n_items()):
            if gmons.get_item(i).get_connector() == mon["name"]:
                LS.set_monitor(w, gmons.get_item(i))
        mw, mh = mon["width"] / mon["scale"], mon["height"] / mon["scale"]
        x = min(max(cur["x"] - mon["x"] - WIDTH // 2, 8), mw - WIDTH - 8)
        y = min(max(cur["y"] - mon["y"] + 24, 8), mh - 480)
        LS.set_anchor(w, LS.Edge.LEFT, True)
        LS.set_anchor(w, LS.Edge.TOP, True)
        LS.set_margin(w, LS.Edge.LEFT, int(x))
        LS.set_margin(w, LS.Edge.TOP, int(y))

    def _start(self, cloud: bool):
        self.gen += 1
        gen, self.final = self.gen, False
        self.status.set_text("Bulut modeliyle denetleniyor…" if cloud else "Denetleniyor…")
        self.cloud_btn.set_sensitive(False)

        def work(fast: bool):
            try:
                res = call("/check", {"text": self.text, "cloud": cloud, "fast": fast})
            except urllib.error.URLError as e:
                res = {"error": f"tdkd çalışmıyor ({e.reason}). systemctl --user start tdkd"}
            self.GLib.idle_add(self._show, res, gen, fast)
        # Kural sonuçları milisaniyede gelir ve hemen uygulanabilir; model sonucu gelince liste güncellenir.
        if not cloud:
            threading.Thread(target=work, args=(True,), daemon=True).start()
        threading.Thread(target=work, args=(False,), daemon=True).start()

    def _toggled(self, cb, key):
        self.overrides[key] = cb.get_active()
        self._render()

    def _show(self, res: dict, gen: int, fast: bool):
        Gtk = self.Gtk
        if gen != self.gen or (fast and self.final):
            return
        if "error" in res:
            self.status.set_text(res["error"])
            self.cloud_btn.set_sensitive(True)
            return
        self.final = not fast
        self.cloud_btn.set_sensitive(self.final)
        self.res = res
        while (row := self.listbox.get_first_child()) is not None:
            self.listbox.remove(row)
        self.checks = []
        for i, e in enumerate(res["edits"]):
            row = Gtk.Box(spacing=10, margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
            key = (e["start"], e["end"], e["replacement"])
            cb = Gtk.CheckButton(active=self.overrides.get(key, e["confidence"] >= res["threshold"]))
            cb.connect("toggled", self._toggled, key)
            self.checks.append(cb)
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            title = Gtk.Label(xalign=0, wrap=True, use_markup=True,
                              label=f"<s>{escape(e['original'])}</s>  →  <b>{escape(e['replacement'])}</b>")
            sub = " · ".join(filter(None, [e["explanation"], "+".join(e["sources"]), f"%{round(e['confidence'] * 100)}"]))
            info = Gtk.Label(label=sub, xalign=0, wrap=True)
            info.add_css_class("dim-label")
            info.add_css_class("caption")
            col.append(title)
            col.append(info)
            key = Gtk.Label(label=str(i + 1) if i < 9 else "")
            key.add_css_class("dim-label")
            for c in (cb, col, key):
                row.append(c)
            self.listbox.append(row)
        n = len(res["edits"])
        warn = f" · uyarı: {res['errors'][0]}" if res.get("errors") else ""
        if n:
            head = f"{n} öneri · 1-9 seç/bırak · Enter uygula · Esc kapat"
        else:
            head = "Kurallara göre hata yok" if fast else "Hata bulunmadı"
        self.status.set_text(head + (" · model denetliyor…" if fast else "") + warn)
        # Katman yüzeyi ilk eşlemedeki boyutta kalıyor; doğal yükseklik yerine açık bir alt sınır verilir.
        self.scroll.set_min_content_height(min(n * 58, 340))
        self.scroll.set_visible(bool(n))
        self._render()

    def _picked(self) -> list[int]:
        return [i for i, cb in enumerate(self.checks) if cb.get_active()]

    def _render(self):
        edits = self.res["edits"] if self.res else []
        picked = set(self._picked())
        out, pos = [], 0
        for i, e in enumerate(edits):
            out.append(escape(self.text[pos:e["start"]]))
            if i in picked:
                out.append(f"<span underline='single'><b>{escape(e['replacement'])}</b></span>")
            else:
                out.append(f"<span alpha='60%'>{escape(e['original'])}</span>")
            pos = e["end"]
        out.append(escape(self.text[pos:]))
        self.preview.set_markup("".join(out))
        self.apply_btn.set_sensitive(bool(picked))

    def _key(self, _ctrl, keyval, _code, _state):
        from gi.repository import Gdk
        name = Gdk.keyval_name(keyval) or ""
        if name == "Escape":
            self.window.close()
        elif name in ("Return", "KP_Enter") and self.apply_btn.get_sensitive():
            self._finish(paste_it=True)
        elif name.isdigit() and 0 < int(name) <= len(self.checks):
            cb = self.checks[int(name) - 1]
            cb.set_active(not cb.get_active())
        else:
            return False
        return True

    def _finish(self, paste_it: bool):
        if not self.res:
            return
        picked = self._picked()
        final = apply_edits(self.text, [self.res["edits"][i] for i in picked])
        cid, cls, addr = self.res["id"], self.win.get("class", ""), self.win.get("address")

        def after():
            # Yapıştırma, kısayola basıldığı penceredeki seçimin yerine gitmeli; arada odak kaymış olabilir.
            if paste_it and addr:
                sh("hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{addr}" }})')
            time.sleep(0.25)
            if not (paste_it and paste(final, cls)):
                copy(final)
                notify("Düzeltilmiş metin panoya kopyalandı")
            feedback(cid, picked)
        self.after = after
        self.window.close()


if __name__ == "__main__":
    run()
