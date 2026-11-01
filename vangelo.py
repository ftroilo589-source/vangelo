"""Scarica la liturgia da chiesacattolica.it (solo letture, niente preghiere del messale).

- vangelo.json: oggi + i prossimi 14 giorni, aggiornato ogni notte
- anno_AAAA.json: tutto l'anno corrente, creato la prima volta che manca
  (quindi automaticamente al primo run di ogni nuovo anno)
"""
import json
import re
import sys
import time
import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://www.chiesacattolica.it/liturgia-del-giorno/?data-liturgia={d}"
ROMA = ZoneInfo("Europe/Rome")
PAUSA = 0.5
GIORNI_PROSSIMI = 14

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
LETTURE = ["Prima lettura", "Salmo responsoriale", "Seconda lettura", "Canto al Vangelo", "Vangelo"]


def norm(riga):
    r = re.sub(r"[^\w\s]", " ", riga.lower())
    return re.sub(r"\s+", " ", r).strip()


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
    return [r for r in righe if r]


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


def taglia(corpo):
    """Ferma il testo appena inizia la parte successiva (altra messa, footer, formula finale)."""
    out = []
    for r in corpo:
        if (r.upper().startswith("COMMEMORAZIONE")
                or norm(r).startswith(("colore liturgico", "conferenza episcopale"))
                or r.startswith(("Parola del Signore", "Parola di Dio", "Si dice il Credo"))):
            break
        out.append(r)
    return out


def riferimento(corpo):
    for r in corpo[:8]:
        m = re.match(r"^((?:Mt|Mc|Lc|Gv)\s*\d[\d,\.\-–a-z ]*)$", r)
        if m:
            return m.group(1).strip()
    return ""


def fonte_e_testo(corpo):
    corpo = taglia(corpo)
    fonte = ""
    for i, r in enumerate(corpo):
        if r.lower().startswith(("dal ", "dalla ", "dall'", "dall’")):
            fonte = r
            corpo = corpo[i + 1 :]
            break
    testo = []
    for r in corpo:
        if r in {".", "(", ")"} or re.match(r"^[A-Za-zÀ-ú]{1,4}\s*\d", r):
            continue  # riferimenti biblici e segni tipografici
        testo.append(r)
    return fonte, "\n".join(testo).strip()


def celebrazione(righe):
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


def costruisci_voce(giorno, righe):
    """Ricava la voce di un giorno dalle righe della pagina. Ritorna None se non c'è il Vangelo."""
    sezioni = estrai(righe)
    if not sezioni:
        return None
    viste = {}
    colletta = 0
    for nome, corpo in sezioni:
        if nome == "Colletta":
            colletta += 1
            if colletta > 1:  # inizia la messa successiva: non la leggiamo
                break
        if nome in LETTURE and nome not in viste:
            viste[nome] = corpo
    if "Vangelo" not in viste:
        return None

    letture = []
    for nome in LETTURE:
        if nome not in viste:
            continue
        fonte, testo = fonte_e_testo(viste[nome])
        voce = {"nome": nome, "fonte": fonte, "testo": testo}
        if nome == "Vangelo":
            voce["riferimento"] = riferimento(viste[nome])
        letture.append(voce)

    vangelo = next(l for l in letture if l["nome"] == "Vangelo")
    nome_cel, colore = celebrazione(righe)
    return {
        "data": giorno.isoformat(),
        "celebrazione": nome_cel,
        "tipo": tipo(nome_cel),
        "colore": colore,
        "riferimento": vangelo.get("riferimento", ""),
        "vangelo": vangelo["testo"],
        "letture": letture,
    }


def leggi_range(inizio, fine):
    giorni, falliti = [], []
    g = inizio
    while g <= fine:
        try:
            voce = costruisci_voce(g, righe_da_html(scarica(g)))
        except Exception as e:
            print("Errore", g, e, file=sys.stderr)
            voce = None
        if voce:
            giorni.append(voce)
        else:
            falliti.append(g.isoformat())
        g += dt.timedelta(days=1)
        time.sleep(PAUSA)
    return giorni, falliti


def scrivi(nome, dati):
    with open(nome, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)


def main():
    oggi = dt.datetime.now(ROMA).date()

    prossimi, falliti = leggi_range(oggi, oggi + dt.timedelta(days=GIORNI_PROSSIMI - 1))
    if not prossimi:
        print("Nessun giorno letto: controlla la pagina", file=sys.stderr)
        sys.exit(1)
    scrivi("vangelo.json", {
        "generato": dt.datetime.now(ROMA).isoformat(timespec="minutes"),
        "giorni": prossimi,
    })
    print("OK prossimi giorni:", len(prossimi), "saltati:", falliti)

    file_anno = Path(f"anno_{oggi.year}.json")
    if not file_anno.exists():
        inizio = dt.date(oggi.year, 1, 1)
        fine = dt.date(oggi.year, 12, 31)
        tutti, falliti = leggi_range(inizio, fine)
        totale = (fine - inizio).days + 1
        if len(tutti) >= 0.9 * totale:
            scrivi(file_anno.name, {"anno": oggi.year, "giorni": tutti})
            print("OK anno", oggi.year, len(tutti), "giorni su", totale)
        else:
            print("Anno incompleto, riprovo al prossimo run:", len(tutti), "su", totale,
                  file=sys.stderr)


if __name__ == "__main__":
    main()
