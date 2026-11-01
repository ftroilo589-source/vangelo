"""Scarica la liturgia del giorno da chiesacattolica.it e scrive vangelo.json (solo il Vangelo, versione compatta per widget)."""
import json
import re
import sys
import datetime as dt
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://www.chiesacattolica.it/liturgia-del-giorno/?data-liturgia={d}"
ROMA = ZoneInfo("Europe/Rome")

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


def data_oggi():
    # la data è quella di oggi a Roma: il run di mezzanotte prepara il giorno appena iniziato
    return dt.datetime.now(ROMA).date()


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


def pulisci_vangelo(corpo):
    """Restituisce (riferimento, testo): via monizione, intestazione del brano e formula finale."""
    rif, testo = "", corpo
    for i, r in enumerate(corpo):
        if r.lower().startswith("dal vangelo secondo"):
            if i + 1 < len(corpo):
                rif = corpo[i + 1]
            testo = corpo[i + 2 :]
            break
    else:
        m = re.search(r"\b(?:Mt|Mc|Lc|Gv)\s*\d+[\d,\.\-–a-z]*", " ".join(corpo[:4]))
        rif = m.group(0) if m else ""
    fine = []
    for r in testo:
        if r.startswith(("Parola del Signore", "Parola di Dio", "Si dice il Credo")):
            break
        fine.append(r)
    return rif.strip(), "\n".join(fine).strip()


def celebrazione(righe):
    """Nome della celebrazione e colore liturgico: la riga prima e dopo 'Colore liturgico'."""
    for i, r in enumerate(righe):
        if norm(r) == "colore liturgico" and i >= 1 and i + 1 < len(righe):
            nome = re.sub(r"\(.*?\)", "", righe[i - 1]).strip()
            return nome, righe[i + 1].strip().lower()
    return "", ""


def tipo(nome):
    n = nome.lower()
    for chiave, etichetta in [("solennit", "Solennità"), ("festa", "Festa"),
                              ("memoria", "Memoria"), ("domenica", "Domenica")]:
        if chiave in n:
            return etichetta
    return "Feria"


def main():
    giorno = data_oggi()
    html = scarica(giorno)
    righe, _ = righe_da_html(html)
    sezioni = estrai(righe)
    corpo = next((c for n, c in (sezioni or []) if n == "Vangelo"), None)
    if not corpo:
        open("debug.html", "w", encoding="utf-8").write(html)
        open("debug.txt", "w", encoding="utf-8").write("\n".join(righe))
        print("Vangelo non trovato: salvati debug.html e debug.txt", file=sys.stderr)
        sys.exit(1)

    rif, testo = pulisci_vangelo(corpo)
    nome, colore = celebrazione(righe)
    out = {
        "data": giorno.isoformat(),
        "celebrazione": nome,
        "tipo": tipo(nome),
        "colore": colore,
        "riferimento": rif,
        "vangelo": testo,
    }
    with open("vangelo.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("OK", out["data"], out["tipo"], out["riferimento"])


if __name__ == "__main__":
    main()
