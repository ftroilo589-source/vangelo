"""Scarica la liturgia del giorno da chiesacattolica.it (testo CEI) e scrive vangelo.json."""
import json
import re
import sys
import datetime as dt
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://www.chiesacattolica.it/liturgia-del-giorno/?data-liturgia={d}"
ROMA = ZoneInfo("Europe/Rome")

# etichette delle sezioni (normalizzate: minuscolo, senza punteggiatura)
SEZIONI = {
    "antifona d ingresso": "Antifona d'ingresso",
    "antifona di ingresso": "Antifona d'ingresso",
    "antifona ingresso": "Antifona d'ingresso",
    "colletta": "Colletta",
    "prima lettura": "Prima lettura",
    "salmo responsoriale": "Salmo responsoriale",
    "seconda lettura": "Seconda lettura",
    "canto al vangelo": "Canto al Vangelo",
    "acclamazione al vangelo": "Canto al Vangelo",
    "vangelo": "Vangelo",
    "sulle offerte": "Sulle offerte",
    "antifona alla comunione": "Antifona alla comunione",
    "antifona di comunione": "Antifona alla comunione",
    "dopo la comunione": "Dopo la comunione",
    "preghiera dopo la comunione": "Dopo la comunione",
}
INIZIO = {"Antifona d'ingresso", "Colletta", "Prima lettura", "Salmo responsoriale"}


def norm(riga):
    r = re.sub(r"[^\w\s]", " ", riga.lower())
    return re.sub(r"\s+", " ", r).strip()


def data_target():
    ora = dt.datetime.now(ROMA)
    # dopo mezzogiorno (es. 23:05 ora di Roma) si prepara già il giorno dopo
    return (ora + dt.timedelta(days=1)).date() if ora.hour >= 12 else ora.date()


def scarica(giorno):
    r = requests.get(
        URL.format(d=giorno.strftime("%Y%m%d")),
        headers={"User-Agent": "Mozilla/5.0 (uso personale)"},
        timeout=30,
    )
    r.raise_for_status()
    return r.text


def righe_da_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    testo = soup.get_text("\n")
    righe = [re.sub(r"\s+", " ", r).strip() for r in testo.split("\n")]
    return [r for r in righe if r], soup


def estrai(righe):
    marcatori = [(i, SEZIONI[norm(r)]) for i, r in enumerate(righe) if norm(r) in SEZIONI]
    # si parte dalla prima sezione "vera" (scarta voci di menu prima del contenuto)
    start = next((k for k, (_, nome) in enumerate(marcatori) if nome in INIZIO), None)
    if start is None:
        return None
    marcatori = marcatori[start:]
    sezioni = []
    for k, (i, nome) in enumerate(marcatori):
        fine = marcatori[k + 1][0] if k + 1 < len(marcatori) else len(righe)
        corpo = righe[i + 1 : fine]
        if corpo:
            sezioni.append((nome, corpo))
    return sezioni


def main():
    giorno = data_target()
    html = scarica(giorno)
    righe, soup = righe_da_html(html)
    sezioni = estrai(righe)
    vangelo = next(((n, c) for n, c in (sezioni or []) if n == "Vangelo"), None)
    if not vangelo:
        open("debug.html", "w", encoding="utf-8").write(html)
        open("debug.txt", "w", encoding="utf-8").write("\n".join(righe))
        print("Vangelo non trovato: salvati debug.html e debug.txt", file=sys.stderr)
        sys.exit(1)

    corpo = vangelo[1]
    rif = re.search(r"\b(?:Mt|Mc|Lc|Gv)\s*\d+[\d,\.\-–a-z\s]*", " ".join(corpo[:4]))
    h = soup.find(["h1", "h2"])
    out = {
        "data": giorno.isoformat(),
        "titolo": h.get_text(" ", strip=True) if h else "",
        "riferimento": rif.group(0).strip() if rif else "",
        "vangelo": "\n".join(corpo),
        "resto": "\n\n".join(
            n.upper() + "\n" + "\n".join(c) for n, c in sezioni if n != "Vangelo"
        ),
        "generato": dt.datetime.now(ROMA).isoformat(timespec="minutes"),
    }
    with open("vangelo.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("OK", out["data"], out["riferimento"])


if __name__ == "__main__":
    main()
