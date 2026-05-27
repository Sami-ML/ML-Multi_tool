#!/usr/bin/env python3
from __future__ import annotations

import cmath
import colorsys
import hashlib
import math
import os
import random
import re
import sqlite3
import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from tkinter import messagebox, ttk

import matplotlib.pyplot as plt
from matplotlib import colors as mcolors
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.ticker import ScalarFormatter

DB_PATH = os.path.join(os.path.dirname(__file__), "multitool_users.db")
LANG_DB_PATH = os.path.join(os.path.dirname(__file__), "lang.db")
TOKEN_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")

_color_items = [(name, hx.upper()) for name, hx in mcolors.CSS4_COLORS.items()]
_color_items.extend((name.replace("xkcd:", "xkcd_"), hx.upper()) for name, hx in mcolors.XKCD_COLORS.items())
_seen = set()
PRESET_COLORS_1200 = []
for _name, _hx in _color_items:
    key = (_name.lower(), _hx)
    if key in _seen:
        continue
    _seen.add(key)
    PRESET_COLORS_1200.append((_name, _hx))
    if len(PRESET_COLORS_1200) >= 1200:
        break


def get_conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS calc_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                expression TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS color_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                rgb TEXT NOT NULL,
                hex TEXT NOT NULL,
                hsl TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )




def get_setting(key: str, default: str) -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute("INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def init_lang_db() -> None:
    with sqlite3.connect(LANG_DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS language_state (id INTEGER PRIMARY KEY CHECK (id=1), code TEXT NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO language_state(id, code) VALUES(1, 'en')")


def get_lang() -> str:
    with sqlite3.connect(LANG_DB_PATH) as conn:
        row = conn.execute("SELECT code FROM language_state WHERE id=1").fetchone()
    return row[0] if row and row[0] in {"en", "fa"} else "en"


def set_lang(code: str) -> None:
    code = code if code in {"en", "fa"} else "en"
    with sqlite3.connect(LANG_DB_PATH) as conn:
        conn.execute("INSERT INTO language_state(id, code) VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET code=excluded.code", (code,))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_user(username: str, password: str) -> bool:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                (username.strip(), hash_password(password), datetime.now().isoformat()),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username: str, password: str) -> bool:
    with get_conn() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE username=?", (username.strip(),)).fetchone()
    return bool(row and row[0] == hash_password(password))


def add_calc_history(username: str, expr: str, result: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO calc_history(username,expression,result,created_at) VALUES (?,?,?,?)",
            (username, expr, result, datetime.now().isoformat(timespec="seconds")),
        )


def add_color_history(username: str, rgb: str, hx: str, hsl: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO color_history(username,rgb,hex,hsl,created_at) VALUES (?,?,?,?,?)",
            (username, rgb, hx, hsl, datetime.now().isoformat(timespec="seconds")),
        )


def get_calc_history(username: str, limit: int = 40) -> list[tuple[str, str, str]]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT created_at, expression, result FROM calc_history WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()


def get_color_history(username: str, limit: int = 40) -> list[tuple[str, str, str, str]]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT created_at, rgb, hex, hsl FROM color_history WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit),
        ).fetchall()


UNIT_CATEGORIES: dict[str, dict[str, tuple[float, float]]] = {
    "Length": {"meter": (1.0, 0.0), "kilometer": (1000.0, 0.0), "centimeter": (0.01, 0.0), "millimeter": (0.001, 0.0), "inch": (0.0254, 0.0), "foot": (0.3048, 0.0), "mile": (1609.344, 0.0)},
    "Mass": {"kilogram": (1.0, 0.0), "gram": (0.001, 0.0), "pound": (0.45359237, 0.0), "ounce": (0.028349523125, 0.0)},
    "Time": {"second": (1.0, 0.0), "minute": (60.0, 0.0), "hour": (3600.0, 0.0), "day": (86400.0, 0.0)},
    "Area": {"sq_meter": (1.0, 0.0), "sq_foot": (0.09290304, 0.0), "acre": (4046.8564224, 0.0)},
    "Volume": {"cubic_meter": (1.0, 0.0), "liter": (0.001, 0.0), "gallon_us": (0.003785411784, 0.0)},
    "Speed": {"m_per_s": (1.0, 0.0), "km_per_h": (0.2777777778, 0.0), "mile_per_h": (0.44704, 0.0)},
    "Acceleration": {"m_per_s2": (1.0, 0.0), "g": (9.80665, 0.0)},
    "Force": {"newton": (1.0, 0.0), "pound_force": (4.4482216152605, 0.0)},
    "Energy": {"joule": (1.0, 0.0), "calorie": (4.184, 0.0), "btu": (1055.05585262, 0.0)},
    "Power": {"watt": (1.0, 0.0), "horsepower": (745.699871582, 0.0)},
    "Pressure": {"pascal": (1.0, 0.0), "bar": (100000.0, 0.0), "atm": (101325.0, 0.0)},
    "Temperature": {"kelvin": (1.0, 0.0), "celsius": (1.0, 273.15), "fahrenheit": (5.0 / 9.0, 255.3722222222)},
    "Angle": {"radian": (1.0, 0.0), "degree": (math.pi / 180.0, 0.0)},
    "Data": {"byte": (1.0, 0.0), "kilobyte": (1000.0, 0.0), "megabyte": (1e6, 0.0)},
    "Frequency": {"hertz": (1.0, 0.0), "rpm": (1 / 60.0, 0.0)},
    "Fuel Economy": {"km_per_l": (1.0, 0.0), "liter_per_100km": (-1.0, 0.0)},
    "Viscosity": {"pa_s": (1.0, 0.0), "poise": (0.1, 0.0)},
    "Magnetic Flux": {"weber": (1.0, 0.0), "maxwell": (1e-8, 0.0)},
    "Electric Charge": {"coulomb": (1.0, 0.0), "ampere_hour": (3600.0, 0.0)},
    "Electric Current": {"ampere": (1.0, 0.0), "milliampere": (0.001, 0.0)},
    "Electric Potential": {"volt": (1.0, 0.0), "kilovolt": (1000.0, 0.0)},
    "Resistance": {"ohm": (1.0, 0.0), "kilohm": (1000.0, 0.0)},
    "Inductance": {"henry": (1.0, 0.0), "millihenry": (0.001, 0.0)},
    "Capacitance": {"farad": (1.0, 0.0), "microfarad": (1e-6, 0.0)},
}


CATEGORY_FA = {
    "Length": "طول",
    "Mass": "جرم",
    "Time": "زمان",
    "Area": "مساحت",
    "Volume": "حجم",
    "Speed": "سرعت",
    "Acceleration": "شتاب",
    "Force": "نیرو",
    "Energy": "انرژی",
    "Power": "توان",
    "Pressure": "فشار",
    "Temperature": "دما",
    "Angle": "زاویه",
    "Data": "داده",
    "Frequency": "فرکانس",
    "Fuel Economy": "مصرف سوخت",
    "Viscosity": "گرانروی",
    "Magnetic Flux": "شار مغناطیسی",
    "Electric Charge": "بار الکتریکی",
    "Electric Current": "جریان الکتریکی",
    "Electric Potential": "پتانسیل الکتریکی",
    "Resistance": "مقاومت",
    "Inductance": "اندوکتانس",
    "Capacitance": "ظرفیت خازنی",
}

UNIT_FA = {
    "meter": "متر",
    "kilometer": "کیلومتر",
    "centimeter": "سانتی‌متر",
    "millimeter": "میلی‌متر",
    "inch": "اینچ",
    "foot": "فوت",
    "mile": "مایل",
    "kilogram": "کیلوگرم",
    "gram": "گرم",
    "pound": "پوند",
    "ounce": "اونس",
    "second": "ثانیه",
    "minute": "دقیقه",
    "hour": "ساعت",
    "day": "روز",
    "sq_meter": "متر مربع",
    "sq_foot": "فوت مربع",
    "acre": "ایکر",
    "cubic_meter": "متر مکعب",
    "liter": "لیتر",
    "gallon_us": "گالن آمریکا",
    "m_per_s": "متر بر ثانیه",
    "km_per_h": "کیلومتر بر ساعت",
    "mile_per_h": "مایل بر ساعت",
    "m_per_s2": "متر بر مجذور ثانیه",
    "g": "جی",
    "newton": "نیوتن",
    "pound_force": "پوند-نیرو",
    "joule": "ژول",
    "calorie": "کالری",
    "btu": "بی‌تی‌یو",
    "watt": "وات",
    "horsepower": "اسب بخار",
    "pascal": "پاسکال",
    "bar": "بار",
    "atm": "اتمسفر",
    "kelvin": "کلوین",
    "celsius": "سلسیوس",
    "fahrenheit": "فارنهایت",
    "radian": "رادیان",
    "degree": "درجه",
    "byte": "بایت",
    "kilobyte": "کیلوبایت",
    "megabyte": "مگابایت",
    "hertz": "هرتز",
    "rpm": "دور بر دقیقه",
    "km_per_l": "کیلومتر بر لیتر",
    "liter_per_100km": "لیتر بر ۱۰۰ کیلومتر",
    "pa_s": "پاسکال-ثانیه",
    "poise": "پواز",
    "weber": "وبر",
    "maxwell": "مکسول",
    "coulomb": "کولن",
    "ampere_hour": "آمپر-ساعت",
    "ampere": "آمپر",
    "milliampere": "میلی‌آمپر",
    "volt": "ولت",
    "kilovolt": "کیلوولت",
    "ohm": "اهم",
    "kilohm": "کیلو اهم",
    "henry": "هنری",
    "millihenry": "میلی‌هنری",
    "farad": "فاراد",
    "microfarad": "میکروفاراد",
}


@dataclass
class FormulaSet:
    name: str
    variables: tuple[str, ...]
    equations: tuple[str, ...]

PHYSICS_FORMULAS = [
    FormulaSet("Kinematics_سینماتیک" , ("u", "v", "a", "t", "s"), ("v=u+a*t", "s=u*t+0.5*a*t*t", "v*v=u*u+2*a*s", "s=(u+v)*t/2")),
    FormulaSet("Dynamics_دینامیک" , ("F", "m", "a", "p", "v"), ("F=m*a", "p=m*v")),
    FormulaSet("Work & Power_کار و توان" , ("W", "F", "d", "P", "t"), ("W=F*d", "P=W/t")),
    FormulaSet("Energy_انرژی" , ("KE", "PE", "m", "v", "g", "h"), ("KE=0.5*m*v*v", "PE=m*g*h")),
    FormulaSet("Gravitation_گرانش" , ("F", "G", "m1", "m2", "r"), ("F=G*m1*m2/(r*r)",)),
    FormulaSet("Circular Motion_حرکت دوار" , ("v", "r", "T", "f", "ac", "omega"), ("v=2*pi*r/T", "f=1/T", "ac=v*v/r", "omega=2*pi*f")),
    FormulaSet("Projectile_پرتابه" , ("R", "u", "theta", "g"), ("R=u*u*sin(2*theta)/g",)),
    FormulaSet("SHM_نوسان ساده", ("x", "A", "w", "t", "T", "f"), ("x=A*cos(w*t)", "T=1/f", "w=2*pi*f")),
    FormulaSet("Waves_موج",  ("v", "f", "lambda_", "T"), ("v=f*lambda_", "T=1/f")),
    FormulaSet("Electricity_برق", ("V", "I", "R", "P", "Q", "t", "C"), ("V=I*R", "P=V*I", "Q=I*t", "C=Q/V", "P=I*I*R", "P=V*V/R")),
    FormulaSet("Capacitor_خازن",  ("Q", "C", "V", "U"), ("Q=C*V", "U=0.5*C*V*V")),
    FormulaSet("Inductor_سلف", ("U", "L", "I"), ("U=0.5*L*I*I",)),
    FormulaSet("Optics_نور", ("f", "do", "di", "m", "ho", "hi"), ("1/f=1/do+1/di", "m=-di/do", "m=hi/ho")),
    FormulaSet("Thermodynamics_ترمودینامیک", ("Q", "m", "c", "dT", "P", "V", "n", "R", "T"), ("Q=m*c*dT", "P*V=n*R*T")),
    FormulaSet("Pressure & Density_فشار و چگالی", ("P", "F", "A", "rho", "m", "V"), ("P=F/A", "rho=m/V")),
]

CHEM_FORMULAS = [
    FormulaSet("Molarity_مولاریته", ("M", "n", "V"), ("M=n/V",)),
    FormulaSet("Mole_مول", ("n", "m", "M_molar"), ("n=m/M_molar",)),
    FormulaSet("Dilution_رقیق سازی", ("M1", "V1", "M2", "V2"), ("M1*V1=M2*V2",)),
    FormulaSet("Ideal Gas_گاز ایده‌آل", ("P", "V", "n", "R", "T"), ("P*V=n*R*T",)),
    FormulaSet("pH/pOH_پی اچ", ("pH", "pOH"), ("pH+pOH=14",)),
    FormulaSet("Density_چگالی", ("rho", "m", "V"), ("rho=m/V",)),
    FormulaSet("Mass Percent_درصد جرمی", ("percent", "m_solute", "m_solution"), ("percent=100*m_solute/m_solution",)),
]

# full element symbols
ELEMENTS = [
"H","He","Li","Be","B","C","N","O","F","Ne","Na","Mg","Al","Si","P","S","Cl","Ar","K","Ca","Sc","Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn","Ga","Ge","As","Se","Br","Kr","Rb","Sr","Y","Zr","Nb","Mo","Tc","Ru","Rh","Pd","Ag","Cd","In","Sn","Sb","Te","I","Xe","Cs","Ba","La","Ce","Pr","Nd","Pm","Sm","Eu","Gd","Tb","Dy","Ho","Er","Tm","Yb","Lu","Hf","Ta","W","Re","Os","Ir","Pt","Au","Hg","Tl","Pb","Bi","Po","At","Rn","Fr","Ra","Ac","Th","Pa","U","Np","Pu","Am","Cm","Bk","Cf","Es","Fm","Md","No","Lr","Rf","Db","Sg","Bh","Hs","Mt","Ds","Rg","Cn","Nh","Fl","Mc","Lv","Ts","Og"
]


def periodic_layout() -> list[tuple[int, str, int, int]]:
    # proper groups/periods for shaped table
    row_data = {
        1: [(1,"H"),(18,"He")],
        2: [(1,"Li"),(2,"Be"),(13,"B"),(14,"C"),(15,"N"),(16,"O"),(17,"F"),(18,"Ne")],
        3: [(1,"Na"),(2,"Mg"),(13,"Al"),(14,"Si"),(15,"P"),(16,"S"),(17,"Cl"),(18,"Ar")],
        4: [(1,"K"),(2,"Ca"),(3,"Sc"),(4,"Ti"),(5,"V"),(6,"Cr"),(7,"Mn"),(8,"Fe"),(9,"Co"),(10,"Ni"),(11,"Cu"),(12,"Zn"),(13,"Ga"),(14,"Ge"),(15,"As"),(16,"Se"),(17,"Br"),(18,"Kr")],
        5: [(1,"Rb"),(2,"Sr"),(3,"Y"),(4,"Zr"),(5,"Nb"),(6,"Mo"),(7,"Tc"),(8,"Ru"),(9,"Rh"),(10,"Pd"),(11,"Ag"),(12,"Cd"),(13,"In"),(14,"Sn"),(15,"Sb"),(16,"Te"),(17,"I"),(18,"Xe")],
        6: [(1,"Cs"),(2,"Ba"),(4,"Hf"),(5,"Ta"),(6,"W"),(7,"Re"),(8,"Os"),(9,"Ir"),(10,"Pt"),(11,"Au"),(12,"Hg"),(13,"Tl"),(14,"Pb"),(15,"Bi"),(16,"Po"),(17,"At"),(18,"Rn")],
        7: [(1,"Fr"),(2,"Ra"),(4,"Rf"),(5,"Db"),(6,"Sg"),(7,"Bh"),(8,"Hs"),(9,"Mt"),(10,"Ds"),(11,"Rg"),(12,"Cn"),(13,"Nh"),(14,"Fl"),(15,"Mc"),(16,"Lv"),(17,"Ts"),(18,"Og")],
        8: [(3,"La"),(4,"Ce"),(5,"Pr"),(6,"Nd"),(7,"Pm"),(8,"Sm"),(9,"Eu"),(10,"Gd"),(11,"Tb"),(12,"Dy"),(13,"Ho"),(14,"Er"),(15,"Tm"),(16,"Yb"),(17,"Lu")],
        9: [(3,"Ac"),(4,"Th"),(5,"Pa"),(6,"U"),(7,"Np"),(8,"Pu"),(9,"Am"),(10,"Cm"),(11,"Bk"),(12,"Cf"),(13,"Es"),(14,"Fm"),(15,"Md"),(16,"No"),(17,"Lr")],
    }
    out = []
    for period, cells in row_data.items():
        for group, sym in cells:
            out.append((ELEMENTS.index(sym)+1, sym, period, group))
    return out

PERIODIC_SHAPE = periodic_layout()

ATOMIC_MASS = {
    "H": "1.008", "He": "4.0026", "Li": "6.94", "Be": "9.0122", "B": "10.81", "C": "12.011", "N": "14.007", "O": "15.999", "F": "18.998", "Ne": "20.180",
    "Na": "22.990", "Mg": "24.305", "Al": "26.982", "Si": "28.085", "P": "30.974", "S": "32.06", "Cl": "35.45", "Ar": "39.948", "K": "39.098", "Ca": "40.078",
    "Sc": "44.956", "Ti": "47.867", "V": "50.942", "Cr": "51.996", "Mn": "54.938", "Fe": "55.845", "Co": "58.933", "Ni": "58.693", "Cu": "63.546", "Zn": "65.38",
    "Ga": "69.723", "Ge": "72.630", "As": "74.922", "Se": "78.971", "Br": "79.904", "Kr": "83.798", "Rb": "85.468", "Sr": "87.62", "Y": "88.906", "Zr": "91.224",
    "Nb": "92.906", "Mo": "95.95", "Tc": "[98]", "Ru": "101.07", "Rh": "102.91", "Pd": "106.42", "Ag": "107.87", "Cd": "112.41", "In": "114.82", "Sn": "118.71",
    "Sb": "121.76", "Te": "127.60", "I": "126.90", "Xe": "131.29", "Cs": "132.91", "Ba": "137.33", "La": "138.91", "Ce": "140.12", "Pr": "140.91", "Nd": "144.24",
    "Pm": "[145]", "Sm": "150.36", "Eu": "151.96", "Gd": "157.25", "Tb": "158.93", "Dy": "162.50", "Ho": "164.93", "Er": "167.26", "Tm": "168.93", "Yb": "173.05",
    "Lu": "174.97", "Hf": "178.49", "Ta": "180.95", "W": "183.84", "Re": "186.21", "Os": "190.23", "Ir": "192.22", "Pt": "195.08", "Au": "196.97", "Hg": "200.59",
    "Tl": "204.38", "Pb": "207.2", "Bi": "208.98", "Po": "[209]", "At": "[210]", "Rn": "[222]", "Fr": "[223]", "Ra": "[226]", "Ac": "[227]", "Th": "232.04",
    "Pa": "231.04", "U": "238.03", "Np": "[237]", "Pu": "[244]", "Am": "[243]", "Cm": "[247]", "Bk": "[247]", "Cf": "[251]", "Es": "[252]", "Fm": "[257]",
    "Md": "[258]", "No": "[259]", "Lr": "[266]", "Rf": "[267]", "Db": "[270]", "Sg": "[271]", "Bh": "[270]", "Hs": "[277]", "Mt": "[278]", "Ds": "[281]",
    "Rg": "[282]", "Cn": "[285]", "Nh": "[286]", "Fl": "[289]", "Mc": "[290]", "Lv": "[293]", "Ts": "[294]", "Og": "[294]"
}


def evaluate_expr(expr: str, values: dict[str, float], deg_mode: bool = False) -> float:
    env = {
        "pi": math.pi, "e": math.e, "sqrt": math.sqrt, "log": math.log10, "ln": math.log,
        "abs": abs, "pow": pow,
        "sin": (lambda x: math.sin(math.radians(x))) if deg_mode else math.sin,
        "cos": (lambda x: math.cos(math.radians(x))) if deg_mode else math.cos,
        "tan": (lambda x: math.tan(math.radians(x))) if deg_mode else math.tan,
    }

    def repl(m: re.Match[str]) -> str:
        t = m.group(0)
        return t if t in env else f"({values[t]})" if t in values else t

    return float(eval(TOKEN_RE.sub(repl, expr), {"__builtins__": None}, env))


def equation_vars(eq: str) -> list[str]:
    bad = {"pi", "e", "sin", "cos", "tan", "sqrt", "log", "ln", "abs", "pow"}
    return [t for t in TOKEN_RE.findall(eq) if t not in bad]


def solve_single_unknown(eq: str, values: dict[str, float]) -> tuple[str, float] | None:
    left, right = [p.strip() for p in eq.split("=", 1)]
    unknowns = [v for v in sorted(set(equation_vars(eq))) if v not in values]
    if len(unknowns) != 1:
        return None
    unk = unknowns[0]

    def f(x: float) -> float:
        t = dict(values); t[unk] = x
        return evaluate_expr(left, t) - evaluate_expr(right, t)

    x = 1.0
    for _ in range(80):
        y = f(x)
        if abs(y) < 1e-10:
            return unk, x
        d = 1e-6
        slope = (f(x + d) - y) / d
        if abs(slope) < 1e-12:
            break
        x = x - y / slope
    return None


def solve_formula_set(formula: FormulaSet, known: dict[str, float]) -> dict[str, float]:
    values = {k: float(v) for k, v in known.items()}
    for _ in range(25):
        changed = False
        for eq in formula.equations:
            ans = solve_single_unknown(eq, values)
            if ans and ans[0] not in values:
                values[ans[0]] = ans[1]
                changed = True
        if not changed:
            break
    return values


def parse_compound(formula: str) -> dict[str, int]:
    tokens = re.findall(r"[A-Z][a-z]?|\(|\)|\d+", formula)
    stack = [dict()]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "(":
            stack.append({})
        elif tok == ")":
            mult = 1
            if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                mult = int(tokens[i + 1]); i += 1
            grp = stack.pop()
            for e, c in grp.items():
                stack[-1][e] = stack[-1].get(e, 0) + c * mult
        elif tok.isdigit():
            pass
        else:
            mult = 1
            if i + 1 < len(tokens) and tokens[i + 1].isdigit():
                mult = int(tokens[i + 1]); i += 1
            stack[-1][tok] = stack[-1].get(tok, 0) + mult
        i += 1
    return stack[0]


def balance_equation(eq: str) -> str:
    eq = eq.replace("→", "=").replace("->", "=")
    left_s, right_s = [p.strip() for p in eq.split("=")]
    left = [x.strip() for x in left_s.split("+")]
    right = [x.strip() for x in right_s.split("+")]
    compounds = left + right
    elems = sorted({e for c in compounds for e in parse_compound(c)})
    mat = []
    for e in elems:
        mat.append([Fraction(parse_compound(c).get(e, 0)) for c in left] + [Fraction(-parse_compound(c).get(e, 0)) for c in right])
    A = [r[:-1] for r in mat]; b = [-r[-1] for r in mat]
    rows, cols = len(A), len(A[0])
    aug = [A[i] + [b[i]] for i in range(rows)]
    rr = 0
    for c in range(cols):
        piv = next((i for i in range(rr, rows) if aug[i][c] != 0), None)
        if piv is None:
            continue
        aug[rr], aug[piv] = aug[piv], aug[rr]
        div = aug[rr][c]
        aug[rr] = [x / div for x in aug[rr]]
        for i in range(rows):
            if i != rr and aug[i][c] != 0:
                fac = aug[i][c]
                aug[i] = [aug[i][j] - fac * aug[rr][j] for j in range(cols + 1)]
        rr += 1
        if rr == rows:
            break
    x = [Fraction(0) for _ in range(cols)]
    for i in range(rows):
        lead = next((j for j in range(cols) if aug[i][j] != 0), None)
        if lead is not None:
            x[lead] = aug[i][-1]
    x.append(Fraction(1))
    lcm = 1
    for v in x:
        lcm = lcm * v.denominator // math.gcd(lcm, v.denominator)
    coeffs = [abs(int(v*lcm)) for v in x]
    g = coeffs[0]
    for c in coeffs[1:]: g = math.gcd(g, c)
    coeffs = [c // g for c in coeffs]
    ltxt = " + ".join([f"{coeffs[i]}{left[i]}" if coeffs[i] != 1 else left[i] for i in range(len(left))])
    rtxt = " + ".join([f"{coeffs[i+len(left)]}{right[i]}" if coeffs[i+len(left)] != 1 else right[i] for i in range(len(right))])
    return f"{ltxt} = {rtxt}"


class LoginWindow(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Multitool Login / ورود مولتی‌تول")
        self.geometry("380x260")
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Username / نام کاربری").grid(row=0, column=0, sticky="w")
        self.user_entry = ttk.Entry(frm); self.user_entry.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(frm, text="Password / رمز عبور").grid(row=2, column=0, sticky="w")
        self.pass_entry = ttk.Entry(frm, show="*"); self.pass_entry.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        actions = ttk.Frame(frm); actions.grid(row=4, column=0, sticky="ew")
        ttk.Button(actions, text="Login / ورود", command=self.do_login).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(actions, text="Register / ثبت نام", command=self.do_register).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(actions, text="Guest Mode / مهمان", command=self.do_guest).pack(side="left", expand=True, fill="x", padx=2)
        frm.columnconfigure(0, weight=1)

    def do_register(self) -> None:
        u, p = self.user_entry.get().strip(), self.pass_entry.get().strip()
        if len(u) < 3 or len(p) < 4:
            return messagebox.showwarning("Invalid / نامعتبر", "Username >=3 chars and password >=4 chars. / نام کاربری حداقل ۳ و رمز حداقل ۴ کاراکتر باشد.")
        messagebox.showinfo("Done / انجام شد", "Registered successfully. / ثبت‌نام با موفقیت انجام شد.") if create_user(u, p) else messagebox.showerror("Exists / موجود است", "Username already exists. / نام کاربری از قبل وجود دارد.")

    def do_login(self) -> None:
        u, p = self.user_entry.get().strip(), self.pass_entry.get().strip()
        if verify_user(u, p):
            self.destroy(); MultiToolApp(u, is_guest=False).mainloop()
        else:
            messagebox.showerror("Failed / ناموفق", "Wrong username or password. / نام کاربری یا رمز عبور اشتباه است.")

    def do_guest(self) -> None:
        self.destroy(); MultiToolApp("guest", is_guest=True).mainloop()


class MultiToolApp(tk.Tk):
    def __init__(self, username: str, is_guest: bool = False):
        super().__init__()
        self.username = username; self.is_guest = is_guest
        self.lang_var = tk.StringVar(value=get_lang())
        self.dark_mode = get_setting("theme", "dark") == "dark"
        self.plot_window = None
        self.plot_ax = None
        self.plot_widget = None

        self.title(f"✨ Kharazmi Multitool / مولتی‌تول خوارزمی — {username}{' (Guest / مهمان)' if is_guest else ''}")
        self.geometry("1420x900")
        try: self.state("zoomed")
        except Exception: pass
        self.resizable(True, True)

        self._apply_theme(); self._build_menu(); self._build_topbar()
        self.nb = ttk.Notebook(self); self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        self.converter_tab = ttk.Frame(self.nb); self.calc_tab = ttk.Frame(self.nb); self.clock_tab = ttk.Frame(self.nb)
        self.color_tab = ttk.Frame(self.nb); self.colors_gallery_tab = ttk.Frame(self.nb); self.physics_tab = ttk.Frame(self.nb); self.chem_tab = ttk.Frame(self.nb)
        self.periodic_tab = ttk.Frame(self.nb); self.math_tab = ttk.Frame(self.nb); self.balance_tab = ttk.Frame(self.nb); self.tools_tab = ttk.Frame(self.nb); self.geometry_tab = ttk.Frame(self.nb); self.bank_tab = ttk.Frame(self.nb); self.notes_tab = ttk.Frame(self.nb); self.random_tab = ttk.Frame(self.nb)

        self.nb.add(self.converter_tab, text="Converter / تبدیل")
        self.nb.add(self.calc_tab, text="Calculator / ماشین‌حساب")
        self.nb.add(self.clock_tab, text="Clock / ساعت")
        self.nb.add(self.color_tab, text="Color Picker")
        self.nb.add(self.colors_gallery_tab, text="Colors")
        self.nb.add(self.physics_tab, text="Physics")
        self.nb.add(self.chem_tab, text="Chemistry")
        self.nb.add(self.periodic_tab, text="Periodic")
        self.nb.add(self.math_tab, text="Math")
        self.nb.add(self.balance_tab, text="Balancer")
        self.nb.add(self.tools_tab, text="Tools")
        self.nb.add(self.geometry_tab, text="Geometry")
        self.nb.add(self.bank_tab, text="Bank")
        self.nb.add(self.notes_tab, text="Notes")
        self.nb.add(self.random_tab, text="Random")

        self.build_converter_tab(); self.build_calculator_tab(); self.build_clock_tab(); self.build_color_tab(); self.build_colors_gallery_tab()
        self.build_physics_tab(); self.build_chemistry_tab(); self.build_periodic_shape_tab(); self.build_math_tab(); self.build_balancer_tab(); self.build_tools_tab(); self.build_geometry_tab(); self.build_bank_tab(); self.build_notes_tab(); self.build_random_tab()
        self.toggle_language()

    def _build_topbar(self) -> None:
        pass

    def _build_menu(self) -> None:
        m = tk.Menu(self)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="About" if self.lang_var.get()=="en" else "درباره", command=self.open_about_window)
        m.add_cascade(label="Help" if self.lang_var.get()=="en" else "راهنما", menu=h)

        st = tk.Menu(m, tearoff=0)
        st.add_command(label="Toggle Theme" if self.lang_var.get()=="en" else "تغییر تم", command=self.toggle_theme)
        current_lang = self.lang_var.get()
        target_lang = "fa" if current_lang == "en" else "en"
        switch_text = "Switch to فارسی" if current_lang == "en" else "تغییر به English"
        st.add_command(label=switch_text, command=lambda: self.set_language(target_lang))
        m.add_cascade(label="Settings" if self.lang_var.get()=="en" else "تنظیمات", menu=st)
        self.config(menu=m)

    def open_about_window(self) -> None:
        w = tk.Toplevel(self); w.title("About Kharazmi / درباره خوارزمی"); w.geometry("540x260")
        ttk.Label(w, text="About / درباره", font=("Segoe UI", 16, "bold")).pack(pady=8)
        text = "Kharazmi Multitool includes converter, calculator, clock, color tools, physics/chemistry solvers, periodic table, math solver, and equation balancer."
        if self.lang_var.get() == "fa":
            text = "خوارزمی مولتی‌تول شامل مبدل، ماشین‌حساب، ساعت، ابزار رنگ، حل‌گر فیزیک و شیمی، جدول تناوبی، حل‌گر ریاضی و بالانس معادلات است."
        ttk.Label(w, text=text, wraplength=500, justify="left").pack(fill="x", padx=10, pady=8)
        ttk.Button(w, text="Open README / باز کردن README", command=lambda: webbrowser.open(f"file://{os.path.abspath('README.md')}")) .pack(pady=8)

    def _apply_theme(self) -> None:
        bg = "#0f1722" if self.dark_mode else "#f4f7fb"
        fg = "#e6efff" if self.dark_mode else "#0f1722"
        self.configure(bg=bg)
        st = ttk.Style(self); st.theme_use("clam")
        for style_name in ["TFrame", "TLabel", "TLabelframe", "TLabelframe.Label", "TNotebook"]:
            st.configure(style_name, background=bg, foreground=fg)

    def toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode; set_setting("theme", "dark" if self.dark_mode else "light"); self._apply_theme()

    def set_language(self, code: str) -> None:
        self.lang_var.set(code)
        self.toggle_language()

    def toggle_language(self) -> None:
        set_setting("lang", self.lang_var.get())
        set_lang(self.lang_var.get())
        labels_en = ["Converter", "Calculator", "Clock", "Color Picker", "Colors", "Physics", "Chemistry", "Periodic", "Math", "Balancer", "Tools", "Geometry", "Bank", "Notes", "Random"]
        labels_fa = ["تبدیل", "ماشین‌حساب", "ساعت", "انتخاب رنگ", "رنگ‌ها", "فیزیک", "شیمی", "تناوبی", "ریاضی", "بالانس", "ابزار", "هندسه", "بانک", "یادداشت", "تصادفی"]
        labels = labels_fa if self.lang_var.get() == "fa" else labels_en
        for i, text in enumerate(labels):
            self.nb.tab(i, text=text)
        if hasattr(self, "conv_category"):
            current_cat = self._cat_key(self.conv_category.get())
            self.conv_category.set(self._cat_display(current_cat))
            self.refresh_units()
        for child in self.colors_gallery_tab.winfo_children():
            child.destroy()
        self.build_colors_gallery_tab()
        self._build_menu()
        self._apply_single_language_to_widget(self)

    def tr(self, en: str, fa: str) -> str:
        return fa if self.lang_var.get() == "fa" else en

    def _lang_pick(self, text: str) -> str:
        if " / " not in text:
            return text
        en, fa = text.split(" / ", 1)
        return fa.strip() if self.lang_var.get() == "fa" else en.strip()

    def _apply_single_language_to_widget(self, w) -> None:
        try:
            txt = w.cget("text")
            if isinstance(txt, str) and " / " in txt:
                w.configure(text=self._lang_pick(txt))
        except Exception:
            pass
        if isinstance(w, ttk.Combobox):
            try:
                vals = list(w.cget("values"))
                if vals:
                    w.configure(values=[self._lang_pick(v) if isinstance(v, str) else v for v in vals])
            except Exception:
                pass
        for ch in w.winfo_children():
            self._apply_single_language_to_widget(ch)

    def _cat_display(self, key: str) -> str:
        return CATEGORY_FA.get(key, key) if self.lang_var.get() == "fa" else key

    def _cat_key(self, display: str) -> str:
        if self.lang_var.get() == "fa":
            for en, fa in CATEGORY_FA.items():
                if display == fa:
                    return en
        return display.split(" / ", 1)[0] if " / " in display else display

    def _unit_display(self, key: str) -> str:
        return UNIT_FA.get(key, key) if self.lang_var.get() == "fa" else key

    def _unit_key(self, display: str) -> str:
        if self.lang_var.get() == "fa":
            for en, fa in UNIT_FA.items():
                if display == fa:
                    return en
        return display.split(" / ", 1)[0] if " / " in display else display

    # converter
    def build_converter_tab(self) -> None:
        f = ttk.Frame(self.converter_tab, padding=16); f.pack(fill="both", expand=True)
        self.conv_category = tk.StringVar(value=self._cat_display(sorted(UNIT_CATEGORIES.keys())[0])); self.conv_from = tk.StringVar(); self.conv_to = tk.StringVar(); self.conv_input = tk.StringVar(value="1"); self.conv_result = tk.StringVar(); self.conv_precision = tk.IntVar(value=10)
        card = ttk.LabelFrame(f, text="Converter / تبدیل", padding=12); card.pack(fill="x", pady=8)
        ttk.Label(card, text="Category / دسته").grid(row=0, column=0, sticky="w")
        cb = ttk.Combobox(card, textvariable=self.conv_category, values=[self._cat_display(c) for c in sorted(UNIT_CATEGORIES)], state="readonly")
        cb.grid(row=1, column=0, sticky="ew", padx=6, pady=6); cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_units())
        ttk.Label(card, text="From / از").grid(row=0, column=1, sticky="w"); self.from_box = ttk.Combobox(card, textvariable=self.conv_from, state="readonly"); self.from_box.grid(row=1, column=1, sticky="ew", padx=6, pady=6)
        ttk.Label(card, text="To / به").grid(row=0, column=2, sticky="w"); self.to_box = ttk.Combobox(card, textvariable=self.conv_to, state="readonly"); self.to_box.grid(row=1, column=2, sticky="ew", padx=6, pady=6)
        ttk.Entry(card, textvariable=self.conv_input).grid(row=2, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(card, text="Convert / تبدیل", command=self.do_convert).grid(row=2, column=1, sticky="ew", padx=6, pady=6)
        ttk.Button(card, text="Swap Units ⇄ / جابجایی واحدها", command=self.swap_units).grid(row=2, column=2, sticky="ew", padx=6, pady=6)
        ttk.Entry(card, textvariable=self.conv_result, state="readonly").grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=6)
        ttk.Label(card, text="Precision / دقت").grid(row=4, column=0, sticky="w", padx=6)
        ttk.Spinbox(card, from_=2, to=16, textvariable=self.conv_precision, width=8).grid(row=4, column=1, sticky="w", padx=6)
        ttk.Button(card, text="Copy Result / کپی نتیجه", command=lambda: self.clipboard_clear() or self.clipboard_append(self.conv_result.get())).grid(row=4, column=2, sticky="ew", padx=6, pady=4)
        ttk.Button(card, text="Open Converter Settings / تنظیمات تبدیل", command=self.open_converter_settings_window).grid(row=5, column=0, columnspan=3, sticky="ew", padx=6, pady=8)
        for i in range(3): card.columnconfigure(i, weight=1)
        self.refresh_units()

    def open_converter_settings_window(self) -> None:
        w = tk.Toplevel(self); w.title("Converter Settings / تنظیمات مبدل"); w.geometry("920x360")
        cat_var = tk.StringVar(value=self._cat_display(sorted(UNIT_CATEGORIES.keys())[0])); unit_var = tk.StringVar()
        name_var = tk.StringVar(); factor_var = tk.StringVar(value="1"); offset_var = tk.StringVar(value="0"); rename_var = tk.StringVar(); new_cat_var = tk.StringVar()
        frm = ttk.Frame(w, padding=12); frm.pack(fill="both", expand=True)

        ttk.Label(frm, text="Category / دسته").grid(row=0, column=0, sticky="w")
        cat_box = ttk.Combobox(frm, textvariable=cat_var, values=[self._cat_display(c) for c in sorted(UNIT_CATEGORIES)], state="readonly")
        cat_box.grid(row=1, column=0, sticky="ew", padx=4)
        ttk.Label(frm, text="Unit / واحد").grid(row=0, column=1, sticky="w")
        unit_box = ttk.Combobox(frm, textvariable=unit_var, state="readonly")
        unit_box.grid(row=1, column=1, sticky="ew", padx=4)

        def refresh_unit_box():
            cat_key = self._cat_key(cat_var.get()); vals = sorted(UNIT_CATEGORIES.get(cat_key, {}).keys())
            unit_box["values"] = [self._unit_display(v) for v in vals]
            if vals:
                unit_var.set(self._unit_display(vals[0])); name_var.set(vals[0]); factor_var.set(str(UNIT_CATEGORIES[cat_key][vals[0]][0])); offset_var.set(str(UNIT_CATEGORIES[cat_key][vals[0]][1]))

        def load_selected(_e=None):
            c, u = self._cat_key(cat_var.get()), self._unit_key(unit_var.get())
            if u in UNIT_CATEGORIES.get(c, {}):
                name_var.set(u); factor_var.set(str(UNIT_CATEGORIES[c][u][0])); offset_var.set(str(UNIT_CATEGORIES[c][u][1]))

        cat_box.bind("<<ComboboxSelected>>", lambda _e: refresh_unit_box())
        unit_box.bind("<<ComboboxSelected>>", load_selected)

        for i, title in enumerate(["Name / نام", "Factor / ضریب", "Offset / آفست", "Rename To / تغییر نام به"]):
            ttk.Label(frm, text=title).grid(row=2, column=i, sticky="w", pady=(10, 0))
        ttk.Entry(frm, textvariable=name_var).grid(row=3, column=0, sticky="ew", padx=4)
        ttk.Entry(frm, textvariable=factor_var).grid(row=3, column=1, sticky="ew", padx=4)
        ttk.Entry(frm, textvariable=offset_var).grid(row=3, column=2, sticky="ew", padx=4)
        ttk.Entry(frm, textvariable=rename_var).grid(row=3, column=3, sticky="ew", padx=4)

        ttk.Button(frm, text="Add Unit / افزودن واحد", command=lambda: (UNIT_CATEGORIES.setdefault(self._cat_key(cat_var.get()), {}).update({name_var.get().strip(): (float(factor_var.get()), float(offset_var.get()))}), refresh_unit_box(), self.refresh_units())).grid(row=4, column=0, sticky="ew", pady=10)
        ttk.Button(frm, text="Change Unit / تغییر واحد", command=lambda: (UNIT_CATEGORIES[self._cat_key(cat_var.get())].update({self._unit_key(unit_var.get()): (float(factor_var.get()), float(offset_var.get()))}), refresh_unit_box(), self.refresh_units())).grid(row=4, column=1, sticky="ew", pady=10)
        ttk.Button(frm, text="Remove Unit / حذف واحد", command=lambda: (UNIT_CATEGORIES[self._cat_key(cat_var.get())].pop(self._unit_key(unit_var.get()), None), refresh_unit_box(), self.refresh_units())).grid(row=4, column=2, sticky="ew", pady=10)
        ttk.Button(frm, text="Rename Unit / تغییر نام واحد", command=lambda: (UNIT_CATEGORIES[self._cat_key(cat_var.get())].update({rename_var.get().strip(): UNIT_CATEGORIES[self._cat_key(cat_var.get())].pop(self._unit_key(unit_var.get()))}) if rename_var.get().strip() and self._unit_key(unit_var.get()) in UNIT_CATEGORIES[self._cat_key(cat_var.get())] else None, refresh_unit_box(), self.refresh_units())).grid(row=4, column=3, sticky="ew", pady=10)

        ttk.Label(frm, text="New Category / دسته جدید").grid(row=5, column=0, sticky="w")
        ttk.Entry(frm, textvariable=new_cat_var).grid(row=6, column=0, sticky="ew", padx=4)
        ttk.Button(frm, text="Add Category / افزودن دسته", command=lambda: (UNIT_CATEGORIES.setdefault(new_cat_var.get().strip(), {}), cat_box.configure(values=[self._cat_display(c) for c in sorted(UNIT_CATEGORIES)]), self.refresh_units())).grid(row=6, column=1, sticky="ew", padx=4)
        ttk.Button(frm, text="Remove Category / حذف دسته", command=lambda: (UNIT_CATEGORIES.pop(self._cat_key(cat_var.get()), None), cat_box.configure(values=[self._cat_display(c) for c in sorted(UNIT_CATEGORIES)]), self.refresh_units())).grid(row=6, column=2, sticky="ew", padx=4)

        for i in range(4): frm.columnconfigure(i, weight=1)
        refresh_unit_box()

    def refresh_units(self) -> None:
        vals = sorted(UNIT_CATEGORIES[self._cat_key(self.conv_category.get())].keys())
        self.from_box["values"] = [self._unit_display(v) for v in vals]; self.to_box["values"] = [self._unit_display(v) for v in vals]
        if vals:
            self.conv_from.set(self._unit_display(vals[0])); self.conv_to.set(self._unit_display(vals[1] if len(vals) > 1 else vals[0]))

    def swap_units(self) -> None:
        a, b = self.conv_from.get(), self.conv_to.get(); self.conv_from.set(b); self.conv_to.set(a)

    def do_convert(self) -> None:
        cat = self._cat_key(self.conv_category.get()); uf, ut = self._unit_key(self.conv_from.get()), self._unit_key(self.conv_to.get()); t = UNIT_CATEGORIES[cat]; v = float(self.conv_input.get())
        if cat == "Fuel Economy":
            base = 100.0 / v if uf == "liter_per_100km" else v * t[uf][0]
            out = 100.0 / base if ut == "liter_per_100km" else base / t[ut][0]
        elif cat == "Temperature":
            fm, fo = t[uf]; tm, to = t[ut]
            out = ((v*fm + fo) - to) / tm
        else:
            out = (v * t[uf][0]) / t[ut][0]
        prec = max(2, min(16, int(self.conv_precision.get() or 10)))
        self.conv_result.set(f"{out:.{prec}g}")

    # calculator and rest copied from prior but concise
    def build_calculator_tab(self) -> None:
        f = ttk.Frame(self.calc_tab, padding=12); f.pack(fill="both", expand=True)
        self.deg_mode = tk.BooleanVar(value=True); self.calc_expr = tk.StringVar(); self.calc_out = tk.StringVar(); self.plot_expr = tk.StringVar(value="sin(x)"); self.calc_memory = 0.0; self.mem_var = tk.StringVar(value="M=0")
        left = ttk.LabelFrame(f, text="Calculator / ماشین‌حساب", padding=8); left.grid(row=0, column=0, sticky="nsew")
        right = ttk.LabelFrame(f, text="History / تاریخچه", padding=8); right.grid(row=0, column=1, sticky="nsew", padx=8)
        ttk.Entry(left, textvariable=self.calc_expr).grid(row=0, column=0, columnspan=5, sticky="ew", pady=3)
        ttk.Entry(left, textvariable=self.calc_out, state="readonly").grid(row=1, column=0, columnspan=5, sticky="ew", pady=3)
        ttk.Checkbutton(left, text="Degree / درجه", variable=self.deg_mode).grid(row=2, column=0, sticky="w")
        keys = [["7", "8", "9", "/", "sin("], ["4", "5", "6", "*", "cos("], ["1", "2", "3", "-", "tan("], ["0", ".", "(", ")", "+"], ["pi", "e", "sqrt(", "^", "ANS"], ["C/پاک", "DEL/حذف", "log(", "ln(", "Plot/نمودار"]]
        r0 = 3
        for r, row in enumerate(keys):
            for c, t in enumerate(row):
                ttk.Button(left, text=t, command=lambda x=t: self.calc_button(x)).grid(row=r0+r, column=c, sticky="nsew", padx=2, pady=2)
        tk.Button(left, text="=", font=("Segoe UI", 16, "bold"), height=2, command=lambda: self.calc_button("=")).grid(row=r0+len(keys), column=0, columnspan=5, sticky="nsew", padx=2, pady=4)
        ttk.Button(left, text="MC", command=lambda: self.calc_memory_action("MC")).grid(row=r0+len(keys)+1, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(left, text="MR", command=lambda: self.calc_memory_action("MR")).grid(row=r0+len(keys)+1, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(left, text="M+", command=lambda: self.calc_memory_action("M+")).grid(row=r0+len(keys)+1, column=2, sticky="ew", padx=2, pady=2)
        ttk.Button(left, text="M-", command=lambda: self.calc_memory_action("M-")).grid(row=r0+len(keys)+1, column=3, sticky="ew", padx=2, pady=2)
        ttk.Label(left, textvariable=self.mem_var).grid(row=r0+len(keys)+1, column=4, sticky="e")
        ttk.Label(left, text="Plot y= / رسم y=").grid(row=r0+len(keys)+2, column=0, sticky="e")
        ttk.Entry(left, textvariable=self.plot_expr).grid(row=r0+len(keys)+2, column=1, columnspan=4, sticky="ew")
        ttk.Button(left, text="Open Plot Window / پنجره نمودار", command=self.open_plot_window).grid(row=r0+len(keys)+3, column=0, columnspan=5, sticky="ew", pady=8)
        self.calc_history_list = tk.Listbox(right); self.calc_history_list.pack(fill="both", expand=True)
        for i in range(5): left.columnconfigure(i, weight=1)
        f.columnconfigure(0, weight=3); f.columnconfigure(1, weight=1); f.rowconfigure(0, weight=1)
        self.refresh_calc_history()

    def calc_button(self, token: str) -> None:
        if token == "=": self.eval_calc()
        elif token == "C/پاک": self.calc_expr.set(""); self.calc_out.set("")
        elif token == "DEL/حذف": self.calc_expr.set(self.calc_expr.get()[:-1])
        elif token == "Plot/نمودار": self.open_plot_window()
        elif token == "ANS": self.calc_expr.set(self.calc_expr.get() + self.calc_out.get())
        elif token == "^": self.calc_expr.set(self.calc_expr.get() + "**")
        else: self.calc_expr.set(self.calc_expr.get() + token)

    def calc_memory_action(self, action: str) -> None:
        try:
            val = float(self.calc_out.get()) if self.calc_out.get().strip() else 0.0
        except Exception:
            val = 0.0
        if action == "MC":
            self.calc_memory = 0.0
        elif action == "MR":
            self.calc_expr.set(self.calc_expr.get() + f"{self.calc_memory:.12g}")
        elif action == "M+":
            self.calc_memory += val
        elif action == "M-":
            self.calc_memory -= val
        self.mem_var.set(f"M={self.calc_memory:.6g}")

    def open_plot_window(self) -> None:
        if self.plot_window and self.plot_window.winfo_exists(): self.draw_plot(); self.plot_window.lift(); return
        self.plot_window = tk.Toplevel(self); self.plot_window.title("Plot / نمودار"); self.plot_window.geometry("800x500")
        fig, self.plot_ax = plt.subplots(figsize=(7, 4), dpi=100)
        self.plot_widget = FigureCanvasTkAgg(fig, master=self.plot_window)
        self.plot_widget.get_tk_widget().pack(fill="both", expand=True)
        controls = ttk.Frame(self.plot_window); controls.pack(fill="x", pady=4)
        self.xmin_var = tk.StringVar(value="")
        self.xmax_var = tk.StringVar(value="")
        self.ymin_var = tk.StringVar(value="")
        self.ymax_var = tk.StringVar(value="")
        for lbl, var in [("xmin", self.xmin_var), ("xmax", self.xmax_var), ("ymin", self.ymin_var), ("ymax", self.ymax_var)]:
            ttk.Label(controls, text=lbl).pack(side="left")
            ttk.Entry(controls, textvariable=var, width=8).pack(side="left", padx=2)
        ttk.Button(controls, text="Apply", command=self.draw_plot).pack(side="left", padx=4)
        ttk.Button(controls, text="Zoom Out x2", command=self.zoom_out_plot).pack(side="left", padx=4)
        toolbar = NavigationToolbar2Tk(self.plot_widget, self.plot_window)
        toolbar.update()
        self.draw_plot()

    def refresh_calc_history(self) -> None:
        self.calc_history_list.delete(0, "end")
        for t, e, r in get_calc_history(self.username): self.calc_history_list.insert("end", f"{t} | {e} = {r}")

    def eval_calc(self) -> None:
        try:
            result = f"{evaluate_expr(self.calc_expr.get(), {}, self.deg_mode.get()):.12g}"
            self.calc_out.set(result)
            if not self.is_guest: add_calc_history(self.username, self.calc_expr.get(), result)
            self.refresh_calc_history()
        except Exception as exc:
            self.calc_out.set(f"Error / خطا: {exc}")

    def zoom_out_plot(self) -> None:
        if self.plot_ax is None:
            return
        xmin, xmax = self.plot_ax.get_xlim(); ymin, ymax = self.plot_ax.get_ylim()
        cx, cy = (xmin+xmax)/2, (ymin+ymax)/2
        rx, ry = (xmax-xmin), (ymax-ymin)
        self.plot_ax.set_xlim(cx-rx, cx+rx)
        self.plot_ax.set_ylim(cy-ry, cy+ry)
        self.plot_widget.draw_idle()

    def draw_plot(self) -> None:
        if self.plot_ax is None:
            return
        self.plot_ax.clear()
        expr = self.plot_expr.get().strip()
        try:
            xmin = float(self.xmin_var.get().strip()) if self.xmin_var.get().strip() else -100.0
            xmax = float(self.xmax_var.get().strip()) if self.xmax_var.get().strip() else 100.0
        except Exception:
            xmin, xmax = -100.0, 100.0
        if xmin == xmax:
            xmax = xmin + 1.0
        if xmin > xmax:
            xmin, xmax = xmax, xmin

        points = 2000
        step = (xmax - xmin) / (points - 1)
        segment_x, segment_y = [], []
        prev_y = None
        for i in range(points):
            x = xmin + i * step
            try:
                y = evaluate_expr(expr, {"x": x}, self.deg_mode.get())
            except Exception:
                y = float("nan")
            if not isinstance(y, (int, float)) or not math.isfinite(y):
                if len(segment_x) > 1:
                    self.plot_ax.plot(segment_x, segment_y, color="#2f80ed")
                segment_x, segment_y, prev_y = [], [], None
                continue
            if prev_y is not None and abs(y - prev_y) > max(1e6, abs(prev_y) * 25):
                if len(segment_x) > 1:
                    self.plot_ax.plot(segment_x, segment_y, color="#2f80ed")
                segment_x, segment_y = [], []
            segment_x.append(x)
            segment_y.append(y)
            prev_y = y
        if len(segment_x) > 1:
            self.plot_ax.plot(segment_x, segment_y, color="#2f80ed")

        self.plot_ax.grid(True, alpha=0.3)
        self.plot_ax.axhline(0, color="gray", linewidth=0.8)
        self.plot_ax.axvline(0, color="gray", linewidth=0.8)
        self.plot_ax.set_xlim(xmin, xmax)
        try:
            if self.ymin_var.get().strip() and self.ymax_var.get().strip():
                ymin, ymax = float(self.ymin_var.get()), float(self.ymax_var.get())
                if ymin != ymax:
                    self.plot_ax.set_ylim(min(ymin, ymax), max(ymin, ymax))
        except Exception:
            pass
        formatter = ScalarFormatter(useMathText=True)
        formatter.set_powerlimits((-3, 4))
        self.plot_ax.xaxis.set_major_formatter(formatter)
        self.plot_ax.yaxis.set_major_formatter(formatter)
        self.plot_ax.ticklabel_format(style='sci', axis='both', scilimits=(-3, 4))
        self.plot_widget.draw_idle()

    def build_clock_tab(self) -> None:
        f = ttk.Frame(self.clock_tab, padding=12); f.pack(fill="both", expand=True)
        self.clock_var = tk.StringVar(); self.alarm_var = tk.StringVar(value="07:00"); self.alarm_state = tk.BooleanVar(value=False)
        ttk.Label(f, textvariable=self.clock_var, font=("Segoe UI", 16, "bold")).pack(); row = ttk.Frame(f); row.pack()
        ttk.Label(row, text=self.tr("Alarm HH:MM", "آلارم HH:MM")).pack(side="left"); ttk.Entry(row, textvariable=self.alarm_var, width=10).pack(side="left"); ttk.Checkbutton(row, text=self.tr("Enable", "فعال"), variable=self.alarm_state).pack(side="left")
        sw = ttk.Frame(f); sw.pack(pady=4)
        self.stopwatch_var = tk.StringVar(value="00:00:00.0")
        self.stopwatch_running = False
        self.stopwatch_elapsed = 0.0
        self.stopwatch_start = 0.0
        ttk.Label(sw, text=self.tr("Stopwatch", "کرنومتر")).pack(side="left", padx=4)
        ttk.Label(sw, textvariable=self.stopwatch_var, font=("Segoe UI", 11, "bold")).pack(side="left", padx=4)
        ttk.Button(sw, text=self.tr("Start", "شروع"), command=self.start_stopwatch).pack(side="left", padx=2)
        ttk.Button(sw, text=self.tr("Stop", "توقف"), command=self.stop_stopwatch).pack(side="left", padx=2)
        ttk.Button(sw, text=self.tr("Reset", "ریست"), command=self.reset_stopwatch).pack(side="left", padx=2)

        cd = ttk.Frame(f); cd.pack(pady=4)
        self.countdown_var = tk.StringVar(value="00:05:00")
        self.countdown_left = 0.0
        self.countdown_running = False
        self.countdown_start = 0.0
        ttk.Label(cd, text=self.tr("Countdown HH:MM:SS", "شمارش معکوس HH:MM:SS")).pack(side="left", padx=4)
        ttk.Entry(cd, textvariable=self.countdown_var, width=12).pack(side="left", padx=2)
        ttk.Button(cd, text="Start", command=self.start_countdown).pack(side="left", padx=2)
        ttk.Button(cd, text="Stop", command=self.stop_countdown).pack(side="left", padx=2)
        ttk.Button(cd, text="Reset", command=self.reset_countdown).pack(side="left", padx=2)

        self.clock_canvas = tk.Canvas(f, width=430, height=430); self.clock_canvas.pack(pady=6)
        self.tick_clock()

    def draw_analog_clock(self, now: datetime) -> None:
        c = self.clock_canvas; c.delete("all"); cx, cy, r = 215, 215, 180
        c.create_oval(cx-r, cy-r, cx+r, cy+r, width=3)
        for i in range(60):
            a = math.radians(i*6-90); inner = r-(20 if i%5==0 else 10)
            c.create_line(cx+math.cos(a)*inner, cy+math.sin(a)*inner, cx+math.cos(a)*r, cy+math.sin(a)*r)
        sec = now.second; minute = now.minute + sec/60; hour = (now.hour % 12) + minute/60
        for v, vmax, ln, w, col in [(hour, 12, r*0.55, 5, "black"), (minute, 60, r*0.75, 3, "blue"), (sec, 60, r*0.9, 2, "red")]:
            a = math.radians(v / vmax * 360 - 90); c.create_line(cx, cy, cx + math.cos(a)*ln, cy + math.sin(a)*ln, width=w, fill=col)

    def tick_clock(self) -> None:
        now = datetime.now(); self.clock_var.set(now.strftime("%A, %Y-%m-%d  %H:%M:%S")); self.draw_analog_clock(now)
        if self.alarm_state.get() and now.strftime("%H:%M") == self.alarm_var.get().strip(): self.alarm_state.set(False); messagebox.showinfo("Alarm / آلارم", "Alarm time reached! / زمان آلارم رسید!")
        self._update_countdown_label()
        self.after(200, self.tick_clock)


    @staticmethod
    def _parse_hms(value: str) -> float:
        parts = value.strip().split(":")
        if len(parts) != 3:
            raise ValueError("HH:MM:SS")
        h, m, s = (int(x) for x in parts)
        if h < 0 or m < 0 or s < 0 or m > 59 or s > 59:
            raise ValueError("HH:MM:SS")
        return float(h * 3600 + m * 60 + s)

    @staticmethod
    def _format_hms(seconds: float) -> str:
        total = max(0, int(round(seconds)))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def start_countdown(self) -> None:
        try:
            if not self.countdown_running:
                if self.countdown_left <= 0:
                    self.countdown_left = self._parse_hms(self.countdown_var.get())
                self.countdown_start = time.time()
                self.countdown_running = True
        except Exception:
            messagebox.showerror("Invalid", "Use HH:MM:SS")

    def stop_countdown(self) -> None:
        if self.countdown_running:
            self.countdown_left = max(0.0, self.countdown_left - (time.time() - self.countdown_start))
            self.countdown_running = False
            self.countdown_var.set(self._format_hms(self.countdown_left))

    def reset_countdown(self) -> None:
        self.countdown_running = False
        try:
            self.countdown_left = self._parse_hms(self.countdown_var.get())
        except Exception:
            self.countdown_left = 0.0
        self.countdown_var.set(self._format_hms(self.countdown_left))

    def _update_countdown_label(self) -> None:
        if self.countdown_running:
            left = max(0.0, self.countdown_left - (time.time() - self.countdown_start))
            self.countdown_var.set(self._format_hms(left))
            if left <= 0:
                self.countdown_running = False
                self.countdown_left = 0.0
                messagebox.showinfo("Countdown", "Time is up!")

    def _update_stopwatch_label(self) -> None:
        total = self.stopwatch_elapsed + (time.time() - self.stopwatch_start if self.stopwatch_running else 0.0)
        h = int(total // 3600); m = int((total % 3600) // 60); sec = total % 60
        self.stopwatch_var.set(f"{h:02d}:{m:02d}:{sec:04.1f}")
        if self.stopwatch_running:
            self.after(100, self._update_stopwatch_label)

    def start_stopwatch(self) -> None:
        if not self.stopwatch_running:
            self.stopwatch_running = True
            self.stopwatch_start = time.time()
            self._update_stopwatch_label()

    def stop_stopwatch(self) -> None:
        if self.stopwatch_running:
            self.stopwatch_elapsed += time.time() - self.stopwatch_start
            self.stopwatch_running = False
            self._update_stopwatch_label()

    def reset_stopwatch(self) -> None:
        self.stopwatch_running = False
        self.stopwatch_elapsed = 0.0
        self.stopwatch_start = 0.0
        self.stopwatch_var.set("00:00:00.0")

    def build_color_tab(self) -> None:
        f = ttk.Frame(self.color_tab, padding=12); f.pack(fill="both", expand=True)
        self.r = tk.IntVar(value=52); self.g = tk.IntVar(value=152); self.b = tk.IntVar(value=219); self.alpha_var = tk.IntVar(value=100); self.hex_var = tk.StringVar(value="#3498db"); self.hsl_var = tk.StringVar(); self.comp_var = tk.StringVar(); self.tone_var = tk.IntVar(value=0)
        left = ttk.LabelFrame(f, text="Picker / انتخاب رنگ", padding=8); left.grid(row=0, column=0, sticky="nsew")
        right = ttk.LabelFrame(f, text="History", padding=8); right.grid(row=0, column=1, sticky="nsew", padx=8)
        for i, (n, var) in enumerate((("R", self.r), ("G", self.g), ("B", self.b))):
            ttk.Label(left, text=n).grid(row=i, column=0, sticky="w")
            tk.Scale(left, from_=0, to=255, orient="horizontal", variable=var, command=lambda _x: self.update_color()).grid(row=i, column=1, sticky="ew")
        ttk.Label(left, text=self.tr("Tint/Shadow", "روشن/تیره")).grid(row=3, column=0, sticky="w")
        tk.Scale(left, from_=-100, to=100, orient="horizontal", variable=self.tone_var, command=lambda _x: self.update_color()).grid(row=3, column=1, sticky="ew")
        ttk.Label(left, text=self.tr("Transparency", "شفافیت")).grid(row=4, column=0, sticky="w")
        tk.Scale(left, from_=0, to=100, orient="horizontal", variable=self.alpha_var, command=lambda _x: self.update_color()).grid(row=4, column=1, sticky="ew")
        ttk.Entry(left, textvariable=self.hex_var, state="readonly").grid(row=0, column=2, sticky="ew")
        ttk.Entry(left, textvariable=self.hsl_var, state="readonly").grid(row=1, column=2, sticky="ew")
        ttk.Entry(left, textvariable=self.comp_var, state="readonly").grid(row=2, column=2, sticky="ew")
        ttk.Button(left, text="Copy HEX / کپی HEX", command=lambda: self.clipboard_clear() or self.clipboard_append(self.hex_var.get())).grid(row=3, column=2, sticky="ew")
        ttk.Button(left, text="Random Color", command=self.random_color).grid(row=5, column=2, sticky="ew")
        ttk.Button(left, text="Save to History", command=self.save_color_history).grid(row=6, column=2, sticky="ew")
        self.preview = tk.Canvas(left, width=200, height=70); self.preview.grid(row=7, column=2, sticky="ew")
        self.tint_canvas = tk.Canvas(left, height=50); self.tint_canvas.grid(row=8, column=0, columnspan=3, sticky="ew")
        self.shade_canvas = tk.Canvas(left, height=50); self.shade_canvas.grid(row=9, column=0, columnspan=3, sticky="ew")
        self.color_history_list = tk.Listbox(right); self.color_history_list.pack(fill="both", expand=True)


        left.columnconfigure(1, weight=1); left.columnconfigure(2, weight=1)
        f.columnconfigure(0, weight=3); f.columnconfigure(1, weight=1); f.rowconfigure(0, weight=1)
        self.update_color(); self.refresh_color_history()


    def _color_bucket_key(self, hx: str) -> str:
        r, g, b = (int(hx[i:i+2], 16) / 255 for i in (1, 3, 5))
        h, sv, v = colorsys.rgb_to_hsv(r, g, b)
        if sv < 0.35 and v > 0.79:
            return "light"
        if 0.02 <= h <= 0.17 and sv > 0.3 and 0.2 < v < 0.6:
            return "brown"
        if sv > 0.35 and 0.1 < v < 0.5:
            return "dark"
        if sv > 0.45 and 0.6 < v < 0.75:
            return "best"
        if v < 0.23 or sv < 0.2:
            return "black_gray"
        if h < 0.05 or h >= 0.94:
            return "red"
        if h < 0.131:
            return "orange"
        if h < 0.171:
            return "yellow"
        if h < 0.43:
            return "green"
        if h < 0.52:
            return "cyan"
        if h < 0.6763:
            return "blue"
        if h < 0.845:
            return "purple"
        return "pink"

    def build_colors_gallery_tab(self) -> None:
        f = ttk.Frame(self.colors_gallery_tab, padding=12); f.pack(fill="both", expand=True)
        self.famous_colors = PRESET_COLORS_1200

        sorted_colors = sorted(
            self.famous_colors,
            key=lambda item: (*colorsys.rgb_to_hsv(*(int(item[1][i:i+2], 16)/255 for i in (1, 3, 5))), item[0].lower()),
        )

        bucket_order = ["black_gray", "red", "orange", "yellow", "green", "cyan", "blue", "purple", "pink", "brown","dark","best","light"]
        names_en = {
            "black_gray": "Black+Gray", "red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green",
            "cyan": "Cyan", "blue": "Blue", "purple": "Purple", "pink": "Pink", "brown": "Brown","dark": "Dark","best": "Best","light":"Light"
        }
        names_fa = {
            "black_gray": "مشکی+خاکستری", "red": "قرمز", "orange": "نارنجی", "yellow": "زرد", "green": "سبز",
            "cyan": "فیروزه‌ای", "blue": "آبی", "purple": "بنفش", "pink": "صورتی", "brown": "قهوه‌ای", "dark":"تیره", "best" : "بهترین", "light":"روشن"
        }

        buckets = {k: [] for k in bucket_order}
        remaining = []
        for name, hx in sorted_colors:
            key = self._color_bucket_key(hx)
            buckets[key].append((name, hx))

        rem_i = 0
        for k in bucket_order:
            while len(buckets[k]) < 208 and rem_i < len(remaining):
                buckets[k].append(remaining[rem_i])
                rem_i += 1

        nb = ttk.Notebook(f); nb.pack(fill="both", expand=True)
        names = names_fa if self.lang_var.get() == "fa" else names_en
        for k in bucket_order:
            tab = ttk.Frame(nb)
            nb.add(tab, text=names[k])
            self.render_color_grid(tab, buckets[k][:208])

    def render_color_grid(self, parent: ttk.Frame, colors_list: list[tuple[str, str]]) -> None:
        for w in parent.winfo_children():
            w.destroy()
        cols = 12
        for i, (name, hx) in enumerate(colors_list):
            r = i // cols
            c = i % cols
            cell = tk.Frame(parent, bd=1, relief="solid", bg=hx)
            cell.grid(row=r, column=c, sticky="nsew", padx=2, pady=2)
            txt_col = "#111" if sum(int(hx[j:j+2], 16) for j in (1,3,5)) > 420 else "#fff"
            tk.Label(cell, text=f"{name}\n{hx}", bg=hx, fg=txt_col, width=24, height=2).pack(fill="both", expand=True)
            cell.bind("<Button-1>", lambda _e, c=hx: self._set_color_from_hex(c))
        for c in range(cols):
            parent.columnconfigure(c, weight=1)

    def random_color(self) -> None:
        self.r.set(random.randint(0,255)); self.g.set(random.randint(0,255)); self.b.set(random.randint(0,255)); self.update_color()

    def _set_color_from_hex(self, hx: str) -> None:
        h = hx.lstrip("#")
        self.r.set(int(h[0:2], 16)); self.g.set(int(h[2:4], 16)); self.b.set(int(h[4:6], 16))
        self.update_color()

    def update_color(self) -> None:
        r, g, b = self.r.get(), self.g.get(), self.b.get()
        tone = self.tone_var.get()/100.0
        if tone >= 0:
            r2 = int(r + (255-r)*tone); g2 = int(g + (255-g)*tone); b2 = int(b + (255-b)*tone)
        else:
            t = 1 + tone
            r2 = int(r*t); g2 = int(g*t); b2 = int(b*t)
        hx = f"#{r2:02x}{g2:02x}{b2:02x}"; self.hex_var.set(hx)
        h, l, s = colorsys.rgb_to_hls(r2/255, g2/255, b2/255); self.hsl_var.set(f"H={h*360:.1f}°, S={s*100:.1f}%, L={l*100:.1f}%")
        alpha = self.alpha_var.get()
        self.comp_var.set(f"Complement / مکمل: #{255-r2:02x}{255-g2:02x}{255-b2:02x} | A={alpha}% | RGBA={hx}{int(alpha*255/100):02x}")
        self._draw_alpha_preview(r2, g2, b2, alpha/100.0)

        for canvas, lighten in ((self.tint_canvas, True), (self.shade_canvas, False)):
            canvas.delete("all")
            w, hh = int(canvas.winfo_width() or 900), int(canvas.winfo_height() or 50)
            step = w / 10
            for i in range(10):
                t = (i+1)/10
                rr = int(r2 + (255-r2)*t) if lighten else int(r2*(1-t))
                gg = int(g2 + (255-g2)*t) if lighten else int(g2*(1-t))
                bb = int(b2 + (255-b2)*t) if lighten else int(b2*(1-t))
                hx_step = f"#{rr:02x}{gg:02x}{bb:02x}"
                tag = f"{('t' if lighten else 's')}{i}"
                canvas.create_rectangle(i*step, 0, (i+1)*step, hh, fill=hx_step, tags=(tag,), outline="")
                canvas.tag_bind(tag, "<Button-1>", lambda _e, c=hx_step: self._set_color_from_hex(c))

    def _draw_alpha_preview(self, r: int, g: int, b: int, alpha: float) -> None:
        self.preview.delete("all")
        w = int(self.preview.winfo_width() or 200)
        h = int(self.preview.winfo_height() or 70)
        block = 12
        c1 = (240, 240, 240)
        c2 = (195, 195, 195)
        for y in range(0, h, block):
            for x in range(0, w, block):
                base = c1 if ((x // block) + (y // block)) % 2 == 0 else c2
                rr = int(base[0] * (1 - alpha) + r * alpha)
                gg = int(base[1] * (1 - alpha) + g * alpha)
                bb = int(base[2] * (1 - alpha) + b * alpha)
                self.preview.create_rectangle(x, y, x + block, y + block, outline="", fill=f"#{rr:02x}{gg:02x}{bb:02x}")

    def save_color_history(self) -> None:
        if self.is_guest: return messagebox.showinfo("Guest / مهمان", "History is disabled in guest mode. / تاریخچه در حالت مهمان غیرفعال است.")
        add_color_history(self.username, f"({self.r.get()},{self.g.get()},{self.b.get()})", self.hex_var.get(), self.hsl_var.get())
        self.refresh_color_history()

    def refresh_color_history(self) -> None:
        self.color_history_list.delete(0, "end")
        for t, rgb, hx, hsl in get_color_history(self.username): self.color_history_list.insert("end", f"{t} | {rgb} | {hx} | {hsl}")

    def build_formula_tab_common(self, parent: ttk.Frame, formulas: list[FormulaSet]):
        mp = {x.name: x for x in formulas}; selected = tk.StringVar(value=formulas[0].name); entries = {}
        cb = ttk.Combobox(parent, textvariable=selected, values=[f"{x.name}" for x in formulas], state="readonly")
        cb.grid(row=0, column=0, columnspan=2, sticky="ew", pady=4)
        fields = ttk.Frame(parent); fields.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=6)
        out = tk.Text(parent, height=12); out.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=6)
        parent.columnconfigure(0, weight=1); parent.columnconfigure(1, weight=1); parent.rowconfigure(1, weight=1); parent.rowconfigure(3, weight=1)
        return selected, entries, out, fields, mp, cb

    def refresh_formula_fields(self, selected, fields, entries, mp, out):
        for w in fields.winfo_children(): w.destroy()
        entries.clear(); formula = mp[selected.get().split(" [", 1)[0]]
        for i, var in enumerate(formula.variables):
            ttk.Label(fields, text=var).grid(row=(i//4)*2, column=i%4, sticky="w")
            e = ttk.Entry(fields); e.grid(row=(i//4)*2+1, column=i%4, sticky="ew", padx=3, pady=3)
            entries[var] = e; fields.columnconfigure(i%4, weight=1)
        out.delete("1.0", "end"); out.insert("end", "Equations / معادلات:\n" + "\n".join(formula.equations))
        return formula

    def build_physics_tab(self) -> None:
        f = ttk.Frame(self.physics_tab, padding=12); f.pack(fill="both", expand=True)
        self.ph_selected, self.ph_entries, self.ph_out, self.ph_fields, self.ph_map, cb = self.build_formula_tab_common(f, PHYSICS_FORMULAS)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_formula_fields(self.ph_selected, self.ph_fields, self.ph_entries, self.ph_map, self.ph_out))
        ttk.Button(f, text="Solve / حل", command=self.solve_physics).grid(row=2, column=0, sticky="ew")
        ttk.Button(f, text="Clear / پاک کردن", command=lambda: self.refresh_formula_fields(self.ph_selected, self.ph_fields, self.ph_entries, self.ph_map, self.ph_out)).grid(row=2, column=1, sticky="ew")
        self.refresh_formula_fields(self.ph_selected, self.ph_fields, self.ph_entries, self.ph_map, self.ph_out)

    def solve_physics(self) -> None:
        formula = self.ph_map[self.ph_selected.get().split(" [", 1)[0]]
        known = {k: float(v.get()) for k, v in self.ph_entries.items() if v.get().strip()}
        solved = solve_formula_set(formula, known)
        self.ph_out.delete("1.0", "end")
        for v in formula.variables: self.ph_out.insert("end", f"{v} = {solved[v]:.12g}\n" if v in solved else f"{v} = (not enough data / داده کافی نیست)\n")

    def build_chemistry_tab(self) -> None:
        f = ttk.Frame(self.chem_tab, padding=12); f.pack(fill="both", expand=True)
        self.ch_selected, self.ch_entries, self.ch_out, self.ch_fields, self.ch_map, cb = self.build_formula_tab_common(f, CHEM_FORMULAS)
        cb.bind("<<ComboboxSelected>>", lambda _e: self.refresh_formula_fields(self.ch_selected, self.ch_fields, self.ch_entries, self.ch_map, self.ch_out))
        ttk.Button(f, text="Solve Chemistry / حل شیمی", command=self.solve_chemistry).grid(row=2, column=0, sticky="ew")
        ttk.Button(f, text="Clear / پاک کردن", command=lambda: self.refresh_formula_fields(self.ch_selected, self.ch_fields, self.ch_entries, self.ch_map, self.ch_out)).grid(row=2, column=1, sticky="ew")
        self.refresh_formula_fields(self.ch_selected, self.ch_fields, self.ch_entries, self.ch_map, self.ch_out)

    def solve_chemistry(self) -> None:
        formula = self.ch_map[self.ch_selected.get().split(" [", 1)[0]]
        known = {k: float(v.get()) for k, v in self.ch_entries.items() if v.get().strip()}
        solved = solve_formula_set(formula, known)
        self.ch_out.delete("1.0", "end")
        for v in formula.variables: self.ch_out.insert("end", f"{v} = {solved[v]:.12g}\n" if v in solved else f"{v} = (not enough data / داده کافی نیست)\n")

    def build_periodic_shape_tab(self) -> None:
        f = ttk.Frame(self.periodic_tab, padding=8); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Complete real-shaped periodic table / جدول تناوبی کامل").pack(anchor="w")
        canvas = tk.Canvas(f, bg="white"); canvas.pack(fill="both", expand=True)
        cell_w, cell_h = 58, 38
        for z, sym, period, group in PERIODIC_SHAPE:
            x1 = (group-1)*cell_w + 8; y1 = (period-1)*cell_h + 20
            canvas.create_rectangle(x1, y1, x1+cell_w-4, y1+cell_h-4, fill="#e8f1ff", outline="#456")
            canvas.create_text(x1 + 8, y1 + 7, text=str(z), font=("Arial", 6), anchor="w")
            canvas.create_text(x1 + 27, y1 + 18, text=sym, font=("Arial", 9, "bold"))
            canvas.create_text(x1 + 27, y1 + 30, text=ATOMIC_MASS.get(sym, "-"), font=("Arial", 6), fill="#334")
        canvas.configure(scrollregion=canvas.bbox("all"))

    def build_math_tab(self) -> None:
        f = ttk.Frame(self.math_tab, padding=12); f.pack(fill="both", expand=True)
        poly = ttk.LabelFrame(f, text="Grade 1/2/3 Polynomial Solver / حل‌گر چندجمله‌ای درجه ۱/۲/۳", padding=8); poly.grid(row=0, column=0, sticky="nsew")
        sys2 = ttk.LabelFrame(f, text="2x2 Equations Device / دستگاه معادلات ۲×۲", padding=8); sys2.grid(row=0, column=1, sticky="nsew", padx=8)
        prime = ttk.LabelFrame(f, text="Prime Checker (up to 12 digits)", padding=8); prime.grid(row=1, column=0, columnspan=2, sticky="ew", pady=8)
        self.ma, self.mb, self.mc, self.md = tk.StringVar(value="1"), tk.StringVar(value="0"), tk.StringVar(value="0"), tk.StringVar(value="0")
        self.mres = tk.StringVar()
        ttk.Label(poly, text="a*x³ + b*x² + c*x + d = 0").grid(row=0, column=0, sticky="w")
        for i, v in enumerate([self.ma, self.mb, self.mc, self.md]): ttk.Entry(poly, textvariable=v).grid(row=i+1, column=0, sticky="ew", pady=2)
        ttk.Button(poly, text="Solve / حل", command=self.solve_polynomial).grid(row=5, column=0, sticky="ew", pady=4)
        ttk.Entry(poly, textvariable=self.mres, state="readonly").grid(row=6, column=0, sticky="ew")

        self.sa11, self.sa12, self.sb1 = tk.StringVar(value="1"), tk.StringVar(value="1"), tk.StringVar(value="2")
        self.sa21, self.sa22, self.sb2 = tk.StringVar(value="1"), tk.StringVar(value="-1"), tk.StringVar(value="0")
        self.sres = tk.StringVar()
        ttk.Entry(sys2, textvariable=self.sa11).grid(row=0, column=0, sticky="ew"); ttk.Entry(sys2, textvariable=self.sa12).grid(row=0, column=1, sticky="ew"); ttk.Entry(sys2, textvariable=self.sb1).grid(row=0, column=2, sticky="ew")
        ttk.Entry(sys2, textvariable=self.sa21).grid(row=1, column=0, sticky="ew"); ttk.Entry(sys2, textvariable=self.sa22).grid(row=1, column=1, sticky="ew"); ttk.Entry(sys2, textvariable=self.sb2).grid(row=1, column=2, sticky="ew")
        ttk.Button(sys2, text="Solve System / حل دستگاه", command=self.solve_system2).grid(row=2, column=0, columnspan=3, sticky="ew", pady=4)
        ttk.Entry(sys2, textvariable=self.sres, state="readonly").grid(row=3, column=0, columnspan=3, sticky="ew")
        self.prime_in = tk.StringVar(value="2")
        self.prime_out = tk.StringVar()
        self.factor_out = tk.StringVar()
        ttk.Label(prime, text="Number").grid(row=0, column=0, sticky="w")
        ttk.Entry(prime, textvariable=self.prime_in).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(prime, text="Check", command=self.check_prime).grid(row=0, column=2, sticky="ew")
        ttk.Entry(prime, textvariable=self.prime_out, state="readonly").grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Entry(prime, textvariable=self.factor_out, state="readonly").grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        for i in range(3): sys2.columnconfigure(i, weight=1)
        prime.columnconfigure(1, weight=1)
        poly.columnconfigure(0, weight=1)
        f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=1); f.rowconfigure(0, weight=1)

    def solve_polynomial(self) -> None:
        a, b, c, d = float(self.ma.get()), float(self.mb.get()), float(self.mc.get()), float(self.md.get())
        if abs(a) < 1e-15:
            if abs(b) < 1e-15:
                self.mres.set("No unique solution / جواب یکتا ندارد" if abs(c) < 1e-15 else f"x = {-d/c:.12g}")
            else:
                disc = c*c - 4*b*d
                if disc >= 0:
                    r = math.sqrt(disc); self.mres.set(f"x1={(-c+r)/(2*b):.8g}, x2={(-c-r)/(2*b):.8g}")
                else:
                    rr = cmath.sqrt(disc); self.mres.set(f"x1={(-c+rr)/(2*b):.4g}, x2={(-c-rr)/(2*b):.4g}")
            return
        p = (3*a*c - b*b)/(3*a*a); q = (2*b*b*b - 9*a*b*c + 27*a*a*d)/(27*a*a*a)
        delta = (q/2)**2 + (p/3)**3; u = (-q/2 + cmath.sqrt(delta))**(1/3); v = (-q/2 - cmath.sqrt(delta))**(1/3)
        w = complex(-0.5, math.sqrt(3)/2)
        roots = [u+v-b/(3*a), w*u + w.conjugate()*v - b/(3*a), w.conjugate()*u + w*v - b/(3*a)]
        self.mres.set("; ".join([f"x{i+1}={rr.real:.6g}" if abs(rr.imag)<1e-8 else f"x{i+1}={rr:.4g}" for i, rr in enumerate(roots)]))

    def solve_system2(self) -> None:
        a11,a12,b1 = float(self.sa11.get()), float(self.sa12.get()), float(self.sb1.get())
        a21,a22,b2 = float(self.sa21.get()), float(self.sa22.get()), float(self.sb2.get())
        det = a11*a22 - a12*a21
        if abs(det) < 1e-12: self.sres.set("No unique solution / جواب یکتا ندارد"); return
        x = (b1*a22 - a12*b2)/det; y = (a11*b2 - b1*a21)/det
        self.sres.set(f"x={x:.12g}, y={y:.12g}")


    @staticmethod
    def _is_prime_12_digits(n: int) -> bool:
        if n < 2:
            return False
        small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29)
        if n in small_primes:
            return True
        if any(n % p == 0 for p in small_primes):
            return False
        d = n - 1
        s = 0
        while d % 2 == 0:
            s += 1
            d //= 2
        for a in (2, 3, 5, 7, 11, 13):
            if a >= n:
                continue
            x = pow(a, d, n)
            if x == 1 or x == n - 1:
                continue
            for _ in range(s - 1):
                x = pow(x, 2, n)
                if x == n - 1:
                    break
            else:
                return False
        return True

    @staticmethod
    def prime_factorization(n: int) -> list[int]:
        factors = []
        while n % 2 == 0:
            factors.append(2)
            n //= 2
        d = 3
        while d * d <= n:
            while n % d == 0:
                factors.append(d)
                n //= d
            d += 2
        if n > 1:
            factors.append(n)
        return factors

    def check_prime(self) -> None:
        txt = self.prime_in.get().strip()
        if not txt.isdigit():
            self.prime_out.set("Enter digits only / فقط عدد وارد کنید")
            self.factor_out.set("")
            return
        if len(txt) > 12:
            self.prime_out.set("Limit: up to 12 digits")
            self.factor_out.set("")
            return
        n = int(txt)
        is_prime = self._is_prime_12_digits(n)
        self.prime_out.set(f"{n} is prime" if is_prime else f"{n} is not prime")
        if n < 2:
            self.factor_out.set("Factors: none")
            return
        fac = self.prime_factorization(n)
        self.factor_out.set("Factors: " + " × ".join(str(x) for x in fac))

    def build_balancer_tab(self) -> None:
        f = ttk.Frame(self.balance_tab, padding=12); f.pack(fill="both", expand=True)
        self.bal_in = tk.StringVar(value="H2 + O2 = H2O"); self.bal_out = tk.StringVar(value="")
        ttk.Label(f, text="Chemical equation / معادله شیمیایی").pack(anchor="w")
        ttk.Entry(f, textvariable=self.bal_in).pack(fill="x", pady=4)
        ttk.Button(f, text="Balance / بالانس", command=self.balance_now).pack(fill="x", pady=4)
        ttk.Entry(f, textvariable=self.bal_out, state="readonly").pack(fill="x", pady=4)

    def balance_now(self) -> None:
        try: self.bal_out.set(balance_equation(self.bal_in.get().strip()))
        except Exception: self.bal_out.set("Could not balance. Check equation format like H2 + O2 = H2O / بالانس نشد. فرمت را مثل H2 + O2 = H2O وارد کنید")


    def build_tools_tab(self) -> None:
        f = ttk.Frame(self.tools_tab, padding=12); f.pack(fill="both", expand=True)
        bmi = ttk.LabelFrame(f, text="BMI Tool / ابزار BMI", padding=8); bmi.grid(row=0, column=0, sticky="nsew")
        pct = ttk.LabelFrame(f, text="Percentage Tool / ابزار درصد", padding=8); pct.grid(row=0, column=1, sticky="nsew", padx=8)

        self.bmi_weight = tk.StringVar(value="70")
        self.bmi_height = tk.StringVar(value="170")
        self.bmi_out = tk.StringVar()
        ttk.Label(bmi, text="Weight (kg) / وزن").grid(row=0, column=0, sticky="w")
        ttk.Entry(bmi, textvariable=self.bmi_weight).grid(row=1, column=0, sticky="ew")
        ttk.Label(bmi, text="Height (cm) / قد").grid(row=2, column=0, sticky="w")
        ttk.Entry(bmi, textvariable=self.bmi_height).grid(row=3, column=0, sticky="ew")
        ttk.Button(bmi, text="Calculate BMI / محاسبه BMI", command=self.calculate_bmi).grid(row=4, column=0, sticky="ew", pady=6)
        ttk.Entry(bmi, textvariable=self.bmi_out, state="readonly").grid(row=5, column=0, sticky="ew")

        self.pct_base = tk.StringVar(value="200")
        self.pct_percent = tk.StringVar(value="15")
        self.pct_out = tk.StringVar()
        ttk.Label(pct, text="Base value / مقدار پایه").grid(row=0, column=0, sticky="w")
        ttk.Entry(pct, textvariable=self.pct_base).grid(row=1, column=0, sticky="ew")
        ttk.Label(pct, text="Percent / درصد").grid(row=2, column=0, sticky="w")
        ttk.Entry(pct, textvariable=self.pct_percent).grid(row=3, column=0, sticky="ew")
        ttk.Button(pct, text="Calculate / محاسبه", command=self.calculate_percent).grid(row=4, column=0, sticky="ew", pady=6)
        ttk.Entry(pct, textvariable=self.pct_out, state="readonly").grid(row=5, column=0, sticky="ew")

        bmi.columnconfigure(0, weight=1); pct.columnconfigure(0, weight=1)
        f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=1); f.rowconfigure(0, weight=1)

    def calculate_bmi(self) -> None:
        try:
            w = float(self.bmi_weight.get()); h = float(self.bmi_height.get()) / 100.0
            bmi = w / (h*h)
            if bmi < 18.5: status = "Underweight / کم‌وزن"
            elif bmi < 25: status = "Normal / نرمال"
            elif bmi < 30: status = "Overweight / اضافه‌وزن"
            else: status = "Obese / چاق"
            self.bmi_out.set(f"BMI={bmi:.3g} | {status}")
        except Exception as exc:
            self.bmi_out.set(f"Error / خطا: {exc}")

    def calculate_percent(self) -> None:
        try:
            base = float(self.pct_base.get()); percent = float(self.pct_percent.get())
            self.pct_out.set(f"{percent:.6g}% of {base:.6g} = {(base*percent/100):.12g}")
        except Exception as exc:
            self.pct_out.set(f"Error / خطا: {exc}")


    def build_random_tab(self) -> None:
        f = ttk.Frame(self.random_tab, padding=12); f.pack(fill="both", expand=True)
        numf = ttk.LabelFrame(f, text="Number Generator / تولید عدد", padding=8); numf.grid(row=0, column=0, sticky="nsew")
        chf = ttk.LabelFrame(f, text="Random Chooser / انتخاب تصادفی", padding=8); chf.grid(row=0, column=1, sticky="nsew", padx=8)

        self.rand_digits = tk.IntVar(value=10)
        self.rand_num_out = tk.StringVar()
        ttk.Label(numf, text="Digits (1..50) / تعداد رقم").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(numf, from_=1, to=50, textvariable=self.rand_digits, width=8).grid(row=1, column=0, sticky="w")
        ttk.Button(numf, text="Generate / تولید", command=self.generate_random_number).grid(row=2, column=0, sticky="ew", pady=6)
        ttk.Entry(numf, textvariable=self.rand_num_out, state="readonly").grid(row=3, column=0, sticky="ew")

        self.chooser_input = tk.Text(chf, height=10)
        self.chooser_input.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.chooser_input.insert("1.0", "Option A\nOption B\nOption C")
        self.choice_pool: list[str] = []
        self.last_choice = tk.StringVar(value="")

        ttk.Button(chf, text="Load Options / بارگذاری گزینه‌ها", command=self.load_chooser_options).grid(row=1, column=0, sticky="ew", pady=4)
        ttk.Button(chf, text="Choose Random / انتخاب تصادفی", command=self.choose_random_option).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(chf, text="Eliminate Last / حذف آخرین", command=self.eliminate_last_choice).grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Entry(chf, textvariable=self.last_choice, state="readonly").grid(row=3, column=0, columnspan=2, sticky="ew", pady=6)

        numf.columnconfigure(0, weight=1)
        chf.columnconfigure(0, weight=1); chf.columnconfigure(1, weight=1); chf.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=2); f.rowconfigure(0, weight=1)

    def generate_random_number(self) -> None:
        digits = max(1, min(50, int(self.rand_digits.get() or 1)))
        first = str(random.randint(1, 9))
        tail = "".join(str(random.randint(0, 9)) for _ in range(digits - 1))
        self.rand_num_out.set(first + tail)

    def load_chooser_options(self) -> None:
        raw = self.chooser_input.get("1.0", "end-1c")
        options = [x.strip() for x in raw.splitlines() if x.strip()]
        self.choice_pool = options[:100]
        self.last_choice.set(self.tr(f"Loaded {len(self.choice_pool)} options", f"{len(self.choice_pool)} گزینه بارگذاری شد"))

    def choose_random_option(self) -> None:
        if not self.choice_pool:
            self.load_chooser_options()
        if not self.choice_pool:
            self.last_choice.set(self.tr("No options available", "گزینه‌ای وجود ندارد"))
            return
        choice = random.choice(self.choice_pool)
        self.last_choice.set(choice)

    def eliminate_last_choice(self) -> None:
        pick = self.last_choice.get().strip()
        if not pick:
            self.last_choice.set(self.tr("No last choice", "انتخاب آخری وجود ندارد"))
            return
        try:
            self.choice_pool.remove(pick)
            self.last_choice.set(self.tr(f"Removed: {pick}", f"حذف شد: {pick}"))
        except ValueError:
            self.last_choice.set(self.tr("Last choice already removed", "گزینه قبلاً حذف شده"))


    def build_geometry_tab(self) -> None:
        f = ttk.Frame(self.geometry_tab, padding=12); f.pack(fill="both", expand=True)
        shapes = ttk.LabelFrame(f, text="2D/3D Shapes / شکل‌های ۲بعدی-۳بعدی", padding=8); shapes.grid(row=0, column=0, sticky="nsew")

        self.shape_type = tk.StringVar(value="Circle")
        self.shape_a = tk.StringVar(value="5")
        self.shape_b = tk.StringVar(value="4")
        self.shape_c = tk.StringVar(value="3")
        self.shape_out = tk.StringVar()
        self.shape_hint_a = tk.StringVar()
        self.shape_hint_b = tk.StringVar()
        self.shape_hint_c = tk.StringVar()
        ttk.Label(shapes, text="Shape / شکل").grid(row=0, column=0, sticky="w")
        shape_box = ttk.Combobox(shapes, textvariable=self.shape_type, values=["Circle","Rectangle","Triangle","Parallelogram","Trapezoid","Cube","Cuboid","Cylinder","Cone","Sphere","Prism"], state="readonly")
        shape_box.grid(row=1, column=0, sticky="ew")
        shape_box.bind("<<ComboboxSelected>>", lambda _e: self.update_shape_param_hints())
        ttk.Label(shapes, textvariable=self.shape_hint_a).grid(row=2, column=0, sticky="w")
        ttk.Entry(shapes, textvariable=self.shape_a).grid(row=3, column=0, sticky="ew")
        ttk.Label(shapes, textvariable=self.shape_hint_b).grid(row=4, column=0, sticky="w")
        ttk.Entry(shapes, textvariable=self.shape_b).grid(row=5, column=0, sticky="ew")
        ttk.Label(shapes, textvariable=self.shape_hint_c).grid(row=6, column=0, sticky="w")
        ttk.Entry(shapes, textvariable=self.shape_c).grid(row=7, column=0, sticky="ew")
        ttk.Button(shapes, text="Compute / محاسبه", command=self.compute_shape).grid(row=8, column=0, sticky="ew", pady=6)
        ttk.Entry(shapes, textvariable=self.shape_out, state="readonly").grid(row=9, column=0, sticky="ew")

        self.update_shape_param_hints()
        shapes.columnconfigure(0, weight=1)
        f.columnconfigure(0, weight=1); f.rowconfigure(0, weight=1)

    def update_shape_param_hints(self) -> None:
        t = self.shape_type.get()
        hints = {
            "Circle": ("a = radius / شعاع", "b = unused / استفاده نمی‌شود", "c = unused / استفاده نمی‌شود"),
            "Rectangle": ("a = length / طول", "b = width / عرض", "c = unused / استفاده نمی‌شود"),
            "Triangle": ("a = side 1 / ضلع ۱", "b = side 2 / ضلع ۲", "c = side 3 / ضلع ۳"),
            "Cube": ("a = edge / ضلع مکعب", "b = unused / استفاده نمی‌شود", "c = unused / استفاده نمی‌شود"),
            "Cylinder": ("a = radius / شعاع", "b = height / ارتفاع", "c = unused / استفاده نمی‌شود"),
            "Sphere": ("a = radius / شعاع", "b = unused / استفاده نمی‌شود", "c = unused / استفاده نمی‌شود"),
            "Parallelogram": ("a = base / قاعده", "b = height / ارتفاع", "c = side / ضلع"),
            "Trapezoid": ("a = base1 / قاعده ۱", "b = base2 / قاعده ۲", "c = height / ارتفاع"),
            "Cuboid": ("a = length / طول", "b = width / عرض", "c = height / ارتفاع"),
            "Cone": ("a = radius / شعاع", "b = height / ارتفاع", "c = unused / استفاده نمی‌شود"),
            "Prism": ("a = base area / مساحت قاعده", "b = perimeter base / محیط قاعده", "c = height / ارتفاع"),
        }
        h1, h2, h3 = hints.get(t, ("a / پارامتر a", "b / پارامتر b", "c / پارامتر c"))
        self.shape_hint_a.set(h1)
        self.shape_hint_b.set(h2)
        self.shape_hint_c.set(h3)

    def compute_shape(self) -> None:
        try:
            t = self.shape_type.get()
            a = float(self.shape_a.get()); b = float(self.shape_b.get() or 0); c = float(self.shape_c.get() or 0)
            if t == "Circle":
                area = math.pi*a*a; per = 2*math.pi*a
                self.shape_out.set(f"A={area:.12g}, P={per:.12g}")
            elif t == "Rectangle":
                self.shape_out.set(f"A={(a*b):.12g}, P={(2*(a+b)):.12g}")
            elif t == "Triangle":
                s = (a+b+c)/2
                area = math.sqrt(max(0.0, s*(s-a)*(s-b)*(s-c)))
                self.shape_out.set(f"A={area:.12g}, P={(a+b+c):.12g}")
            elif t == "Cube":
                self.shape_out.set(f"V={(a**3):.12g}, S={(6*a*a):.12g}")
            elif t == "Cylinder":
                vol = math.pi*a*a*b; surf = 2*math.pi*a*(a+b)
                self.shape_out.set(f"V={vol:.12g}, S={surf:.12g}")
            elif t == "Sphere":
                self.shape_out.set(f"V={(4/3*math.pi*a**3):.12g}, S={(4*math.pi*a*a):.12g}")
            elif t == "Parallelogram":
                self.shape_out.set(f"A={(a*b):.12g}, P={(2*(a+c)):.12g}")
            elif t == "Trapezoid":
                self.shape_out.set(f"A={((a+b)*c/2):.12g}")
            elif t == "Cuboid":
                self.shape_out.set(f"V={(a*b*c):.12g}, S={(2*(a*b+b*c+a*c)):.12g}")
            elif t == "Cone":
                l = math.sqrt(a*a + b*b)
                self.shape_out.set(f"V={(math.pi*a*a*b/3):.12g}, S={(math.pi*a*(a+l)):.12g}")
            elif t == "Prism":
                self.shape_out.set(f"V={(a*c):.12g}, S={(2*a + b*c):.12g}")
        except Exception as exc:
            self.shape_out.set(f"Error / خطا: {exc}")

    def build_notes_tab(self) -> None:
        f = ttk.Frame(self.notes_tab, padding=12); f.pack(fill="both", expand=True)
        ttk.Label(f, text=self.tr("Quick Notes", "یادداشت سریع"), font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.notes_text = tk.Text(f, height=20)
        self.notes_text.pack(fill="both", expand=True, pady=8)
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key='quick_notes'").fetchone()
        if row:
            self.notes_text.insert("1.0", row[0])
        ttk.Button(f, text=self.tr("Save Notes", "ذخیره یادداشت"), command=self.save_notes).pack(anchor="e")

    def save_notes(self) -> None:
        set_setting("quick_notes", self.notes_text.get("1.0", "end-1c"))

    def build_bank_tab(self) -> None:
        f = ttk.Frame(self.bank_tab, padding=12); f.pack(fill="both", expand=True)
        loan = ttk.LabelFrame(f, text="Loan Calculator", padding=8); loan.grid(row=0, column=0, sticky="nsew")
        intr = ttk.LabelFrame(f, text="Interest Calculator", padding=8); intr.grid(row=0, column=1, sticky="nsew", padx=8)

        self.loan_principal = tk.StringVar(value="100000")
        self.loan_rate = tk.StringVar(value="18")
        self.loan_years = tk.StringVar(value="3")
        self.loan_out = tk.StringVar()
        ttk.Label(loan, text="Principal").grid(row=0, column=0, sticky="w")
        ttk.Entry(loan, textvariable=self.loan_principal).grid(row=1, column=0, sticky="ew")
        ttk.Label(loan, text="Rate % yearly").grid(row=2, column=0, sticky="w")
        ttk.Entry(loan, textvariable=self.loan_rate).grid(row=3, column=0, sticky="ew")
        ttk.Label(loan, text="Years").grid(row=4, column=0, sticky="w")
        ttk.Entry(loan, textvariable=self.loan_years).grid(row=5, column=0, sticky="ew")
        ttk.Button(loan, text="Calculate EMI", command=self.calculate_loan).grid(row=6, column=0, sticky="ew", pady=6)
        ttk.Entry(loan, textvariable=self.loan_out, state="readonly").grid(row=7, column=0, sticky="ew")

        self.int_principal = tk.StringVar(value="100000")
        self.int_rate = tk.StringVar(value="18")
        self.int_years = tk.StringVar(value="3")
        self.int_out = tk.StringVar()
        ttk.Label(intr, text="Principal").grid(row=0, column=0, sticky="w")
        ttk.Entry(intr, textvariable=self.int_principal).grid(row=1, column=0, sticky="ew")
        ttk.Label(intr, text="Rate % yearly").grid(row=2, column=0, sticky="w")
        ttk.Entry(intr, textvariable=self.int_rate).grid(row=3, column=0, sticky="ew")
        ttk.Label(intr, text="Years").grid(row=4, column=0, sticky="w")
        ttk.Entry(intr, textvariable=self.int_years).grid(row=5, column=0, sticky="ew")
        ttk.Button(intr, text="Simple+Compound", command=self.calculate_interest).grid(row=6, column=0, sticky="ew", pady=6)
        ttk.Entry(intr, textvariable=self.int_out, state="readonly").grid(row=7, column=0, sticky="ew")

        loan.columnconfigure(0, weight=1); intr.columnconfigure(0, weight=1)
        f.columnconfigure(0, weight=1); f.columnconfigure(1, weight=1); f.rowconfigure(0, weight=1)

    def calculate_interest(self) -> None:
        try:
            p = float(self.int_principal.get()); r = float(self.int_rate.get())/100.0; y = float(self.int_years.get())
            simple = p*r*y
            compound = p*((1+r)**y - 1)
            self.int_out.set(f"Simple={simple:.12g}, Compound={compound:.12g}")
        except Exception as exc:
            self.int_out.set(f"Error: {exc}")

    def calculate_loan(self) -> None:
        try:
            p = float(self.loan_principal.get())
            r = float(self.loan_rate.get()) / 1200.0
            n = int(float(self.loan_years.get()) * 12)
            emi = p/n if abs(r) < 1e-15 else p*r*((1+r)**n)/(((1+r)**n)-1)
            total = emi*n
            self.loan_out.set(f"EMI={emi:.12g}, Total={total:.12g}, Interest={(total-p):.12g}")
        except Exception as exc:
            self.loan_out.set(f"Error: {exc}")

def main() -> None:
    init_db(); init_lang_db(); LoginWindow().mainloop()


if __name__ == "__main__":
    main()
