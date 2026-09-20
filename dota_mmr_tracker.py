#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dota 2 MMR Tracker — MVP для Windows + второй экран.
- Ручной ввод MMR за 3 сек после матча (самый надежный способ без бана и пароля Steam)
- Авто-подсчет разницы, история, график, винрейт, стрик
- Режим "Второй экран": огромное окно, перетащи на второй монитор + "Поверх всех окон"
- Данные: mmr_history.csv рядом со скриптом
Запуск: python dota_mmr_tracker.py  (или двойной клик)
Только стандартная библиотека Python, ничего ставить не надо.
"""
import csv
import glob
import json
import os
import re
import sys
import threading
import tkinter as tk
import urllib.request
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date

if getattr(sys, "frozen", False):
    # exe (PyInstaller onefile): данные рядом с программой, а не во временной папке
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "mmr_history.csv")
CONFIG_PATH = os.path.join(BASE_DIR, "mmr_config.json")

APP_VERSION = 12  # увеличивай при каждом релизе, иначе автообновление не сработает

# ---------- автообновление ----------
# Канал = статическая ссылка на manifest.json вида:
# {"version": 12, "url": "https://.../DotaMMRTracker_portable.zip", "notes": "что нового"}
# Где хостить: GitHub Releases/gist (рекомендую, всегда онлайн) или свой ПК
# (serve_updates.py + проброс порта). URL задается в настройках, хранится в конфиге.
def fetch_manifest(channel_url):
    req = urllib.request.Request(channel_url, headers={"User-Agent": "DotaMMRTracker/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def download_file(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "DotaMMRTracker/1.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)
    return dest

# ---------- тема: темный navy + золотые акценты (современный dark UI) ----------
TH_BG = "#0e1626"      # фон
TH_PANEL = "#152238"   # панели
TH_FIELD = "#0a1220"   # поля/таблицы
TH_FG = "#e8edf5"      # текст
TH_MUTED = "#7f95b3"   # приглушенный
TH_GOLD = "#f0a832"    # акцент (dota gold)
TH_CYAN = "#57c7ff"    # второй акцент
TH_GREEN = "#5ad66f"
TH_RED = "#ff6b6b"
TH_BTN = "#1d3350"
TH_BTN_HOVER = "#27436b"

def apply_theme(root):
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except Exception:
        pass
    st.configure(".", background=TH_BG, foreground=TH_FG,
                 fieldbackground=TH_FIELD, bordercolor=TH_BTN)
    st.configure("TFrame", background=TH_BG)
    st.configure("TLabel", background=TH_BG, foreground=TH_FG)
    st.configure("TLabelframe", background=TH_BG, foreground=TH_FG,
                 bordercolor=TH_BTN, relief="groove")
    st.configure("TLabelframe.Label", background=TH_BG, foreground=TH_GOLD)
    st.configure("TButton", background=TH_BTN, foreground=TH_FG,
                 bordercolor=TH_BTN, relief="flat", padding=6)
    st.map("TButton",
           background=[("active", TH_BTN_HOVER), ("pressed", TH_BTN_HOVER)],
           foreground=[("active", "#ffffff")])
    st.configure("TEntry", fieldbackground=TH_FIELD, foreground=TH_FG,
                 insertcolor=TH_FG)
    st.configure("TCheckbutton", background=TH_BG, foreground=TH_FG)
    st.map("TCheckbutton", background=[("active", TH_BG)])
    st.configure("Treeview", background=TH_FIELD, fieldbackground=TH_FIELD,
                 foreground=TH_FG, rowheight=22)
    st.map("Treeview",
           background=[("selected", TH_BTN_HOVER)],
           foreground=[("selected", "#ffffff")])
    st.configure("Treeview.Heading", background=TH_PANEL, foreground=TH_GOLD,
                 relief="flat")
    st.map("Treeview.Heading", background=[("active", TH_BTN)])
    st.configure("TScrollbar", background=TH_BG, troughcolor=TH_PANEL,
                 bordercolor=TH_BG)
    try:
        root.configure(bg=TH_BG)
    except Exception:
        pass

# ---------- config ----------
def load_config():
    cfg = {"account_id": "", "last_match_id": 0, "auto": True,
           "scan_region": None, "scan_interval": 15, "scan_on": False,
           "update_url": "", "last_update_check": ""}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def parse_account_id(text):
    """Принимает: 123456789, 76561198... (steam64), ссылку dotabuff/opendota/steam. Возвращает account32 (str) или None."""
    if not text:
        return None
    text = text.strip()
    # прямая ссылка на игрока opendota/dotabuff/stratz: /players/12345
    m = re.search(r"/players/(\d+)", text)
    if m:
        return m.group(1)
    # steam профиль /profiles/7656...
    m = re.search(r"/profiles/(\d+)", text)
    if m:
        return str(int(m.group(1)) - 76561197960265728)
    # все числа в строке
    nums = re.findall(r"\d{6,}", text)
    for n in nums:
        if n.startswith("7656119") and len(n) >= 15:
            try:
                return str(int(n) - 76561197960265728)
            except ValueError:
                continue
        if 6 <= len(n) <= 10:
            return n
    if text.isdigit() and 6 <= len(text) <= 10:
        return text
    return None

def fetch_recent_matches(account_id, limit=10):
    """OpenDota recentMatches, без ключа. Возвращает (list, error_str)."""
    url = f"https://api.opendota.com/api/players/{account_id}/recentMatches"
    req = urllib.request.Request(url, headers={"User-Agent": "DotaMMRTracker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data[:limit] if isinstance(data, list) else []), ""
    except Exception as e:
        return [], str(e)

def fetch_match_history(account_id, limit=100):
    """OpenDota: до 100 последних матчей (те же данные, что Dotabuff)."""
    url = f"https://api.opendota.com/api/players/{account_id}/matches?limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "DotaMMRTracker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return (data[:limit] if isinstance(data, list) else []), ""
    except Exception as e:
        return [], str(e)

def fetch_wl(account_id):
    """OpenDota: суммарные победы/поражения. Возвращает (win, lose)."""
    url = f"https://api.opendota.com/api/players/{account_id}/wl"
    req = urllib.request.Request(url, headers={"User-Agent": "DotaMMRTracker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return int(data.get("win", 0)), int(data.get("lose", 0))
    except Exception:
        return 0, 0

EST_STEP = 25  # шаг оценки кривой по результатам (±25 за матч)

def build_est_curve(matches):
    """Из списка матчей (любой порядок) строит оценку: oldest→newest, cum ±25."""
    ordered = sorted(matches, key=lambda m: (int(m.get("start_time", 0)), int(m.get("match_id", 0))))
    cum, out = 0, []
    for m in ordered:
        # в оценку берем только ранкеды (lobby_type 7); если поля нет — считаем
        lt = m.get("lobby_type", 7)
        try:
            lt = int(lt)
        except (TypeError, ValueError):
            lt = 7
        if lt != 7:
            continue
        w = match_is_win(m)
        if w is True:
            cum += EST_STEP
        elif w is False:
            cum -= EST_STEP
        try:
            ts = datetime.fromtimestamp(int(m.get("start_time", 0))).strftime("%m-%d %H:%M")
        except Exception:
            ts = ""
        out.append({"date": ts, "match_id": str(m.get("match_id", "")),
                    "win": w, "cum": cum,
                    "hero_id": str(m.get("hero_id", "?")),
                    "kda": f"{m.get('kills', '?')}/{m.get('deaths', '?')}/{m.get('assists', '?')}"})
    return out

def match_is_win(m):
    try:
        return (int(m.get("player_slot", 0)) < 128) == bool(m.get("radiant_win"))
    except Exception:
        return None

HERO_NAMES = {
    1: "Anti-Mage", 2: "Axe", 3: "Bane", 4: "Bloodseeker", 5: "Crystal Maiden",
    6: "Drow Ranger", 7: "Earthshaker", 8: "Juggernaut", 9: "Mirana", 10: "Morphling",
    11: "Shadow Fiend", 12: "Phantom Lancer", 13: "Puck", 14: "Pudge", 15: "Razor",
    16: "Sand King", 17: "Storm Spirit", 18: "Sven", 19: "Tiny", 20: "Vengeful Spirit",
    21: "Windranger", 22: "Zeus", 23: "Kunkka", 25: "Lina", 26: "Lion",
    27: "Shadow Shaman", 28: "Slardar", 29: "Tidehunter", 30: "Witch Doctor",
    31: "Lich", 32: "Riki", 33: "Enigma", 34: "Tinker", 35: "Sniper", 36: "Necrophos",
    37: "Warlock", 38: "Beastmaster", 39: "Queen of Pain", 40: "Venomancer",
    41: "Faceless Void", 42: "Wraith King", 43: "Death Prophet", 44: "Phantom Assassin",
    45: "Pugna", 46: "Templar Assassin", 47: "Viper", 48: "Luna", 49: "Dragon Knight",
    50: "Dazzle", 51: "Clockwerk", 52: "Leshrac", 53: "Nature's Prophet", 54: "Lifestealer",
    55: "Dark Seer", 56: "Clinkz", 57: "Omniknight", 58: "Enchantress", 59: "Huskar",
    60: "Night Stalker", 61: "Broodmother", 62: "Bounty Hunter", 63: "Weaver",
    64: "Jakiro", 65: "Batrider", 66: "Chen", 67: "Spectre", 68: "Ancient Apparition",
    69: "Doom", 70: "Ursa", 71: "Spirit Breaker", 72: "Gyrocopter", 73: "Alchemist",
    74: "Invoker", 75: "Silencer", 76: "Outworld Devourer", 77: "Lycan", 78: "Brewmaster",
    79: "Shadow Demon", 80: "Lone Druid", 81: "Chaos Knight", 82: "Meepo",
    83: "Treant Protector", 84: "Ogre Magi", 85: "Undying", 86: "Rubick",
    87: "Disruptor", 88: "Nyx Assassin", 89: "Naga Siren", 90: "Keeper of the Light",
    91: "Io", 92: "Visage", 93: "Slark", 94: "Medusa", 95: "Troll Warlord",
    96: "Centaur Warrunner", 97: "Magnus", 98: "Timbersaw", 99: "Bristleback",
    100: "Tusk", 101: "Skywrath Mage", 102: "Abaddon", 103: "Elder Titan",
    104: "Legion Commander", 105: "Techies", 106: "Ember Spirit", 107: "Earth Spirit",
    108: "Underlord", 109: "Terrorblade", 110: "Phoenix", 111: "Oracle",
    112: "Winter Wyvern", 113: "Arc Warden", 114: "Monkey King", 119: "Dark Willow",
    120: "Pangolier", 121: "Grimstroke", 123: "Hoodwink", 126: "Void Spirit",
    128: "Snapfire", 129: "Mars", 131: "Ring Master", 135: "Dawnbreaker", 136: "Marci",
    137: "Primal Beast", 138: "Muerta", 145: "Kez",
}

def hero_short(hero_id):
    """80 -> LD (Lone Druid). Длинные имена жмем до 2 букв."""
    try:
        name = HERO_NAMES.get(int(hero_id), "")
    except (TypeError, ValueError):
        name = ""
    if not name:
        return str(hero_id)
    parts = [p for p in re.split(r"[\s\-']+", name) if p]
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[:2].upper()

# ---------- storage ----------
def load_history():
    rows = []
    if not os.path.exists(CSV_PATH):
        return rows
    try:
        with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    rows.append({
                        "date": r.get("date", ""),
                        "mmr": int(r.get("mmr", 0)),
                        "change": int(r.get("change", 0) or 0),
                        "result": r.get("result", ""),
                        "match_id": str(r.get("match_id", "") or ""),
                        "hero_id": str(r.get("hero_id", "") or ""),
                        "kda": str(r.get("kda", "") or ""),
                    })
                except ValueError:
                    continue
    except Exception:
        pass
    return rows

def save_history(rows):
    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "mmr", "change", "result", "match_id", "hero_id", "kda"])
        w.writeheader()
        # сохраняем только известные колонки (обратная совместимость)
        for r in rows:
            w.writerow({k: r.get(k, "") for k in ["date", "mmr", "change", "result", "match_id", "hero_id", "kda"]})

def match_id_to_change(rows):
    """match_id -> change, для подстановки в таблицу последних 10."""
    d = {}
    for r in rows:
        mid = str(r.get("match_id", "") or "")
        if mid and mid != "0":
            d[mid] = r.get("change", 0)
    return d

# ---------- Сканер экрана (OCR, без ShowMMR) ----------
# Принцип: пользователь 1 раз рамкой выделяет область с цифрой MMR в клиенте Dota,
# дальше трекер сам скринит эту область (mss), распознает цифры (RapidOCR, onnx)
# и при стабильном изменении пишет запись в историю. Ничего вводить не надо.
_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine = RapidOCR()
    return _ocr_engine

def capture_region(region):
    """region = (x, y, w, h) -> PIL Image (увеличенная 2.5x для OCR)."""
    import mss
    from PIL import Image
    x, y, w, h = [int(v) for v in region]
    with mss.mss() as sct:
        shot = sct.grab({"left": x, "top": y, "width": w, "height": h})
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    # апскейл + ч/б: так OCR видит мелкие цифры клиента
    img = img.convert("L").resize((img.width * 3, img.height * 3))
    return img

def ocr_image_to_text(img):
    eng = get_ocr_engine()
    res, _ = eng(img)
    if not res:
        return ""
    return " ".join([str(r[1]) for r in res])

def parse_mmr_text(text):
    """Ищет итоговый MMR 100..30000. Понимает разделители тысяч: '2 315' -> 2315."""
    if not text:
        return None
    clean = re.sub(r"[^\d]", " ", str(text))
    toks = [t for t in clean.split() if t]
    if not toks:
        return None
    # 1) все цифры подряд (обычный случай: одна группа)
    alldigits = "".join(toks)
    if 3 <= len(alldigits) <= 5:
        try:
            v = int(alldigits)
            if 100 <= v <= 30000:
                return v
        except ValueError:
            pass
    # 2) склейка соседних групп: "2"+"315" -> 2315 (а "12"+"4230"+... пропускаем)
    for i in range(len(toks)):
        s = ""
        for j in range(i, min(i + 3, len(toks))):
            s += toks[j]
            if len(s) > 5:
                break
            if len(s) >= 3:
                try:
                    v = int(s)
                    if 100 <= v <= 30000:
                        return v
                except ValueError:
                    pass
    # 3) отдельные токены
    for tok in toks:
        try:
            v = int(tok)
            if 100 <= v <= 30000:
                return v
        except ValueError:
            continue
    # 4) слипшиеся длинные строки пополам
    m = re.search(r"\d{7,10}", alldigits)
    if m:
        s = m.group(0)
        half = len(s) // 2
        for cand in (s[:half], s[half:]):
            try:
                v = int(cand)
                if 100 <= v <= 30000:
                    return v
            except ValueError:
                pass
    return None

# ---------- ShowMMR import (принцип GameCoordinator) ----------
# ShowMMR (Lypheo, C# + SteamKit2) ходит в тот же GC-эндпоинт, что и вкладка Battle Stats:
# CMsgDOTAGetPlayerMatchHistory (по 20 матчей на страницу), откуда берет
# previous_rank (Start MMR) + rank_change. Сохраняет mmr_hist_v2_<user>.csv:
# Date,Unix time,MatchID,Solo Queue,HeroID,Start MMR,Rank Change
# Наш трекер нативно читает этот CSV и мержит по MatchID — это и есть
# "позаимствованный принцип": точные цифры без ручного ввода.
def find_showmmr_csv():
    pats = glob.glob(os.path.join(BASE_DIR, "mmr_hist_v2_*.csv"))
    return sorted(pats)[0] if pats else ""

def parse_showmmr_csv(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            cols = { (c or "").strip().lower(): c for c in (reader.fieldnames or []) }
            def get(r, *names):
                for n in names:
                    if n in cols and cols[n] in r and r[cols[n]] not in (None, ""):
                        return r[cols[n]]
                return ""
            for r in reader:
                try:
                    mid = str(get(r, "matchid", "match_id", "match id")).strip()
                    start = int(str(get(r, "start mmr", "start_mmr", "previous rank", "previous_rank")).strip() or 0)
                    ch = int(str(get(r, "rank change", "rank_change", "change")).strip() or 0)
                    if not mid or not start:
                        continue
                    out.append({
                        "date": str(get(r, "date")).strip(),
                        "unix": int(str(get(r, "unix time", "unix_time", "unix")).strip() or 0),
                        "match_id": mid,
                        "solo": str(get(r, "solo queue", "solo_queue", "solo")).strip(),
                        "hero_id": str(get(r, "heroid", "hero id", "hero_id", "hero")).strip(),
                        "start_mmr": start,
                        "rank_change": ch,
                    })
                except (ValueError, TypeError):
                    continue
    except Exception:
        pass
    return out

def merge_showmmr(show_rows, existing_rows):
    """Мержит ShowMMR-строки в нашу историю по MatchID. Возвращает (новых, всего)."""
    existing_ids = {str(r.get("match_id", "")) for r in existing_rows if str(r.get("match_id", ""))}
    # ShowMMR пишет newest-first; нам нужен chronological oldest-first
    ordered = sorted(show_rows, key=lambda x: (x.get("unix", 0), x.get("match_id", "")))
    added = 0
    for s in ordered:
        mid = str(s["match_id"])
        if mid in existing_ids:
            continue
        end_mmr = int(s["start_mmr"]) + int(s["rank_change"])
        ch = int(s["rank_change"])
        existing_rows.append({
            "date": s.get("date") or datetime.now().strftime("%Y-%m-%d %H:%M"),
            "mmr": end_mmr,
            "change": ch,
            "result": "победа" if ch > 0 else ("поражение" if ch < 0 else "без изменений"),
            "match_id": mid,
            "hero_id": str(s.get("hero_id", "")),
            "kda": "",
        })
        existing_ids.add(mid)
        added += 1
    return added, len(existing_rows)

# ---------- stats ----------
def calc_stats(rows):
    if not rows:
        return dict(current=0, prev=0, last_change=0, peak=0, games=0,
                    wins=0, losses=0, winrate=0.0, streak=0, streak_type="",
                    today_diff=0, week_diff=0)
    current = rows[-1]["mmr"]
    prev = rows[-2]["mmr"] if len(rows) >= 2 else current
    last_change = rows[-1]["change"]
    peak = max(r["mmr"] for r in rows)
    games = max(0, len(rows) - 1)  # первая запись = стартовая точка, без результата
    wins = sum(1 for r in rows[1:] if r["change"] > 0)
    losses = sum(1 for r in rows[1:] if r["change"] < 0)
    winrate = (wins / games * 100) if games else 0.0
    # стрик
    streak = 0
    streak_type = ""
    for r in reversed(rows[1:]):
        if r["change"] == 0:
            continue
        t = "W" if r["change"] > 0 else "L"
        if not streak_type:
            streak_type = t
            streak = 1
        elif t == streak_type:
            streak += 1
        else:
            break
    # сегодня / 7 дней
    today_str = date.today().isoformat()
    today_rows = [r for r in rows if r["date"][:10] == today_str]
    today_diff = sum(r["change"] for r in today_rows)
    week_diff = rows[-1]["mmr"] - rows[max(0, len(rows) - 8)]["mmr"] if len(rows) >= 2 else 0
    return dict(current=current, prev=prev, last_change=last_change, peak=peak,
                games=games, wins=wins, losses=losses, winrate=winrate,
                streak=streak, streak_type=streak_type,
                today_diff=today_diff, week_diff=week_diff)

# ---------- app ----------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Dota 2 MMR Tracker")
        self.geometry("1000x800")
        apply_theme(self)
        self.rows = load_history()
        self.cfg = load_config()
        self.second_win = None
        self.pending_matches = []  # новые матчи с OpenDota, ждут ввода MMR
        self.last_fetched = []
        self.scan_stop = threading.Event()
        self.scan_thread = None
        self.scan_scanning = False
        self.scan_last_raw = None
        self.scan_stable = 0
        self._build_ui()
        self.refresh()
        self.est_matches = []  # последние ~100 матчей с OpenDota (для кривой-оценки)
        self.wl = {"win": 0, "lose": 0}
        # авто-подхват ShowMMR CSV если лежит рядом (тихо, без UI)
        try:
            auto_csv = find_showmmr_csv()
            if auto_csv:
                show_rows = parse_showmmr_csv(auto_csv)
                if show_rows:
                    added, _ = merge_showmmr(show_rows, self.rows)
                    if added:
                        save_history(self.rows)
                        self.refresh()
        except Exception:
            pass
        # авто-проверка при старте и каждые 5 мин
        if self.cfg.get("account_id"):
            self.after(3000, lambda: self.check_new_matches(silent=True))
        self.after(300000, self._auto_loop)
        # тихая проверка обновлений раз в день (только если задан канал)
        try:
            if self.cfg.get("update_url") and self.cfg.get("last_update_check") != date.today().isoformat():
                self.after(15000, lambda: self.check_updates(silent=True))
        except Exception:
            pass

    def _auto_loop(self):
        if self.cfg.get("auto") and self.cfg.get("account_id"):
            self.check_new_matches(silent=True)
        self.after(300000, self._auto_loop)

    def _build_ui(self):
        # верхняя панель
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.lbl_current = ttk.Label(top, text="—", font=("Segoe UI", 28, "bold"))
        self.lbl_current.pack(side="left", padx=(0, 12))
        info = ttk.Frame(top)
        info.pack(side="left", fill="y")
        self.lbl_change = ttk.Label(info, text="", font=("Segoe UI", 14, "bold"))
        self.lbl_change.pack(anchor="w")
        self.lbl_stats = ttk.Label(info, text="", font=("Segoe UI", 10))
        self.lbl_stats.pack(anchor="w")

        btns = ttk.Frame(top)
        btns.pack(side="right")
        ttk.Button(btns, text="🖥 Второй экран", command=self.open_second_screen).pack(fill="x", pady=2)
        ttk.Button(btns, text="⟳ Обновления", command=lambda: self.check_updates(silent=False)).pack(fill="x", pady=2)
        ttk.Button(btns, text="↩ Отменить последнюю", command=self.undo).pack(fill="x", pady=2)

        # (ручной ввод удален: цифры дает сканер экрана или оценка по результатам)

        # автоподтяжка OpenDota
        auto_frame = ttk.LabelFrame(self, text="Матчи • OpenDota", padding=6)
        auto_frame.pack(fill="x", padx=10, pady=4)
        ttk.Label(auto_frame, text="ID:").pack(side="left")
        self.ent_account = ttk.Entry(auto_frame, width=20)
        self.ent_account.pack(side="left", padx=6)
        if self.cfg.get("account_id"):
            self.ent_account.insert(0, self.cfg["account_id"])
        ttk.Button(auto_frame, text="Сохранить", command=self.save_account).pack(side="left", padx=2)
        ttk.Button(auto_frame, text="Проверить матчи", command=lambda: self.check_new_matches(silent=False)).pack(side="left", padx=2)
        self.auto_var = tk.BooleanVar(value=bool(self.cfg.get("auto", True)))
        ttk.Checkbutton(auto_frame, text="Авто каждые 5 мин", variable=self.auto_var,
                        command=self.save_account).pack(side="left", padx=8)
        self.lbl_auto = ttk.Label(auto_frame, text="", font=("Segoe UI", 9), foreground=TH_MUTED)
        self.lbl_auto.pack(side="left", padx=8)
        self.lbl_pending = ttk.Label(self, text="", font=("Segoe UI", 11, "bold"), foreground=TH_GOLD)
        self.lbl_pending.pack(fill="x", padx=12)

        # (блок ShowMMR/GC удален: точные цифры дает сканер, оценку — Dotabuff/OpenDota)

        # Сканер экрана: сам видит цифру MMR, ничего вводить не надо
        scan_frame = ttk.LabelFrame(self, text="Сканер экрана", padding=6)
        scan_frame.pack(fill="x", padx=10, pady=4)
        ttk.Button(scan_frame, text="Выбрать область", command=self.select_region).pack(side="left", padx=2)
        self.btn_scan = ttk.Button(scan_frame, text="▶ Старт", command=self.toggle_scan)
        self.btn_scan.pack(side="left", padx=2)
        ttk.Label(scan_frame, text="Каждые (сек):").pack(side="left", padx=(8, 2))
        self.ent_interval = ttk.Entry(scan_frame, width=5)
        self.ent_interval.pack(side="left")
        self.ent_interval.insert(0, str(self.cfg.get("scan_interval", 15)))
        self.lbl_scan = ttk.Label(scan_frame, text="Область не выбрана", font=("Segoe UI", 9), foreground=TH_MUTED)
        self.lbl_scan.pack(side="left", padx=8)
        if self.cfg.get("scan_region"):
            x, y, w, h = self.cfg["scan_region"]
            self.lbl_scan.config(text=f"✅ Область сохранена: {x},{y} {w}x{h}")

        # середина: график + история
        mid = ttk.Frame(self, padding=10)
        mid.pack(fill="both", expand=True)
        graph_box = ttk.LabelFrame(mid, text="Кривая", padding=5)
        graph_box.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(graph_box, bg=TH_FIELD, highlightthickness=1,
                                highlightbackground=TH_BTN)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw_graph())

        hist_box = ttk.LabelFrame(mid, text="История", padding=5)
        hist_box.pack(side="right", fill="both", expand=False, padx=(10, 0))
        self.hist_list = tk.Listbox(hist_box, width=34, font=("Consolas", 10),
                                    bg=TH_FIELD, fg=TH_FG, selectbackground=TH_BTN_HOVER,
                                    highlightthickness=0, borderwidth=0)
        self.hist_list.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(hist_box, orient="vertical", command=self.hist_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.hist_list.configure(yscrollcommand=scrollbar.set)

        # нижняя панель: последние 10 матчей с изменением MMR
        matches_box = ttk.LabelFrame(self, text="Последние 10", padding=5)
        matches_box.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        cols = ("date", "match", "hero", "kda", "result", "mmr")
        self.tree = ttk.Treeview(matches_box, columns=cols, show="headings", height=10)
        self.tree.heading("date", text="Дата")
        self.tree.heading("match", text="Матч ID")
        self.tree.heading("hero", text="Герой")
        self.tree.heading("kda", text="K/D/A")
        self.tree.heading("result", text="Результат")
        self.tree.heading("mmr", text="MMR ±")
        self.tree.column("date", width=110)
        self.tree.column("match", width=100)
        self.tree.column("hero", width=50)
        self.tree.column("kda", width=80)
        self.tree.column("result", width=90)
        self.tree.column("mmr", width=70)
        self.tree.pack(fill="both", expand=True, side="left")
        tscroll = ttk.Scrollbar(matches_box, orient="vertical", command=self.tree.yview)
        tscroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tscroll.set)

    # --- автоподтяжка ---
    def save_account(self):
        raw = self.ent_account.get().strip()
        acc = parse_account_id(raw)
        if raw and not acc:
            messagebox.showinfo(
                "Где взять ID",
                "Не смог распознать ID.\n\n"
                "Варианты:\n"
                "1. Зайди на dotabuff.com / opendota.com / stratz.com, войди через Steam\n"
                "2. Открой свой профиль — в адресе будет /players/ЧИСЛО — это и есть Account ID\n"
                "3. Или скинь ссылку на Steam-профиль вида steamcommunity.com/profiles/76561... — я сам пересчитаю\n"
                "4. Вставь сюда число или ссылку целиком и нажми Сохранить")
            return
        self.cfg["account_id"] = acc or ""
        self.cfg["auto"] = bool(self.auto_var.get())
        save_config(self.cfg)
        self.lbl_auto.config(text=f"ID: {acc} сохранен" if acc else "ID очищен")
        if acc:
            self.check_new_matches(silent=False)

    def check_new_matches(self, silent=True):
        acc = self.cfg.get("account_id", "")
        if not acc:
            if not silent:
                messagebox.showinfo("Нет ID", "Сначала вставь Account ID или ссылку на профиль.")
            return
        self.lbl_auto.config(text="Проверяю OpenDota…")
        threading.Thread(target=self._fetch_worker, args=(acc, silent), daemon=True).start()

    def _fetch_worker(self, acc, silent):
        matches, err = fetch_recent_matches(acc, limit=10)
        hist, herr = fetch_match_history(acc, limit=100)
        win, lose = fetch_wl(acc)
        if herr:
            hist = []
        self.after(0, lambda: self._fetch_done(matches, err, hist, win, lose, silent))

    def render_matches(self):
        """Отрисовать последние 10 матчей + подставить изменение MMR из истории."""
        for i in self.tree.get_children():
            self.tree.delete(i)
        if not self.last_fetched:
            return
        cmap = match_id_to_change(self.rows)
        for m in self.last_fetched[:10]:
            mid = str(m.get("match_id", ""))
            try:
                ts = datetime.fromtimestamp(int(m.get("start_time", 0))).strftime("%m-%d %H:%M")
            except Exception:
                ts = ""
            w = match_is_win(m)
            res = "победа ✅" if w else ("поражение ❌" if w is False else "?")
            kda = f"{m.get('kills', '?')}/{m.get('deaths', '?')}/{m.get('assists', '?')}"
            ch = cmap.get(mid)
            if ch is None:
                # оценки по результатам Dotabuff: победа ~+25, поражение ~-25
                mmr_txt = f"+{EST_STEP}~" if w is True else (f"-{EST_STEP}~" if w is False else "—")
            else:
                mmr_txt = f"+{ch}" if ch > 0 else (str(ch) if ch < 0 else "старт")
            tag = "win" if w else ("loss" if w is False else "")
            self.tree.insert("", "end", values=(ts, mid, hero_short(m.get("hero_id", "?")), kda, res, mmr_txt), tags=(tag,))
        try:
            self.tree.tag_configure("win", foreground=TH_GREEN)
            self.tree.tag_configure("loss", foreground=TH_RED)
        except Exception:
            pass

    def _fetch_done(self, matches, err, hist, win, lose, silent):
        if err:
            self.lbl_auto.config(text=f"OpenDota недоступен ({err[:60]})")
            if not silent:
                messagebox.showwarning("OpenDota", f"Не получилось получить матчи:\n{err}")
            return
        if not matches:
            self.lbl_auto.config(text="Матчи не найдены. Проверь ID и что профиль открыт (Expose public match data).")
            return
        self.last_fetched = matches
        # оценка кривой по результатам (Dotabuff = те же матчи)
        self.est_matches = build_est_curve(hist if hist else matches)
        self.wl = {"win": win, "lose": lose}
        newest_id = matches[0].get("match_id", 0)
        last_id = int(self.cfg.get("last_match_id", 0) or 0)
        if last_id == 0:
            # первый запуск с ID — запоминаем, не спамим
            self.cfg["last_match_id"] = newest_id
            save_config(self.cfg)
            self.lbl_auto.config(text=f"Ок, слежу за {len(matches)} посл. матчами. Новый матч покажу здесь.")
            self._render_pending()
            self.render_matches()
            self.refresh()
            return
        new = [m for m in matches if int(m.get("match_id", 0)) > last_id]
        # иногда история сдвигается — берем сверху до last_id
        if not new:
            self.lbl_auto.config(text=f"Новых матчей нет. Последний: {newest_id}")
            self.pending_matches = []
            self._render_pending()
            self.render_matches()
            self.refresh()
            return
        self.pending_matches = sorted(new, key=lambda m: int(m.get("match_id", 0)))
        parts = []
        for m in self.pending_matches:
            w = match_is_win(m)
            res = "победа ✅" if w else ("поражение ❌" if w is False else "?")
            parts.append(f"{m.get('match_id')} — {res}")
        self.lbl_auto.config(text=f"Новых матчей: {len(new)}")
        self._render_pending()
        self.render_matches()
        self.refresh()
        # всплывашка только если окно активно и не silent-спам
        if not silent or len(new) <= 2:
            pass  # баннер снизу уже виден, не надоедаем popup

    def _render_pending(self):
        if not self.pending_matches:
            self.lbl_pending.config(text="")
            return
        lines = []
        for m in self.pending_matches:
            w = match_is_win(m)
            res = "ПОБЕДА ✅" if w else ("ПОРАЖЕНИЕ ❌" if w is False else "матч")
            kda = f"{m.get('kills', '?')}/{m.get('deaths', '?')}/{m.get('assists', '?')}"
            lines.append(f"{res} ({kda}, {hero_short(m.get('hero_id', '?'))})")
        hint = "  →  включи сканер экрана: он сам считает цифру MMR"
        self.lbl_pending.config(text="Найден новый матч: " + " | ".join(lines) + hint)

    # --- сканер экрана ---
    def select_region(self):
        """Оверлей на весь виртуальный экран: тянешь рамку по цифре MMR."""
        ov = tk.Toplevel(self)
        try:
            vw = self.winfo_vrootwidth()
            vh = self.winfo_vrootheight()
            vx = self.winfo_vrootx()
            vy = self.winfo_vrooty()
        except Exception:
            vw, vh, vx, vy = 1920, 1080, 0, 0
        ov.geometry(f"{vw}x{vh}+{vx}+{vy}")
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.3)
        cv = tk.Canvas(ov, bg="black", highlightthickness=0)
        cv.pack(fill="both", expand=True)
        cv.create_text(vw // 2, 40, text="Рамку строго по цифре «Рейтинг» в профиле (напр. 2 315). Enter — сохранить, Esc — отмена.",
                       fill="white", font=("Segoe UI", 16))
        rect = {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "id": None}

        def on_down(e):
            rect["x0"], rect["y0"] = e.x, e.y
            if rect["id"]:
                cv.delete(rect["id"])
            rect["id"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="lime", width=3)

        def on_move(e):
            rect["x1"], rect["y1"] = e.x, e.y
            if rect["id"]:
                cv.coords(rect["id"], rect["x0"], rect["y0"], e.x, e.y)

        def on_done(e=None):
            x = min(rect["x0"], rect["x1"]) + vx
            y = min(rect["y0"], rect["y1"]) + vy
            w = abs(rect["x1"] - rect["x0"])
            h = abs(rect["y1"] - rect["y0"])
            ov.destroy()
            if w < 20 or h < 10:
                messagebox.showinfo("Область", "Слишком маленькая рамка — попробуй еще раз.")
                return
            self.cfg["scan_region"] = [x, y, w, h]
            save_config(self.cfg)
            self.lbl_scan.config(text=f"✅ Область сохранена: {x},{y} {w}x{h}")
            messagebox.showinfo("Область сохранена", f"Область {w}x{h} сохранена.\nЖми «Старт».")

        cv.bind("<Button-1>", on_down)
        cv.bind("<B1-Motion>", on_move)
        cv.bind("<Double-Button-1>", on_done)
        ov.bind("<Return>", on_done)
        ov.bind("<Escape>", lambda e: ov.destroy())
        ov.focus_force()

    def toggle_scan(self):
        if self.scan_scanning:
            self.scan_stop.set()
            self.scan_scanning = False
            self.btn_scan.config(text="▶ Старт")
            self.lbl_scan.config(text="Скан остановлен")
            return
        if not self.cfg.get("scan_region"):
            messagebox.showinfo("Скан", "Сначала выбери область с MMR (кнопка 1️⃣).")
            return
        try:
            iv = int(self.ent_interval.get().strip() or 15)
            iv = max(5, min(300, iv))
        except ValueError:
            iv = 15
        self.cfg["scan_interval"] = iv
        save_config(self.cfg)
        self.scan_stop.clear()
        self.scan_scanning = True
        self.scan_last_raw = None
        self.scan_stable = 0
        self.btn_scan.config(text="⏸ Стоп")
        self.lbl_scan.config(text="Загрузка OCR…")
        self.scan_thread = threading.Thread(target=self._scan_loop, args=(iv,), daemon=True)
        self.scan_thread.start()

    def _scan_loop(self, interval):
        try:
            get_ocr_engine()  # греем модель
        except Exception as e:
            err = str(e)[:300]
            self.after(0, lambda: self.lbl_scan.config(text=f"OCR не загрузился: {err}"))
            self.after(0, lambda e=e: messagebox.showwarning(
                "Сканер не запустился",
                f"OCR-движок не загрузился:\n{e}\n\n"
                "Что проверить:\n"
                "1. Интернет при первом запуске (модель докачивается 1 раз)\n"
                "2. Антивирус не удалил файлы рядом с программой\n"
                "3. Скинь этот текст разработчику"))
            self.after(0, lambda: self.toggle_scan())
            return
        self.after(0, lambda: self.lbl_scan.config(text="Сканирую… наведи клиент Dota с цифрой MMR"))
        while not self.scan_stop.wait(interval):
            try:
                img = capture_region(self.cfg["scan_region"])
                text = ocr_image_to_text(img)
                val = parse_mmr_text(text)
            except Exception as e:
                self.after(0, lambda e=e: self.lbl_scan.config(text=f"Ошибка кадра: {e}"))
                continue
            self.after(0, lambda v=val, t=text: self._scan_tick(v, t))

    def _scan_tick(self, val, text):
        if val is None:
            self.scan_last_raw = None
            self.scan_stable = 0
            self.lbl_scan.config(text=f"Не вижу цифр ({(text or '—')[:30]}). Открой профиль Dota с MMR.")
            return
        if val == self.scan_last_raw:
            self.scan_stable += 1
        else:
            self.scan_last_raw = val
            self.scan_stable = 1
        current = self.rows[-1]["mmr"] if self.rows else None
        self.lbl_scan.config(text=f"Вижу: {val} (стабильно {self.scan_stable}/2), у нас: {current}")
        if self.scan_stable >= 2 and (current is None or val != current):
            self.scan_stable = 0  # чтобы не дублировать
            self._auto_add_scan(val)

    def _auto_add_scan(self, mmr):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        if not self.rows:
            change, result = 0, "старт (скан)"
        else:
            change = mmr - self.rows[-1]["mmr"]
            if change == 0:
                return
            if abs(change) > 500:
                self.lbl_scan.config(text=f"Пропуск: скачок {change} (похоже на ошибку чтения)")
                return
            result = "победа" if change > 0 else "поражение"
        match_id, hero_id, kda = "", "", ""
        if self.pending_matches:
            newest = max(self.pending_matches, key=lambda m: int(m.get("match_id", 0)))
            match_id = str(newest.get("match_id", ""))
            hero_id = str(newest.get("hero_id", ""))
            kda = f"{newest.get('kills', '?')}/{newest.get('deaths', '?')}/{newest.get('assists', '?')}"
        elif self.last_fetched:
            newest_id = str(self.last_fetched[0].get("match_id", ""))
            existing = {str(r.get("match_id", "")) for r in self.rows}
            if newest_id and newest_id not in existing:
                m0 = self.last_fetched[0]
                match_id, hero_id = newest_id, str(m0.get("hero_id", ""))
                kda = f"{m0.get('kills', '?')}/{m0.get('deaths', '?')}/{m0.get('assists', '?')}"
        self.rows.append({"date": now, "mmr": mmr, "change": change, "result": result + " [скан]",
                          "match_id": match_id, "hero_id": hero_id, "kda": kda})
        save_history(self.rows)
        if self.last_fetched:
            try:
                self.cfg["last_match_id"] = int(self.last_fetched[0].get("match_id", 0)) or int(self.cfg.get("last_match_id", 0))
                save_config(self.cfg)
            except Exception:
                pass
            self.pending_matches = []
            self._render_pending()
        self.refresh()
        sign = f"+{change}" if change > 0 else str(change)
        self.lbl_scan.config(text=f"✅ Записал {mmr} ({sign}). Продолжаю сканировать…")

    # --- обновления ---
    def check_updates(self, silent=True):
        url = (self.cfg.get("update_url") or "").strip()
        if not url:
            if silent:
                return
            from tkinter import simpledialog
            url = simpledialog.askstring(
                "Канал обновлений",
                "Вставь ссылку на manifest.json\n(из релиза или своего сервера):",
                parent=self)
            if not url:
                return
            self.cfg["update_url"] = url.strip()
            save_config(self.cfg)
        threading.Thread(target=self._update_worker, args=(url, silent), daemon=True).start()

    def _update_worker(self, url, silent):
        try:
            man = fetch_manifest(url)
            remote = int(man.get("version", 0))
        except Exception as e:
            if not silent:
                self.after(0, lambda e=e: messagebox.showwarning("Обновления", f"Не смог проверить:\n{e}"))
            return
        try:
            self.cfg["last_update_check"] = date.today().isoformat()
            save_config(self.cfg)
        except Exception:
            pass
        if remote <= APP_VERSION:
            if not silent:
                self.after(0, lambda: messagebox.showinfo("Обновления", f"У тебя последняя версия ({APP_VERSION})."))
            return
        self.after(0, lambda: self._offer_update(man, remote))

    def _offer_update(self, man, remote):
        notes = str(man.get("notes", ""))
        if not messagebox.askyesno("Доступно обновление",
                                    f"Версия {remote} (у тебя {APP_VERSION}).\n{notes}\n\nСкачать и установить?"):
            return
        self.lbl_auto.config(text="Качаю обновление…")
        threading.Thread(target=self._download_worker, args=(man.get("url", ""),), daemon=True).start()

    def _download_worker(self, zip_url):
        try:
            import tempfile
            import zipfile
            import subprocess
            tmp = tempfile.mkdtemp(prefix="mmr_upd_")
            zp = os.path.join(tmp, "upd.zip")
            download_file(zip_url, zp)
            if getattr(sys, "frozen", False):
                with zipfile.ZipFile(zp) as z:
                    names = z.namelist()
                    exe_name = next((n for n in names if n.lower().endswith(".exe")), None)
                    if not exe_name:
                        raise RuntimeError("в архиве нет exe")
                    new_exe = os.path.join(tmp, "new.exe")
                    with z.open(exe_name) as src, open(new_exe, "wb") as dst:
                        dst.write(src.read())
                cur = os.path.abspath(sys.executable)
                bat = os.path.join(tmp, "apply.bat")
                pid = os.getpid()
                with open(bat, "w") as f:
                    f.write(f"@echo off\n:wait\n"
                            f'tasklist /FI "PID eq {pid}" | find "{pid}" >nul\n'
                            f"if not errorlevel 1 (timeout /t 1 >nul & goto wait)\n"
                            f'copy /Y "{new_exe}" "{cur}" >nul\n'
                            f'start "" "{cur}"\n'
                            f'rmdir /S /Q "{tmp}"\n')
                subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000)
                self.after(0, lambda: self.destroy())
            else:
                with zipfile.ZipFile(zp) as z:
                    names = z.namelist()
                    py_name = next((n for n in names if n.endswith("dota_mmr_tracker.py")), None)
                    if not py_name:
                        raise RuntimeError("в архиве нет dota_mmr_tracker.py")
                    data = z.read(py_name)
                cur = os.path.abspath(__file__)
                with open(cur, "wb") as f:
                    f.write(data)
                self.after(0, lambda: self._restart_py())
        except Exception as e:
            self.after(0, lambda e=e: messagebox.showwarning("Обновление", f"Не получилось:\n{e}"))
            self.after(0, lambda: self.lbl_auto.config(text=""))

    def _restart_py(self):
        try:
            os.execv(sys.executable, [sys.executable, os.path.abspath(__file__)])
        except Exception:
            self.destroy()

    def undo(self):
        if not self.rows:
            return
        self.rows.pop()
        save_history(self.rows)
        self.refresh()

    def est_stats(self):
        """Статистика из результатов Dotabuff/OpenDota (без единой введенной цифры)."""
        est = getattr(self, "est_matches", []) or []
        wl = getattr(self, "wl", {"win": 0, "lose": 0})
        wins = sum(1 for e in est if e["win"] is True)
        losses = sum(1 for e in est if e["win"] is False)
        games = wins + losses
        total_w, total_l = wl.get("win", 0), wl.get("lose", 0)
        base_w, base_l = (total_w, total_l) if (total_w + total_l) else (wins, losses)
        winrate = (base_w / (base_w + base_l) * 100) if (base_w + base_l) else 0.0
        streak, stype = 0, ""
        for e in reversed(est):
            if e["win"] is None:
                continue
            t = "W" if e["win"] else "L"
            if not stype:
                stype, streak = t, 1
            elif t == stype:
                streak += 1
            else:
                break
        last_step = 0
        for e in reversed(est):
            if e["win"] is True:
                last_step = EST_STEP
                break
            elif e["win"] is False:
                last_step = -EST_STEP
                break
        return dict(wins=base_w, losses=base_l, winrate=winrate, games=games,
                    streak=streak, streak_type=stype, last_step=last_step,
                    cum_last=est[-1]["cum"] if est else 0)

    def refresh(self):
        if self.rows:
            s = calc_stats(self.rows)
            self.lbl_current.config(text=str(s["current"]))
            ch = s["last_change"]
            if ch > 0:
                self.lbl_change.config(text=f"+{ch}  победа ✅", foreground=TH_GREEN)
            elif ch < 0:
                self.lbl_change.config(text=f"{ch}  поражение ❌", foreground=TH_RED)
            else:
                self.lbl_change.config(text="старт", foreground=TH_MUTED)
            streak_txt = f"{s['streak']}{'W' if s['streak_type']=='W' else 'L'}" if s["streak"] else "—"
            self.lbl_stats.config(
                text=(f"Матчей: {s['games']}  |  W {s['wins']} / L {s['losses']}  |  Винрейт {s['winrate']:.1f}%\n"
                      f"Пик: {s['peak']}  |  Стрик: {streak_txt}  |  Сегодня {s['today_diff']:+d}"))
            # история: точные записи сканера
            self.hist_list.delete(0, "end")
            for i in range(len(self.rows) - 1, max(0, len(self.rows) - 60) - 1, -1):
                r = self.rows[i]
                if i == 0:
                    self.hist_list.insert("end", f"{r['date'][:16]}  СТАРТ {r['mmr']}")
                else:
                    prev = self.rows[i - 1]["mmr"]
                    sign = f"+{r['change']}" if r["change"] > 0 else str(r["change"])
                    mark = "✅" if r["change"] > 0 else "❌"
                    self.hist_list.insert("end", f"{r['date'][:16]} {prev}→{r['mmr']} ({sign}) {mark}")
        elif getattr(self, "est_matches", None):
            e = self.est_stats()
            self.lbl_current.config(text="~")
            st = e["last_step"]
            if st > 0:
                self.lbl_change.config(text=f"~+{st}  победа ✅ (оценка)", foreground=TH_GREEN)
            elif st < 0:
                self.lbl_change.config(text=f"~{st}  поражение ❌ (оценка)", foreground=TH_RED)
            else:
                self.lbl_change.config(text="жду матчи…", foreground=TH_MUTED)
            streak_txt = f"{e['streak']}{e['streak_type']}" if e["streak"] else "—"
            self.lbl_stats.config(
                text=(f"Матчей: {e['games']}  |  W {e['wins']} / L {e['losses']}  |  Винрейт {e['winrate']:.1f}%\n"
                      f"Стрик: {streak_txt}"))
            # история: оценка по результатам (~)
            self.hist_list.delete(0, "end")
            for m in reversed(self.est_matches[-60:]):
                mark = "✅" if m["win"] is True else ("❌" if m["win"] is False else "?")
                step = f"~+{EST_STEP}" if m["win"] is True else (f"~-{EST_STEP}" if m["win"] is False else "~?")
                self.hist_list.insert("end", f"{m['date']}  {mark} {step}  ({hero_short(m['hero_id'])})")
        else:
            self.lbl_current.config(text="—")
            self.lbl_change.config(text="Загружаю матчи…")
            self.lbl_stats.config(text="Вставь Account ID и нажми «Проверить матчи»")
            self.hist_list.delete(0, "end")
        self.draw_graph()
        try:
            self.render_matches()
        except Exception:
            pass
        if self.second_win and self.second_win.winfo_exists():
            self.update_second_screen()

    def draw_graph(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 50 or h < 50:
            return
        if len(self.rows) >= 2:
            # точная кривая сканера
            vals = [r["mmr"] for r in self.rows[-20:]]
            note, note_color = "точные цифры сканера", "#7f95b3"
            fmt = lambda v: str(v)
        elif getattr(self, "est_matches", None) and len(self.est_matches) >= 2:
            # окно 20 матчей, якорь — текущий MMR (со сканера), дальше ±25
            win = self.est_matches[-20:]
            anchor = self.rows[-1]["mmr"] if self.rows else None
            if anchor is None:
                vals = [e["cum"] for e in win]
                note = "относительные очки: 0 = начало окна (сканер даст точные)"
                fmt = lambda v: f"+{v}" if v > 0 else str(v)
            else:
                base = self.est_matches[-1]["cum"]
                vals = [anchor + (e["cum"] - base) for e in win]
                note = f"от текущего {anchor} (сканер), дальше ±25 за игру"
                fmt = lambda v: str(v)
            note_color = "#57c7ff"
        else:
            c.create_text(w // 2, h // 2, text="Нажми «Проверить матчи» — построю кривую",
                          fill="#7f95b3", font=("Segoe UI", 11))
            return
        mn, mx = min(vals), max(vals)
        if mn == mx:
            mn -= 25
            mx += 25
        pad = 20
        pts = []
        for i, v in enumerate(vals):
            x = pad + i * (w - 2 * pad) / (len(vals) - 1)
            y = h - pad - (v - mn) / (mx - mn) * (h - 2 * pad)
            pts.append((x, y))
        # сетка min/max
        c.create_text(pad, 12, text=fmt(mx), anchor="w", fill=TH_MUTED, font=("Segoe UI", 9))
        c.create_text(pad, h - 8, text=fmt(mn), anchor="w", fill=TH_MUTED, font=("Segoe UI", 9))
        # линия
        for i in range(len(pts) - 1):
            color = TH_GREEN if vals[i + 1] >= vals[i] else TH_RED
            c.create_line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], width=2, fill=color)
        for x, y in pts:
            c.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#cfe0ff", outline="")
        c.create_text(pts[-1][0] - 5, pts[-1][1] - 12, text=fmt(vals[-1]),
                      anchor="se", font=("Segoe UI", 10, "bold"))
        try:
            c.create_text(w // 2, h - 8, text=note, fill=note_color, font=("Segoe UI", 9))
        except Exception:
            pass

    # --- второй экран ---
    def open_second_screen(self):
        if self.second_win and self.second_win.winfo_exists():
            self.second_win.lift()
            return
        win = tk.Toplevel(self)
        win.title("MMR — второй экран")
        win.geometry("500x350")
        try:
            win.configure(bg=TH_BG)
        except Exception:
            pass
        self.second_win = win
        self.s_current = ttk.Label(win, text="—", font=("Segoe UI", 90, "bold"))
        self.s_current.pack(pady=(20, 0))
        self.s_change = ttk.Label(win, text="", font=("Segoe UI", 28, "bold"))
        self.s_change.pack()
        self.s_sub = ttk.Label(win, text="", font=("Segoe UI", 14), foreground=TH_MUTED)
        self.s_sub.pack(pady=10)
        row = ttk.Frame(win)
        row.pack(pady=10)
        self.topmost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Поверх всех окон", variable=self.topmost_var,
                        command=lambda: win.attributes("-topmost", self.topmost_var.get())).pack(side="left", padx=10)
        ttk.Label(row, text="Перетащи это окно на 2-й монитор", font=("Segoe UI", 10)).pack(side="left")
        win.attributes("-topmost", True)
        self.update_second_screen()

    def update_second_screen(self):
        s = calc_stats(self.rows)
        if not self.rows:
            e = self.est_stats() if getattr(self, "est_matches", None) else None
            if e and e["games"]:
                self.s_current.config(text="~")
                st = e["last_step"]
                self.s_change.config(text=f"~+{st}" if st > 0 else (f"~{st}" if st < 0 else "—"),
                                     foreground=TH_GREEN if st > 0 else (TH_RED if st < 0 else TH_MUTED))
                self.s_sub.config(text=f"W {e['wins']} / L {e['losses']}  •  {e['winrate']:.0f}%  •  оценка")
            else:
                self.s_current.config(text="—")
                self.s_change.config(text="Нет данных")
                self.s_sub.config(text="Нажми «Проверить матчи»")
            return
        self.s_current.config(text=str(s["current"]))
        ch = s["last_change"]
        if ch > 0:
            self.s_change.config(text=f"+{ch}", foreground=TH_GREEN)
        elif ch < 0:
            self.s_change.config(text=str(ch), foreground=TH_RED)
        else:
            self.s_change.config(text="старт", foreground=TH_MUTED)
        self.s_sub.config(text=f"W {s['wins']} / L {s['losses']}  •  {s['winrate']:.0f}%  •  Сегодня {s['today_diff']:+d}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
