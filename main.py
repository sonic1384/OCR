import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

from PIL import ImageGrab, ImageEnhance, ImageFilter

APP_NAME = "ScreenText OCR"
HOTKEY_ID = 1
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
VK = {**{chr(i): i for i in range(ord('A'), ord('Z')+1)}, **{str(i): 0x30+i for i in range(10)}}
VK.update({"F1":0x70,"F2":0x71,"F3":0x72,"F4":0x73,"F5":0x74,"F6":0x75,"F7":0x76,"F8":0x77,"F9":0x78,"F10":0x79,"F11":0x7A,"F12":0x7B})
CONFIG_DIR = Path(os.getenv("APPDATA", Path.home())) / "ScreenTextOCR"
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / name)


def capture_screen():
    return ImageGrab.grab(all_screens=True)


def ocr_with_windows(image_path, language):
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", resource_path("ocr.ps1"), image_path, language]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "Windows OCR failed.")
    return p.stdout.strip()


def enhance(img):
    # Upscaling + contrast/sharpness helps small UI/game text.
    if img.width < 1400 or img.height < 800:
        img = img.resize((img.width * 2, img.height * 2))
    img = ImageEnhance.Contrast(img).enhance(1.25)
    return ImageEnhance.Sharpness(img).enhance(1.5).filter(ImageFilter.SHARPEN)


class Overlay:
    def __init__(self, app, image):
        self.app, self.image = app, image
        self.win = tk.Toplevel(app.root)
        self.win.attributes("-fullscreen", True); self.win.attributes("-topmost", True); self.win.attributes("-alpha", 0.22)
        self.win.configure(cursor="crosshair", bg="black")
        self.canvas = tk.Canvas(self.win, bg="black", highlightthickness=0); self.canvas.pack(fill="both", expand=True)
        self.x0 = self.y0 = None; self.rect = None
        self.win.bind("<ButtonPress-1>", self.start); self.win.bind("<B1-Motion>", self.drag); self.win.bind("<ButtonRelease-1>", self.finish)
        self.win.bind("<Escape>", lambda e: self.close()); self.win.focus_force()

    def start(self, e):
        self.x0, self.y0 = e.x, e.y
        self.rect = self.canvas.create_rectangle(e.x,e.y,e.x,e.y,outline="white",width=2)

    def drag(self, e):
        if self.rect: self.canvas.coords(self.rect,self.x0,self.y0,e.x,e.y)

    def finish(self, e):
        if self.x0 is None: return
        x1,y1,x2,y2 = min(self.x0,e.x),min(self.y0,e.y),max(self.x0,e.x),max(self.y0,e.y)
        self.close()
        if x2-x1 >= 5 and y2-y1 >= 5: self.app.run_ocr(self.image.crop((x1,y1,x2,y2)))

    def close(self):
        try: self.win.destroy()
        except tk.TclError: pass


class App:
    def __init__(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = self.load_config(); self.history = self.load_history()
        self.root = tk.Tk(); self.root.title(APP_NAME); self.root.geometry("980x700"); self.root.minsize(760,520)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        self.style = ttk.Style();
        try: self.style.theme_use("vista")
        except tk.TclError: pass
        self.build_ui(); self.register_hotkey(); self.refresh_history()

    def load_config(self):
        defaults = {"language":"en-US","hotkey":"Ctrl+Shift+C","enhance":True,"auto_copy":True,"mode":"select"}
        try: defaults.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except Exception: pass
        return defaults

    def load_history(self):
        try: return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception: return []

    def save_config(self):
        CONFIG_FILE.write_text(json.dumps(self.cfg,indent=2),encoding="utf-8")

    def save_history(self):
        HISTORY_FILE.write_text(json.dumps(self.history[:100],indent=2,ensure_ascii=False),encoding="utf-8")

    def build_ui(self):
        top=ttk.Frame(self.root,padding=18); top.pack(fill="x")
        ttk.Label(top,text="ScreenText OCR",font=("Segoe UI",24,"bold")).pack(side="left")
        self.hotkey_label=ttk.Label(top,text=self.cfg["hotkey"],font=("Segoe UI",11)); self.hotkey_label.pack(side="right",pady=8)

        bar=ttk.Frame(self.root,padding=(18,0,18,12)); bar.pack(fill="x")
        ttk.Button(bar,text="Capture Region",command=self.capture_select).pack(side="left")
        ttk.Button(bar,text="OCR Entire Screen",command=self.capture_full).pack(side="left",padx=8)
        ttk.Button(bar,text="Auto Detect Text",command=self.capture_auto).pack(side="left")
        ttk.Button(bar,text="Copy",command=self.copy).pack(side="right")
        ttk.Button(bar,text="Clear",command=lambda:self.text.delete("1.0","end")).pack(side="right",padx=8)

        pan=ttk.Panedwindow(self.root,orient="horizontal"); pan.pack(fill="both",expand=True,padx=18,pady=(0,12))
        left=ttk.Frame(pan,padding=10); right=ttk.Frame(pan,padding=10); pan.add(left,weight=4); pan.add(right,weight=1)
        self.text=tk.Text(left,wrap="word",font=("Segoe UI",11),undo=True,relief="solid",borderwidth=1); self.text.pack(fill="both",expand=True)

        ttk.Label(right,text="Settings",font=("Segoe UI",13,"bold")).pack(anchor="w",pady=(0,10))
        ttk.Label(right,text="OCR language").pack(anchor="w")
        self.lang=ttk.Combobox(right,values=["English (en-US)","Persian (fa-IR)","French (fr-FR)","German (de-DE)","Spanish (es-ES)","Japanese (ja-JP)","Chinese (zh-CN)","User profile languages"],state="readonly")
        lang_map={"en-US":"English (en-US)","fa-IR":"Persian (fa-IR)","fr-FR":"French (fr-FR)","de-DE":"German (de-DE)","es-ES":"Spanish (es-ES)","ja-JP":"Japanese (ja-JP)","zh-CN":"Chinese (zh-CN)"}
        self.lang.set(lang_map.get(self.cfg["language"],"User profile languages")); self.lang.pack(fill="x",pady=(4,14)); self.lang.bind("<<ComboboxSelected>>",lambda e:self.save_settings())
        self.enh=tk.BooleanVar(value=self.cfg["enhance"]); ttk.Checkbutton(right,text="Enhance small text",variable=self.enh,command=self.save_settings).pack(anchor="w",pady=3)
        self.acopy=tk.BooleanVar(value=self.cfg["auto_copy"]); ttk.Checkbutton(right,text="Copy OCR result automatically",variable=self.acopy,command=self.save_settings).pack(anchor="w",pady=3)
        ttk.Separator(right).pack(fill="x",pady=14)
        ttk.Label(right,text="Global hotkey",font=("Segoe UI",10,"bold")).pack(anchor="w")
        self.hk=ttk.Entry(right); self.hk.insert(0,self.cfg["hotkey"]); self.hk.pack(fill="x",pady=5)
        ttk.Button(right,text="Apply hotkey",command=self.change_hotkey).pack(fill="x")
        ttk.Label(right,text="Examples: Ctrl+Shift+C, Alt+F8, Ctrl+F9",wraplength=190).pack(anchor="w",pady=(5,0))
        ttk.Separator(right).pack(fill="x",pady=14)
        ttk.Label(right,text="OCR History",font=("Segoe UI",10,"bold")).pack(anchor="w")
        self.hist=tk.Listbox(right,height=12); self.hist.pack(fill="both",expand=True,pady=5); self.hist.bind("<Double-Button-1>",self.open_history)
        ttk.Button(right,text="Clear history",command=self.clear_history).pack(fill="x")

        self.status=tk.StringVar(value="Ready — use the hotkey or choose a capture mode.")
        ttk.Label(self.root,textvariable=self.status,anchor="w",padding=(18,6)).pack(fill="x")

    def save_settings(self):
        self.cfg["language"]=self.language_code(); self.cfg["enhance"]=self.enh.get(); self.cfg["auto_copy"]=self.acopy.get(); self.save_config()

    def language_code(self):
        s=self.lang.get(); return {"English (en-US)":"en-US","Persian (fa-IR)":"fa-IR","French (fr-FR)":"fr-FR","German (de-DE)":"de-DE","Spanish (es-ES)":"es-ES","Japanese (ja-JP)":"ja-JP","Chinese (zh-CN)":"zh-CN"}.get(s,"user")

    def register_hotkey(self):
        self.user32=ctypes.windll.user32; self.apply_hotkey_string(self.cfg["hotkey"]); self.root.after(80,self.poll_hotkey)

    def parse_hotkey(self,s):
        parts=[p.strip().upper() for p in s.split("+")]; mods=0; key=None
        for p in parts:
            if p in ("CTRL","CONTROL"): mods|=MOD_CONTROL
            elif p=="SHIFT": mods|=MOD_SHIFT
            elif p=="ALT": mods|=MOD_ALT
            elif p in ("WIN","WINDOWS"): mods|=MOD_WIN
            elif p in VK: key=VK[p]
        return (mods,key) if key else None

    def apply_hotkey_string(self,s):
        try: self.user32.UnregisterHotKey(None,HOTKEY_ID)
        except Exception: pass
        parsed=self.parse_hotkey(s)
        if not parsed or not self.user32.RegisterHotKey(None,HOTKEY_ID,*parsed):
            self.status.set("Could not register that hotkey. Try another combination."); return False
        self.cfg["hotkey"]=s; self.hotkey_label.config(text=s); self.save_config(); return True

    def change_hotkey(self):
        s=self.hk.get().strip()
        if s and self.apply_hotkey_string(s): self.status.set(f"Hotkey changed to {s}.")

    def poll_hotkey(self):
        msg=ctypes.wintypes.MSG()
        while self.user32.PeekMessageW(ctypes.byref(msg),None,0,0,1):
            if msg.message==WM_HOTKEY and msg.wParam==HOTKEY_ID: self.capture_select()
        self.root.after(80,self.poll_hotkey)

    def capture_select(self):
        try:
            self.status.set("Drag over any text. Press Esc to cancel."); self.root.update()
            Overlay(self,capture_screen())
        except Exception as e: self.status.set(f"Capture error: {e}")

    def capture_full(self):
        try: self.run_ocr(capture_screen())
        except Exception as e: self.status.set(f"Capture error: {e}")

    def capture_auto(self):
        # Windows OCR itself finds text regions/lines across the supplied image.
        self.status.set("Automatically detecting text across the entire screen…")
        self.capture_full()

    def run_ocr(self,img):
        def worker():
            tmp=None
            try:
                self.root.after(0,lambda:self.status.set("Recognizing text…"))
                if self.enh.get(): img=enhance(img)
                fd,tmp=tempfile.mkstemp(suffix=".png"); os.close(fd); img.save(tmp,"PNG")
                result=ocr_with_windows(tmp,self.language_code())
                self.root.after(0,lambda:self.show_result(result))
            except Exception as e: self.root.after(0,lambda:self.status.set(f"OCR error: {e}"))
            finally:
                if tmp:
                    try: os.remove(tmp)
                    except OSError: pass
        threading.Thread(target=worker,daemon=True).start()

    def show_result(self,result):
        self.text.delete("1.0","end"); self.text.insert("1.0",result)
        if result.strip():
            self.history.insert(0,{"time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),"text":result})
            self.history=self.history[:100]; self.save_history(); self.refresh_history()
            if self.acopy.get(): self.copy(silent=True)
            self.status.set("OCR complete.")
        else: self.status.set("No text detected.")

    def copy(self,silent=False):
        value=self.text.get("1.0","end-1c")
        self.root.clipboard_clear(); self.root.clipboard_append(value); self.root.update()
        if not silent: self.status.set("Copied to clipboard.")

    def refresh_history(self):
        self.hist.delete(0,"end")
        for h in self.history:
            preview=" ".join(h["text"].split())[:55]
            self.hist.insert("end",f"{h['time']}  —  {preview}")

    def open_history(self,e=None):
        i=self.hist.curselection()
        if i: self.text.delete("1.0","end"); self.text.insert("1.0",self.history[i[0]]["text"]); self.status.set("Loaded OCR history item.")

    def clear_history(self):
        self.history=[]; self.save_history(); self.refresh_history(); self.status.set("History cleared.")

    def quit(self):
        try:self.user32.UnregisterHotKey(None,HOTKEY_ID)
        except Exception:pass
        self.root.destroy()

    def run(self): self.root.mainloop()

if __name__=="__main__": App().run()
