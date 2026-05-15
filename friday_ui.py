"""
FRIDAY — AI Voice Assistant  (complete, fixed)

Install:
    pip install customtkinter SpeechRecognition pyttsx3 pyaudio requests ddgs newspaper3k

Run Ollama first:
    ollama serve
    ollama pull phi3      ← or llama3 / mistral

Then:
    python friday_final.py
"""

# ── stdlib ────────────────────────────────────────────────────────
import math, time, threading, datetime, webbrowser, queue
# ── third-party ───────────────────────────────────────────────────
import requests
import customtkinter as ctk
from tkinter import Canvas
import speech_recognition as sr

# optional internet search
try:
    from ddgs import DDGS
    from newspaper import Article
    SEARCH_OK = True
except ImportError:
    SEARCH_OK = False

# ═════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "phi3"          # change to llama3 / mistral etc.
USER_NAME    = "Keshav"

# ═════════════════════════════════════════════════════════════════
# INTERNET SEARCH
# ═════════════════════════════════════════════════════════════════
def smart_search(query: str) -> str:
    if not SEARCH_OK:
        return ""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        collected = ""
        for r in results:
            try:
                url = r["href"]
                article = Article(url)
                article.download()
                article.parse()
                collected += article.text[:1500]
            except:
                pass
        return collected[:4000]
    except Exception as e:
        print("SEARCH ERROR:", e)
        return ""

# ═════════════════════════════════════════════════════════════════
# AI  (Ollama)
# ═════════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are FRIDAY, an advanced AI voice assistant like Iron Man's FRIDAY.

RULES:
- Reply in 1-2 short sentences ONLY (you speak aloud, be brief)
- Never say "As an AI"
- Address the user as """ + USER_NAME + """
- Sound confident, human, slightly witty
- No bullet points, no markdown, no lists

BROWSER CONTROL — open ANY website by outputting this tag in your reply:
  [OPEN:full_url]

Examples:
  open youtube         → [OPEN:https://youtube.com] Opening YouTube for you.
  open instagram       → [OPEN:https://instagram.com] Here\'s Instagram.
  open gmail           → [OPEN:https://mail.google.com] Opening your Gmail.
  search cats google   → [OPEN:https://www.google.com/search?q=cats] Searching for cats.
  open netflix         → [OPEN:https://netflix.com] Opening Netflix.
  open github          → [OPEN:https://github.com] Here\'s GitHub.
  search python on youtube → [OPEN:https://www.youtube.com/results?search_query=python] Searching YouTube.
  open reddit          → [OPEN:https://reddit.com] Here\'s Reddit.
  open twitter         → [OPEN:https://x.com] Opening X, formerly Twitter.
  open spotify         → [OPEN:https://open.spotify.com] Opening Spotify.

SHUTDOWN — when user says goodbye/exit/quit/shut down:
  [SHUTDOWN] Goodbye """ + USER_NAME + """.

Always put the [OPEN:url] tag FIRST before your spoken words.
The tag is invisible to the user — only your words are spoken aloud."""

import re as _re

def extract_url(reply: str):
    match = _re.search(r'\[OPEN:(https?://[^\]]+)\]', reply)
    if match:
        url = match.group(1).strip()
        clean = _re.sub(r'\[OPEN:[^\]]+\]', '', reply).strip()
        return clean, url
    return reply.strip(), None

def ask_ai(prompt: str) -> str:
    try:
        internet = smart_search(prompt)
        full_prompt = (
            SYSTEM_PROMPT + "\n\n"
            + (f"Internet context:\n{internet}\n\n" if internet else "")
            + f"User: {prompt}\nFRIDAY:"
        )
        res = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": full_prompt, "stream": False},
            timeout=30
        )
        res.raise_for_status()
        return res.json()["response"].strip()
    except requests.exceptions.ConnectionError:
        return "Ollama is not running. Please start it with: ollama serve"
    except requests.exceptions.Timeout:
        return "That took too long. Try a lighter model like phi3."
    except Exception as e:
        print("AI ERROR:", e)
        return "Something went wrong with my AI core."

# ═════════════════════════════════════════════════════════════════
# TTS  — macOS `say` command (most reliable on Mac)
#         falls back to pyttsx3 on Windows/Linux
# ═════════════════════════════════════════════════════════════════
import subprocess, sys, shutil

_tts_queue = queue.Queue()
_tts_done  = threading.Event()
_tts_done.set()

# macOS voices — Samantha sounds most natural
# Run `say -v ?` in terminal to list all available voices
MACOS_VOICE = "Samantha"   # change to: Ava, Karen, Moira, Tessa, Veena

def _say_macos(text: str):
    """Use macOS built-in TTS — works even without pyttsx3."""
    subprocess.run(["say", "-v", MACOS_VOICE, "-r", "185", text])

def _say_pyttsx3(text: str):
    """Fallback for Windows / Linux."""
    try:
        import pyttsx3 as _px
        e = _px.init()
        e.setProperty("rate", 170)
        e.say(text)
        e.runAndWait()
    except Exception as ex:
        print(f"[TTS ERROR] {ex}")

IS_MAC = sys.platform == "darwin"

def _tts_worker():
    while True:
        text = _tts_queue.get()
        if text is None:
            break
        _tts_done.clear()
        if IS_MAC:
            _say_macos(text)
        else:
            _say_pyttsx3(text)
        _tts_done.set()
        _tts_queue.task_done()

threading.Thread(target=_tts_worker, daemon=True).start()

def speak(text: str, wait: bool = False):
    """Queue text for speech. Safe to call from any thread."""
    short = text[:72] + ("…" if len(text) > 72 else "")
    update_status(f"FRIDAY: {short}", CYAN)
    _tts_queue.put(text)
    if wait:
        _tts_queue.join()
        _tts_done.wait(timeout=15)

# ═════════════════════════════════════════════════════════════════
# LISTEN
# ═════════════════════════════════════════════════════════════════
_rec = sr.Recognizer()
_rec.pause_threshold       = 0.8
_rec.energy_threshold      = 300
_rec.dynamic_energy_threshold = True

def listen(timeout: int = 6, phrase_limit: int = 10) -> str:
    try:
        with sr.Microphone() as source:
            update_status("🎤  LISTENING…", CYAN2)
            _rec.adjust_for_ambient_noise(source, duration=0.3)
            update_status("🎤  SPEAK NOW…", CYAN2)
            audio = _rec.listen(source, timeout=timeout, phrase_time_limit=phrase_limit)
        update_status("⏳  PROCESSING…", "#AAAAFF")
        text = _rec.recognize_google(audio)
        update_status(f"YOU: {text.upper()}", "#FFFFFF")
        return text.lower().strip()
    except sr.UnknownValueError:
        update_status("❓  COULDN'T UNDERSTAND", "#FF9966")
    except sr.WaitTimeoutError:
        update_status("⏱  NO SPEECH DETECTED", "#888888")
    except OSError as e:
        update_status(f"MIC ERROR: {e}", "#FF4444")
        time.sleep(1)
    except Exception as e:
        update_status(f"ERROR: {e}", "#FF4444")
        time.sleep(0.5)
    return ""

# ═════════════════════════════════════════════════════════════════
# COMMAND HANDLER
# ═════════════════════════════════════════════════════════════════
def handle_command(cmd: str) -> bool:
    """All commands go to AI. Returns False if Friday should shut down."""
    c = cmd.lower().strip()
    print(f"[CMD] {c}")

    # ── instant local shortcuts (no AI delay) ───────────────────
    if any(w in c for w in ("goodbye", "shut down", "shutdown", "exit", "quit")):
        speak(f"Goodbye, {USER_NAME}.", wait=True)
        return False
    if c in ("time", "what time is it", "what\'s the time"):
        t = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The time is {t}.")
        return True
    if c in ("date", "what\'s today", "what is today"):
        d = datetime.datetime.now().strftime("%A, %B %d")
        speak(f"Today is {d}.")
        return True

    # ── everything else → AI brain (handles ALL browser requests) ─
    update_status("🧠  THINKING…", "#AA88FF")
    raw_reply = ask_ai(cmd)
    print(f"[AI RAW] {raw_reply}")

    # extract [OPEN:url] tag if AI included one
    spoken, url = extract_url(raw_reply)

    # check for shutdown tag
    if "[SHUTDOWN]" in spoken:
        spoken = spoken.replace("[SHUTDOWN]", "").strip()
        speak(spoken or f"Goodbye, {USER_NAME}.", wait=True)
        return False

    # open URL first (non-blocking), then speak
    if url:
        print(f"[BROWSER] {url}")
        webbrowser.open(url)

    speak(spoken or "Done.")
    return True

# ═════════════════════════════════════════════════════════════════
# ASSISTANT LOOP
# ═════════════════════════════════════════════════════════════════
running          = False
_loop_started    = False

def run_assistant():
    global running
    while True:
        if not running:
            time.sleep(0.2)
            continue

        update_status("👂  WAITING FOR 'FRIDAY'…", "#336655")
        heard = listen(timeout=6, phrase_limit=6)

        if not heard:
            time.sleep(0.2)
            continue

        if "friday" not in heard:
            continue

        # Command may be inline: "Friday what time is it"
        inline = heard.replace("friday", "").strip(" ,.")
        if inline:
            keep = handle_command(inline)
        else:
            speak("Yes?", wait=True)
            time.sleep(0.3)
            command = listen(timeout=8, phrase_limit=12)
            if not command:
                speak("I didn't catch that.")
                continue
            keep = handle_command(command)

        if not keep:
            running = False
            _set_btn_state(False)

# ═════════════════════════════════════════════════════════════════
# UI CONTROLS
# ═════════════════════════════════════════════════════════════════
def start():
    global running, _loop_started
    if running:
        return
    running = True
    _set_btn_state(True)
    if not _loop_started:
        _loop_started = True
        threading.Thread(target=run_assistant, daemon=True).start()
    speak(f"FRIDAY online. Ready, {USER_NAME}.")

def stop():
    global running
    running = False
    _set_btn_state(False)
    update_status("SYSTEM IDLE", "#445566")

def _set_btn_state(active: bool):
    app.after(0, lambda: (
        start_btn.configure(state="disabled" if active else "normal"),
        stop_btn.configure(state="normal"   if active else "disabled"),
    ))

# ═════════════════════════════════════════════════════════════════
# UI CONSTANTS
# ═════════════════════════════════════════════════════════════════
BG       = "#020B18"
CYAN     = "#00F5FF"
CYAN2    = "#00BCD4"
DIM      = "#003344"
DARK     = "#001122"
W, H     = 1100, 750
CX, CY   = 550, 310
FPS      = 30
FONT_HUD = ("Courier New", 9)

# ═════════════════════════════════════════════════════════════════
# WINDOW
# ═════════════════════════════════════════════════════════════════
ctk.set_appearance_mode("dark")
app = ctk.CTk()
app.geometry(f"{W}x{H}")
app.configure(fg_color=BG)
app.title("FRIDAY")
app.resizable(False, False)

# ── top bar ──────────────────────────────────────────────────────
top = ctk.CTkFrame(app, fg_color=BG, height=60)
top.pack(fill="x", pady=(10, 0))

ctk.CTkLabel(top, text="F  R  I  D  A  Y",
             font=("Courier New", 36, "bold"),
             text_color=CYAN).pack(side="left", padx=30)
ctk.CTkLabel(top, text="AUTONOMOUS RESPONSE INTELLIGENCE\nDIGITAL ASSISTANT YIELDING",
             font=("Courier New", 9), text_color=DIM,
             justify="left").pack(side="left", padx=4)

clock_lbl = ctk.CTkLabel(top, text="", font=("Courier New", 11), text_color=CYAN2)
clock_lbl.pack(side="right", padx=30)

def _tick():
    while True:
        now = time.strftime("%H:%M:%S   %Y.%m.%d")
        app.after(0, lambda t=now: clock_lbl.configure(text=t))
        time.sleep(1)
threading.Thread(target=_tick, daemon=True).start()

# ═════════════════════════════════════════════════════════════════
# CANVAS + 3-D SPHERE
# ═════════════════════════════════════════════════════════════════
canvas = Canvas(app, width=W, height=420, bg=BG, highlightthickness=0)
canvas.pack()

class Sphere3D:
    def __init__(self, cv, cx, cy, r=120, lat_n=8, lon_n=12):
        self.cv, self.cx, self.cy = cv, cx, cy
        self.r, self.lat, self.lon = r, lat_n, lon_n
        self.ax = self.ay = 0.0
        self.ids = []

    def _project(self, x, y, z):
        cosX, sinX = math.cos(self.ax), math.sin(self.ax)
        cosY, sinY = math.cos(self.ay), math.sin(self.ay)
        x2 =  x*cosY + z*sinY;  z2 = -x*sinY + z*cosY
        y3 =  y*cosX - z2*sinX; z3 =  y*sinX + z2*cosX
        sc = 0.8 + 0.2*(z3/self.r + 1)
        return self.cx + x2*sc, self.cy + y3*sc, z3

    def draw(self):
        for i in self.ids:
            try: self.cv.delete(i)
            except: pass
        self.ids = []
        steps = 60
        for li in range(1, self.lat):
            phi  = math.pi*li/self.lat - math.pi/2
            cy_r = math.cos(phi)*self.r
            cz   = math.sin(phi)*self.r
            pts  = []
            for j in range(steps+1):
                th = 2*math.pi*j/steps
                px, py, pz = self._project(cy_r*math.cos(th), cz, cy_r*math.sin(th))
                pts.append((px, py, pz))
            for j in range(len(pts)-1):
                d = (pts[j][2]+self.r)/(2*self.r)
                a = int(30+120*d)
                c = f"#{0:02x}{min(a,0xF5):02x}{min(a+20,0xFF):02x}"
                self.ids.append(self.cv.create_line(pts[j][0],pts[j][1],pts[j+1][0],pts[j+1][1],fill=c,width=1))
        for lo in range(self.lon):
            th  = 2*math.pi*lo/self.lon
            pts = []
            for j in range(steps+1):
                phi = math.pi*j/steps - math.pi/2
                px, py, pz = self._project(math.cos(phi)*math.cos(th)*self.r,
                                           math.sin(phi)*self.r,
                                           math.cos(phi)*math.sin(th)*self.r)
                pts.append((px, py, pz))
            for j in range(len(pts)-1):
                d = (pts[j][2]+self.r)/(2*self.r)
                a = int(30+100*d)
                c = f"#{0:02x}{min(a,0xF5):02x}{min(a+20,0xFF):02x}"
                self.ids.append(self.cv.create_line(pts[j][0],pts[j][1],pts[j+1][0],pts[j+1][1],fill=c,width=1))

sphere     = Sphere3D(canvas, CX, CY, r=120)
RING_R     = [145, 170, 200, 235]
RING_TILT  = [15, -20, 10, -8]
N_PART     = 18
particles  = [{"orbit_r": 180+(i%3)*28, "speed": 0.012-i*0.0003,
               "angle": 2*math.pi*i/N_PART, "size": 2+(i%3), "trail": []}
              for i in range(N_PART)]
scan_angle = 0.0
frame_ids  = []
_frame_n   = 0

def _clr():
    for i in frame_ids:
        try: canvas.delete(i)
        except: pass
    frame_ids.clear()

def _c(iid):
    frame_ids.append(iid)
    return iid

# ═════════════════════════════════════════════════════════════════
# ANIMATION LOOP
# ═════════════════════════════════════════════════════════════════
def draw_frame():
    global scan_angle, _frame_n
    _clr()
    t     = _frame_n / FPS
    _frame_n += 1
    pulse = 0.5 + 0.5*math.sin(t*2.2)

    # sphere
    sphere.ax = math.sin(t*0.3)*0.25
    sphere.ay = t*0.4
    sphere.draw()

    # rings
    for idx, (rr, tilt) in enumerate(zip(RING_R, RING_TILT)):
        off = t*(0.4+idx*0.15) + idx*1.2
        a   = math.radians(tilt)
        rx  = rr
        ry  = rr*abs(math.sin(a+off*0.1))*0.55 + rr*0.12
        br  = int(80+80*pulse) if idx%2==0 else int(40+40*pulse)
        col = f"#{0:02x}{min(br,0xF5):02x}{min(br+30,0xFF):02x}"
        prev= None
        for s in range(121):
            ang = 2*math.pi*s/120 + off
            x   = CX + rx*math.cos(ang)
            y   = CY + ry*math.sin(ang)
            if prev:
                _c(canvas.create_line(prev[0],prev[1],x,y,fill=col,width=1+(idx==2)))
            prev = (x,y)

    # scan arc
    scan_angle += 3.5
    sa = math.radians(scan_angle)
    SR = 155
    for w, af in [(3,0.8),(2,0.5),(1,0.3)]:
        for ds in range(70):
            ang  = sa + math.radians(ds)
            fade = 1 - ds/70
            br   = int(200*fade*af)
            col  = f"#{0:02x}{min(br,0xF5):02x}{min(br+20,0xFF):02x}"
            x1=CX+SR*math.cos(ang-math.radians(1)); y1=CY+(SR*0.45)*math.sin(ang-math.radians(1))
            x2=CX+SR*math.cos(ang);                 y2=CY+(SR*0.45)*math.sin(ang)
            _c(canvas.create_line(x1,y1,x2,y2,fill=col,width=w))

    # particles
    for p in particles:
        p["angle"] += p["speed"]
        rx=p["orbit_r"]; ry=rx*0.38
        x=CX+rx*math.cos(p["angle"]); y=CY+ry*math.sin(p["angle"])
        p["trail"].append((x,y))
        if len(p["trail"])>14: p["trail"].pop(0)
        for ti,(tx,ty) in enumerate(p["trail"]):
            fade=ti/len(p["trail"]); br=int(220*fade)
            col=f"#{0:02x}{min(br,0xF5):02x}{min(br+20,0xFF):02x}"
            r=max(1,int(p["size"]*fade))
            _c(canvas.create_oval(tx-r,ty-r,tx+r,ty+r,fill=col,outline=""))
        sz=p["size"]
        _c(canvas.create_oval(x-sz,y-sz,x+sz,y+sz,fill=CYAN,outline=""))

    # HUD left
    lx,ly = 30,55
    for line,col in [
        ("SYSTEM STATUS",CYAN),("─────────────",DIM),
        (f"CPU    {40+int(30*pulse):>3}%",CYAN2),(f"MEM    {55+int(10*pulse):>3}%",CYAN2),
        ("NET    ACTIVE",CYAN),("",DIM),
        ("VOICE CORE",CYAN),("─────────────",DIM),
        ("STT    READY",CYAN2),("NLU    ACTIVE",CYAN2),("TTS    ONLINE",CYAN2),("",DIM),
        ("OLLAMA BRIDGE",CYAN),("─────────────",DIM),
        (f"MODEL  {OLLAMA_MODEL}",CYAN2),("PORT   11434",CYAN2),
        (f"PING   {8+int(5*pulse)}ms",CYAN2),
    ]:
        _c(canvas.create_text(lx,ly,text=line,font=FONT_HUD,fill=col,anchor="w"))
        ly+=15

    # HUD right
    rx2,ry2 = W-30,55
    for line,col in [
        ("ENVIRONMENT",CYAN),("─────────────",DIM),
        (f"TIME   {time.strftime('%H:%M:%S')}",CYAN2),(f"DATE   {time.strftime('%Y.%m.%d')}",CYAN2),
        ("LOC    EARTH",CYAN2),("",DIM),
        ("SENSORS",CYAN),("─────────────",DIM),
        ("MIC    ARMED",CYAN2),("WAKE   FRIDAY",CYAN2),("LANG   EN-US",CYAN2),("",DIM),
        ("AI CORE",CYAN),("─────────────",DIM),
        ("MODE   CHAT",CYAN2),("CTX    ACTIVE",CYAN2),
        (f"RESP   {120+int(40*pulse)}ms",CYAN2),
    ]:
        _c(canvas.create_text(rx2,ry2,text=line,font=FONT_HUD,fill=col,anchor="e"))
        ry2+=15

    # corner brackets
    for (cx2,cy2),(dx,dy) in zip([(4,4),(W-4,4),(4,420-4),(W-4,420-4)],[(1,1),(-1,1),(1,-1),(-1,-1)]):
        _c(canvas.create_line(cx2,cy2,cx2+18*dx,cy2,fill=CYAN,width=2))
        _c(canvas.create_line(cx2,cy2,cx2,cy2+18*dy,fill=CYAN,width=2))

    # centre glow
    gr=int(8+6*pulse)
    for rad,alpha in [(gr+8,20),(gr+4,60),(gr,200)]:
        col=f"#00{alpha:02x}ff" if alpha<100 else CYAN
        _c(canvas.create_oval(CX-rad,CY-rad,CX+rad,CY+rad,
                              fill="" if alpha<100 else CYAN,outline=col,width=1))

    app.after(1000//FPS, draw_frame)

# ═════════════════════════════════════════════════════════════════
# STATUS + BUTTONS
# ═════════════════════════════════════════════════════════════════
bottom = ctk.CTkFrame(app, fg_color=BG)
bottom.pack(fill="x")

status_label = ctk.CTkLabel(bottom, text="SYSTEM READY",
    font=("Courier New", 15, "bold"), text_color=CYAN, wraplength=900)
status_label.pack(pady=(4,8))

def update_status(text: str, color: str = CYAN):
    app.after(0, lambda: status_label.configure(
        text=text[:90].upper(), text_color=color))

btn_row = ctk.CTkFrame(bottom, fg_color=BG)
btn_row.pack(pady=(0,10))

start_btn = ctk.CTkButton(btn_row, text="▶  INITIATE", command=start,
    fg_color=CYAN, hover_color=CYAN2, text_color=BG,
    font=("Courier New",15,"bold"), width=220, height=50, corner_radius=30)
start_btn.grid(row=0, column=0, padx=16)

stop_btn = ctk.CTkButton(btn_row, text="■  SHUTDOWN", command=stop,
    fg_color=DARK, hover_color="#001A2A", border_color=CYAN, border_width=2,
    text_color=CYAN, font=("Courier New",15,"bold"),
    width=220, height=50, corner_radius=30, state="disabled")
stop_btn.grid(row=0, column=1, padx=16)

ctk.CTkLabel(bottom, text='SAY  "FRIDAY"  TO WAKE  •  "FRIDAY GOODBYE"  TO SLEEP',
    font=("Courier New",9), text_color=DIM).pack(pady=(0,6))

# ═════════════════════════════════════════════════════════════════
# START
# ═════════════════════════════════════════════════════════════════
draw_frame()
app.mainloop()