#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bis_diff.py
============
Confronta l'EQUIPAGGIAMENTO ATTUALE di un personaggio di World of Warcraft
(reami TBC Anniversary) con la sua BIS LIST presa da wowtbc.gg, e ti dice
slot per slot cosa ti manca.

FONTI DEI DATI
--------------
* Equip attuale  -> API ufficiale di Blizzard (la STESSA fonte usata da
                    classic-armory.org, ma in JSON pulito). Host eu.api.blizzard.com,
                    namespace "profile-classicann-eu" per i reami TBC Anniversary.
* BiS list       -> pagina https://wowtbc.gg/bis-list/<classe-spec>/  (sito statico,
                    si legge direttamente dall'HTML).

COSA PRODUCE
------------
* Una tabella a video con: slot | item attuale | item BiS | match.
* Un file di testo (bis_diff_<nome>_<regione>_<data>.txt) con lo stesso contenuto.

DIPENDENZE
----------
    pip install requests beautifulsoup4

CHIAVE API BLIZZARD (gratuita, una volta sola)
----------------------------------------------
1) Vai su  https://develop.battle.net/access/clients  (login col tuo account Battle.net).
2) Clicca "Create Client", dai un nome qualsiasi (es. "bisdiff"), lascia il resto vuoto.
3) Copia il "Client ID" e il "Client Secret".
Alla prima esecuzione lo script te li chiede e li salva in "blizzard_api.json"
(nella stessa cartella), così non li reinserisci più.
In alternativa puoi metterli nelle variabili d'ambiente
BLIZZARD_CLIENT_ID e BLIZZARD_CLIENT_SECRET.
"""

import os
import re
import sys
import csv
import json
import time
import datetime
from getpass import getpass
from urllib.parse import quote

try:
    import requests
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    print("Mancano delle dipendenze. Installale con:\n")
    print("    pip install requests beautifulsoup4\n")
    sys.exit(1)


# --------------------------------------------------------------------------- #
#  Config / costanti
# --------------------------------------------------------------------------- #

HERE = os.path.dirname(os.path.abspath(__file__))
CRED_FILE = os.path.join(HERE, "blizzard_api.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Etichette di slot usate da wowtbc.gg  ->  tipo di slot dell'API Blizzard.
# (Tengo varianti diverse per robustezza tra le varie spec.)
LABEL_TO_SLOT = {
    "head": "HEAD",
    "neck": "NECK",
    "shoulder": "SHOULDER", "shoulders": "SHOULDER",
    "back": "BACK", "cloak": "BACK",
    "chest": "CHEST",
    "wrist": "WRIST", "wrists": "WRIST", "bracers": "WRIST",
    "hands": "HANDS", "gloves": "HANDS",
    "waist": "WAIST", "belt": "WAIST",
    "legs": "LEGS",
    "feet": "FEET", "boots": "FEET",
    "finger 1": "FINGER_1", "ring 1": "FINGER_1",
    "finger 2": "FINGER_2", "ring 2": "FINGER_2",
    "trinket 1": "TRINKET_1",
    "trinket 2": "TRINKET_2",
    "weapon": "MAIN_HAND", "main hand": "MAIN_HAND",
    "two hand": "MAIN_HAND", "two-hand": "MAIN_HAND", "2h": "MAIN_HAND",
    "off hand": "OFF_HAND", "offhand": "OFF_HAND", "off-hand": "OFF_HAND",
    "ranged": "RANGED", "relic": "RANGED", "wand": "RANGED",
    "idol": "RANGED", "totem": "RANGED", "libram": "RANGED", "thrown": "RANGED",
}
# Set di etichette riconoscibili nel testo della pagina BiS.
SLOT_LABELS = set(LABEL_TO_SLOT.keys())

# Ordine + nome (in inglese, come nell'API) per la stampa finale.
SLOT_DISPLAY = [
    ("HEAD", "Head"),
    ("NECK", "Neck"),
    ("SHOULDER", "Shoulder"),
    ("BACK", "Back"),
    ("CHEST", "Chest"),
    ("WRIST", "Wrist"),
    ("HANDS", "Hands"),
    ("WAIST", "Waist"),
    ("LEGS", "Legs"),
    ("FEET", "Feet"),
    ("FINGER_1", "Finger 1"),
    ("FINGER_2", "Finger 2"),
    ("TRINKET_1", "Trinket 1"),
    ("TRINKET_2", "Trinket 2"),
    ("MAIN_HAND", "Main Hand"),
    ("OFF_HAND", "Off Hand"),
    ("RANGED", "Ranged"),
]

# Sigle brevi (in inglese) per la riga di riepilogo rapido / intestazione matrice.
SLOT_ABBR = {
    "HEAD": "Hd", "NECK": "Nk", "SHOULDER": "Sh", "BACK": "Bk", "CHEST": "Ch",
    "WRIST": "Wr", "HANDS": "Hn", "WAIST": "Ws", "LEGS": "Lg", "FEET": "Ft",
    "FINGER_1": "F1", "FINGER_2": "F2", "TRINKET_1": "T1", "TRINKET_2": "T2",
    "MAIN_HAND": "MH", "OFF_HAND": "OH", "RANGED": "Rg",
}


# --------------------------------------------------------------------------- #
#  Utility
# --------------------------------------------------------------------------- #

def norm(s):
    """Normalizza un nome di item per confrontarlo (minuscole, spazi, apostrofi)."""
    if not s:
        return ""
    s = s.strip().lower()
    s = s.replace("\u2019", "'").replace("`", "'").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def slugify_spec(text):
    """'Shadow Priest' -> 'shadow-priest' (per l'URL di wowtbc.gg)."""
    s = text.strip().lower()
    s = s.replace("&", " ").replace("/", " ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


# --------------------------------------------------------------------------- #
#  Credenziali Blizzard
# --------------------------------------------------------------------------- #

def load_credentials():
    """Legge client id/secret da env, poi da file, altrimenti li chiede e li salva."""
    cid = os.environ.get("BLIZZARD_CLIENT_ID")
    secret = os.environ.get("BLIZZARD_CLIENT_SECRET")
    if cid and secret:
        return cid.strip(), secret.strip()

    if os.path.exists(CRED_FILE):
        try:
            with open(CRED_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("client_id") and data.get("client_secret"):
                return data["client_id"].strip(), data["client_secret"].strip()
        except Exception:
            pass

    print("\n--- Chiave API Blizzard (serve solo la prima volta) ---")
    print("Creane una gratis su: https://develop.battle.net/access/clients")
    cid = input("Client ID: ").strip()
    secret = getpass("Client Secret (non viene mostrato): ").strip()
    if input("Salvare le credenziali in blizzard_api.json? [s/N]: ").strip().lower() in ("s", "si", "sì", "y", "yes"):
        try:
            with open(CRED_FILE, "w", encoding="utf-8") as f:
                json.dump({"client_id": cid, "client_secret": secret}, f)
            print(f"Salvate in {CRED_FILE}")
        except Exception as e:
            print(f"(Non sono riuscito a salvarle: {e})")
    return cid, secret


def get_token(cid, secret):
    """Ottiene un access token OAuth con il flusso client_credentials."""
    r = requests.post(
        "https://oauth.battle.net/token",
        data={"grant_type": "client_credentials"},
        auth=(cid, secret),
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(
            f"Login Blizzard fallito (HTTP {r.status_code}). "
            "Controlla Client ID/Secret. Risposta: " + r.text[:200]
        )
    return r.json()["access_token"]


# --------------------------------------------------------------------------- #
#  Equip attuale (API Blizzard)
# --------------------------------------------------------------------------- #

def get_current_gear(region, realm, name, token):
    """
    Ritorna un dict {SLOT_TYPE: {"name": str, "ilvl": int|None}} con l'equip attuale.
    Prova prima il namespace dei reami progression (TBC Anniversary), poi quello Era.
    """
    region = region.lower()
    host = f"https://{region}.api.blizzard.com"
    realm_slug = realm.strip().lower().replace(" ", "-").replace("'", "")
    name_path = quote(name.strip().lower())

    url = f"{host}/profile/wow/character/{realm_slug}/{name_path}/equipment"
    headers = {"Authorization": f"Bearer {token}"}

    # I reami TBC Anniversary usano il namespace "classicann" (documentato da
    # Blizzard a fine gennaio 2026). Lo provo per primo; gli altri sono fallback.
    namespaces = (
        f"profile-classicann-{region}",   # TBC Anniversary  <-- quello giusto
        f"profile-classic-{region}",      # Progression (fallback)
        f"profile-classic1x-{region}",    # Era (fallback)
    )
    tried = []
    for namespace in namespaces:
        params = {"namespace": namespace, "locale": "en_US"}
        r = requests.get(url, headers=headers, params=params, timeout=30)
        tried.append(f"{namespace}  ->  HTTP {r.status_code}")
        if r.status_code == 200:
            return _parse_equipment(r.json()), namespace
        # 404 = non trovato in quel namespace, provo il prossimo.
        # 401/403 = problema di token/permessi: inutile insistere.
        if r.status_code in (401, 403):
            break

    raise RuntimeError(
        "Non riesco a leggere l'equip del personaggio.\n"
        f"URL: {url}\n"
        f"Reame (slug): {realm_slug}   Nome: {name.strip().lower()}\n"
        "Namespace provati:\n  " + "\n  ".join(tried) + "\n\n"
        "- Se sono TUTTI 404: ricontrolla nome/reame/regione e che il personaggio "
        "sia loggato almeno una volta (i nuovi personaggi ci mettono un po').\n"
        "- Se vedi 401/403: problema con la chiave API (Client ID/Secret) o permessi."
    )


def _parse_equipment(data):
    gear = {}
    for it in data.get("equipped_items", []):
        slot_type = (it.get("slot") or {}).get("type")
        if not slot_type:
            continue
        item_name = it.get("name") or (it.get("item") or {}).get("name")
        ilvl = (it.get("level") or {}).get("value")
        gear[slot_type] = {"name": item_name, "ilvl": ilvl}
    return gear


# --------------------------------------------------------------------------- #
#  BiS list (scraping wowtbc.gg)
# --------------------------------------------------------------------------- #

def fetch_bis(spec_slug):
    """Scarica e analizza la BiS list. Ritorna (dict {SLOT_TYPE: nome}, url)."""
    url = f"https://wowtbc.gg/bis-list/{spec_slug}/"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    if r.status_code == 404:
        raise RuntimeError(
            f"Pagina BiS non trovata: {url}\n"
            "Controlla classe/spec (es. 'Shadow Priest', 'Beast Mastery Hunter', "
            "'Fury Warrior'...)."
        )
    r.raise_for_status()
    labels_to_names = parse_bis_html(r.text)
    if not labels_to_names:
        raise RuntimeError(
            "Ho scaricato la pagina ma non sono riuscito a estrarre la BiS list "
            "(forse il sito ha cambiato struttura). URL: " + url
        )
    # Converto le etichette di wowtbc nei tipi di slot dell'API Blizzard.
    bis_by_slot = {}
    for label, item_name in labels_to_names.items():
        slot = LABEL_TO_SLOT.get(label)
        if slot and slot not in bis_by_slot:
            bis_by_slot[slot] = item_name
    return bis_by_slot, url


# Parole con cui iniziano (o che contengono) gli INCANTESIMI, per distinguerli
# dal nome dell'item quando precedono l'etichetta di slot.
ENCHANT_PREFIXES = (
    "glyph", "greater inscription", "lesser inscription", "inscription of",
    "arcanum", "runic spellthread", "mystic spellthread", "golden spellthread",
    "silver spellthread", "spellthread", "enchant",
)


def _looks_like_enchant(text):
    t = text.lower()
    if " - " in t:                       # es. "Bracer - Spellpower", "Weapon - Soulfrost"
        return True
    # Incantesimi/kit per le gambe (NON sono oggetti): Nethercobra/Nethercleft/
    # Cobrahide/Clefthide "Leg Armor", e gli "Armor Kit".
    if t.endswith("leg armor") or t.endswith("armor kit"):
        return True
    # es. "Glyph of Power"
    return any(t.startswith(p) for p in ENCHANT_PREFIXES)


def _looks_like_item(name):
    """True se 'name' sembra un vero nome di oggetto (scarta refusi tipo '(35%)',
    percentuali o numeri isolati che a volte compaiono nello slot off-hand)."""
    if not name:
        return False
    return bool(re.search(r"[A-Za-z]{3,}", name))


def _text_tokens(soup):
    """Tutti i nodi di testo non vuoti, in ordine di documento (salta script/style)."""
    toks = []
    for el in soup.descendants:
        if isinstance(el, NavigableString):
            if any(p.name in ("script", "style", "noscript", "head")
                   for p in el.parents if isinstance(p, Tag)):
                continue
            t = re.sub(r"\s+", " ", str(el)).strip()
            if t:
                toks.append(t)
    return toks


def parse_bis_text(soup):
    """
    Parser principale (NON dipende dalle icone, quindi immune al lazy-load).

    In ordine di documento ogni riga della BiS e':
        NomeItem, [NomeIncantesimo], ETICHETTA_SLOT, Fonte1, [Fonte2]
    Quindi mi ancoro alle etichette di slot (head, neck, ...) e prendo come item
    il testo che le precede; se quel testo e' un incantesimo, prendo quello prima.
    """
    toks = _text_tokens(soup)
    low = [t.lower() for t in toks]
    n = len(toks)

    # Inizio dopo l'intestazione "Gear / Slot / Source" (se c'e'); fine al footer.
    start = 0
    for i in range(n - 2):
        if low[i] == "gear" and low[i + 1] == "slot" and low[i + 2] == "source":
            start = i + 3
            break
    end = n
    for i in range(start, n):
        if "class guide" in low[i] or low[i].startswith("wowtbc.gg"):
            end = i
            break

    result = {}
    i = start
    while i < end:
        # L'etichetta di slot puo' essere un solo token ("head") o due ("off hand").
        label, consumed = None, 1
        if low[i] in SLOT_LABELS:
            label = low[i]
        elif i + 1 < end and (low[i] + " " + low[i + 1]) in SLOT_LABELS:
            label, consumed = low[i] + " " + low[i + 1], 2

        if label:
            j = i - 1
            item = None
            if j >= 0:
                cand = toks[j]
                if _looks_like_enchant(cand) and j - 1 >= 0:
                    item = toks[j - 1]
                else:
                    item = cand
            # scarta refusi tipo "(35%)"
            if item and not _looks_like_item(item):
                item = None
            if item and label not in result:
                result[label] = item
            i += consumed
        else:
            i += 1
    return result


def _img_attr_has(tag, needle):
    """True se QUALSIASI attributo dell'<img> contiene 'needle' (es. '/WOW/Items/')."""
    for v in tag.attrs.values():
        if isinstance(v, (list, tuple)):
            v = " ".join(v)
        if isinstance(v, str) and needle in v:
            return True
    return False


def parse_bis_images(soup):
    """Rete di sicurezza: usa le icone (cartella /WOW/Items/) quando l'URL e' presente."""
    entries = []

    def walk(node):
        for child in node.children:
            if isinstance(child, NavigableString):
                txt = re.sub(r"\s+", " ", str(child)).strip().lower()
                if txt in SLOT_LABELS:
                    for e in reversed(entries):
                        if e["slot"] is None:
                            e["slot"] = txt
                            break
            elif isinstance(child, Tag):
                if child.name == "img":
                    if _img_attr_has(child, "/WOW/Items/"):
                        name = (child.get("alt") or "").strip()
                        if name and _looks_like_item(name) and not _looks_like_enchant(name):
                            entries.append({"name": name, "slot": None})
                else:
                    walk(child)

    walk(soup)
    result = {}
    for e in entries:
        if e["slot"] and e["slot"] not in result:
            result[e["slot"]] = e["name"]
    return result


def parse_bis_html(html):
    """Estrae {etichetta_slot: nome_item}. Prima il parser testuale, poi le icone."""
    soup = BeautifulSoup(html, "html.parser")
    result = parse_bis_text(soup)
    if len(result) < 10:                      # se il testuale ha preso poco, integro
        for label, name in parse_bis_images(soup).items():
            result.setdefault(label, name)
    return result


# --------------------------------------------------------------------------- #
#  Confronto + report
# --------------------------------------------------------------------------- #

# Gruppi di slot "intercambiabili": un oggetto BiS conta come posseduto se e'
# indossato in uno qualsiasi degli slot del gruppo (anelli, monili, armi).
SLOT_GROUPS = [("FINGER_1", "FINGER_2"), ("TRINKET_1",
                                          "TRINKET_2"), ("MAIN_HAND", "OFF_HAND")]


def build_rows(current, bis_by_slot):
    """Ritorna le righe (label, attuale, bis, match, ha_bis) nell'ordine slot.

    Per i gruppi intercambiabili: si confronta l'INSIEME degli oggetti BiS con
    quello indossato. Cosi' un anello BiS messo nello slot opposto risulta
    comunque posseduto, e come "mancanti" restano solo i BiS non posseduti.
    """
    def cur_name(slot):
        v = current.get(slot)
        return v["name"] if v else None

    resolved = {}
    for group in SLOT_GROUPS:
        bis = {s: bis_by_slot.get(s) for s in group}
        bis_slots = [s for s in group if bis.get(s)]
        bis_norms = [norm(bis[s]) for s in bis_slots]
        cur_norms = {norm(cur_name(s)) for s in group if cur_name(s)}
        owned = {nrm for nrm in bis_norms if nrm in cur_norms}
        missing = [bis[s] for s in bis_slots if norm(bis[s]) not in owned]
        mi = 0
        for s in group:
            c = cur_name(s)
            if not bis.get(s):
                # nessun BiS per questo slot (es. off-hand quando il BiS e' un'arma 2H)
                resolved[s] = (c, None, False, False)
            elif c and norm(c) in bis_norms:
                # indossi un oggetto BiS (anche se in un altro slot del gruppo): conta
                resolved[s] = (c, c, True, True)
            else:
                # slot da completare: mostro uno dei BiS ancora mancanti
                disp = missing[mi] if mi < len(missing) else bis[s]
                mi += 1
                resolved[s] = (c, disp, False, True)

    rows = []
    for slot, label in SLOT_DISPLAY:
        if slot in resolved:
            cur, b, match, has_bis = resolved[slot]
        else:
            cur = cur_name(slot)
            b = bis_by_slot.get(slot)
            has_bis = bool(b)
            match = bool(cur) and has_bis and norm(cur) == norm(b)

        cur_disp = cur or "(vuoto)"
        if cur and current.get(slot) and current[slot].get("ilvl"):
            cur_disp = f"{cur} (ilvl {current[slot]['ilvl']})"
        rows.append((label, cur_disp, b or "(nessun BiS)", match, has_bis))
    return rows


def slot_marks(rows):
    """Lista dei 17 marcatori in ordine di slot: 'X'=BiS, ' '=manca, '-'=nessun BiS."""
    marks = []
    for (slot, _label_it), row in zip(SLOT_DISPLAY, rows):
        match, has_bis = row[3], row[4]
        marks.append("-" if not has_bis else ("X" if match else " "))
    return marks


def abbr_header():
    """Riga di sigle (Te Co Sp ...) allineata ai quadretti, larga 3 char per slot."""
    return "".join(f"{SLOT_ABBR.get(slot, slot[:2]):^3}" for slot, _ in SLOT_DISPLAY)


def legend_lines(per_line=5):
    """Legenda sigla=nome, a gruppi."""
    pairs = [f"{SLOT_ABBR.get(slot, slot[:2])}={label_it}"
             for slot, label_it in SLOT_DISPLAY]
    return ["  ".join(pairs[k:k + per_line]) for k in range(0, len(pairs), per_line)]


def render_quick_view(rows):
    """
    Riga compatta in stile array:
      [X] = ce l'hai (e' BiS)   [ ] = ti manca   [-] = nessun BiS per lo slot
    Sopra i quadretti le sigle degli slot, sotto una piccola legenda.
    """
    matched = sum(1 for r in rows if r[3] and r[4])
    total = sum(1 for r in rows if r[4])
    boxes = "".join(f"[{m}]" for m in slot_marks(rows))

    out = [
        f"RIEPILOGO RAPIDO  (X = ce l'hai BiS,  vuoto = ti manca)    {matched}/{total}",
        abbr_header(),
        boxes,
        "",
        "Legenda:",
    ]
    out += ["  " + l for l in legend_lines()]
    return out


def render_overview(results):
    """
    Matrice riassuntiva: una riga per personaggio, etichettata col NOME DEL PLAYER.
    'results' e' la lista di dict prodotti da analyze_character (+ eventuali errori).
    """
    name_w = min(20, max([len("Player")] + [len(r["player"])
                 for r in results]))
    out = []
    out.append("RIEPILOGO COMPLESSIVO  (X = BiS,  vuoto = manca,  - = n/d)")
    out.append(f"{'':<{name_w}}  {abbr_header()}  tot")
    out.append(f"{'':<{name_w}}  {'-' * (3 * len(SLOT_DISPLAY))}")
    for r in results:
        label = r["player"][:name_w].ljust(name_w)
        if r.get("error"):
            out.append(f"{label}  >> ERRORE: {_short_err(r['error'])}")
            continue
        boxes = "".join(f"[{m}]" for m in r["marks"])
        out.append(f"{label}  {boxes}  {r['matched']}/{r['total']}")
    out.append("")
    out.append("Legenda:")
    out += ["  " + l for l in legend_lines()]
    return out


def render_report(meta, rows, quick=True):
    """Costruisce il testo del report di UN personaggio (a video e su file)."""
    matched = sum(1 for r in rows if r[3] and r[4])
    total = sum(1 for r in rows if r[4])

    w_slot = max(len("SLOT"), max(len(r[0]) for r in rows))
    w_cur = max(len("ATTUALE"), max(len(r[1]) for r in rows))
    w_bis = max(len("BIS"), max(len(r[2]) for r in rows))

    def line(a, b, c, d):
        return f"{a:<{w_slot}}  {b:<{w_cur}}  {c:<{w_bis}}  {d}"

    out = []
    out.append("=" * (w_slot + w_cur + w_bis + 12))
    out.append(
        f"Personaggio : {meta['name']}  ({meta['realm']} - {meta['region'].upper()})")
    if meta.get("player"):
        out.append(f"Player      : {meta['player']}")
    out.append(f"Spec / BiS  : {meta['spec']}")
    out.append(f"Fonte equip : API Blizzard  [{meta['namespace']}]")
    out.append(f"Fonte BiS   : {meta['bis_url']}")
    out.append("=" * (w_slot + w_cur + w_bis + 12))
    out.append("")
    if quick:
        out.extend(render_quick_view(rows))
        out.append("")
    out.append("DETTAGLIO:")
    out.append(line("SLOT", "ATTUALE", "BIS", "OK"))
    out.append("-" * (w_slot + w_cur + w_bis + 12))
    for label_it, cur_disp, bis_disp, match, has_bis in rows:
        mark = "OK" if match else ("--" if not has_bis else "NO")
        out.append(line(label_it, cur_disp, bis_disp, mark))
    out.append("-" * (w_slot + w_cur + w_bis + 12))
    out.append("")
    out.append(f"Pezzi gia' BiS: {matched}/{total}")

    upgrades = [(r[0], r[1], r[2]) for r in rows if r[4] and not r[3]]
    if upgrades:
        out.append("")
        out.append("DA MIGLIORARE:")
        for label_it, cur_disp, bis_disp in upgrades:
            out.append(f"  - {label_it}: {cur_disp}  ->  {bis_disp}")
    else:
        out.append("\nComplimenti: hai tutta la BiS list!")

    out.append("")
    out.append(
        "Nota: la BiS e' quella mostrata di default su wowtbc.gg per questa spec.")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
#  Orchestrazione (singolo / batch)
# --------------------------------------------------------------------------- #

def analyze_character(region, realm, name, spec, token, bis_cache):
    """Analizza UN personaggio. Ritorna dict con rows/marks/conteggi/fonti. Solleva su errore."""
    spec_slug = slugify_spec(spec)
    current, namespace = get_current_gear(region, realm, name, token)
    # BiS in cache (stessa spec)
    if spec_slug in bis_cache:
        bis_by_slot, bis_url = bis_cache[spec_slug]
    else:
        bis_by_slot, bis_url = fetch_bis(spec_slug)
        bis_cache[spec_slug] = (bis_by_slot, bis_url)
    rows = build_rows(current, bis_by_slot)
    return {
        "rows": rows,
        "marks": slot_marks(rows),
        "matched": sum(1 for r in rows if r[3] and r[4]),
        "total": sum(1 for r in rows if r[4]),
        "namespace": namespace,
        "bis_url": bis_url,
    }


def read_csv(path):
    """Legge righe: nome_pg, nome_player, class [, realm [, region]] (senza header)."""
    chars = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for raw in csv.reader(f):
            cells = [c.strip() for c in raw]
            if not any(cells):                       # riga vuota
                continue
            # salta un'eventuale riga di intestazione lasciata per sbaglio
            if (len(cells) >= 3 and cells[2].lower() in ("class", "classe", "spec")
                    and cells[0].lower() in ("nome_pg", "nome pg", "pg", "personaggio")):
                continue
            if len(cells) < 3:
                chars.append({"pg": cells[0] if cells else "?", "player": "?",
                              "spec": "", "realm": None, "region": None,
                              "bad": "riga con meno di 3 colonne"})
                continue
            chars.append({
                "pg": cells[0],
                "player": cells[1],
                "spec": cells[2],
                "realm": cells[3] if len(cells) >= 4 and cells[3] else None,
                "region": cells[4].lower() if len(cells) >= 5 and cells[4] else None,
            })
    return chars


def _short_err(msg):
    first = (msg or "").strip().splitlines()[
        0] if (msg or "").strip() else "errore"
    return (first[:80] + "...") if len(first) > 80 else first


def doc_header():
    return ["BiS Diff - WoW TBC Anniversary",
            f"Generato: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"]


def save_doc(doc, slug):
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", slug.lower())
    fname = os.path.join(HERE, f"bis_diff_{safe}_{stamp}.txt")
    try:
        with open(fname, "w", encoding="utf-8") as f:
            f.write(doc + "\n")
        print(f"\n>> Report salvato in: {fname}")
    except Exception as e:
        print(f"\n(Non sono riuscito a salvare il file: {e})")


def build_export(results, realm_def, region_def):
    """Struttura dati (per l'HTML) a partire dai risultati."""
    slots_meta = [{"code": SLOT_ABBR.get(s, s[:2]), "name": label}
                  for s, label in SLOT_DISPLAY]
    chars = []
    for r in results:
        c = {
            "pg": r["pg"], "player": r.get("player") or r["pg"],
            "spec": r.get("spec", ""), "realm": r.get("realm", realm_def),
            "region": (r.get("region") or region_def).upper(),
            "error": _short_err(r["error"]) if r.get("error") else None,
            "matched": r.get("matched", 0), "total": r.get("total", 0),
            "slots": [],
        }
        if not r.get("error") and r.get("rows"):
            for (slot, _label), row in zip(SLOT_DISPLAY, r["rows"]):
                label_it, cur_disp, bis_disp, match, has_bis = row
                c["slots"].append({
                    "code": SLOT_ABBR.get(slot, slot[:2]), "name": label_it,
                    "have": bool(match), "nd": (not has_bis),
                    "current": cur_disp, "bis": bis_disp,
                })
        chars.append(c)
    return {
        "title": "PIS List \u2014 TBC Anniversary",
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "realm": realm_def, "region": region_def.upper(),
        "slots": slots_meta, "characters": chars,
    }


def save_data_js(export):
    """Scrive i dati per il visualizzatore in un file a NOME FISSO: bis_data.js.
    Definisce window.BIS_DATA, cosi' roster.html lo carica con <script> e
    funziona anche aprendo l'HTML in locale (senza server)."""
    fname = os.path.join(HERE, "bis_data.js")
    try:
        with open(fname, "w", encoding="utf-8") as f:
            f.write("window.BIS_DATA = " +
                    json.dumps(export, ensure_ascii=False) + ";\n")
        print(f">> Dati per il visualizzatore aggiornati: {fname}")
    except Exception as e:
        print(f"(Non sono riuscito a salvare {fname}: {e})")


def run_single(token, bis_cache):
    name = input("Nome personaggio: ").strip()
    realm = input("Reame [Spineshatter]: ").strip() or "Spineshatter"
    region = (input("Regione (eu/us) [eu]: ").strip() or "eu").lower()
    spec = input("Classe e spec (es. Shadow Priest): ").strip()
    if not name or not spec:
        print("Servono almeno nome e spec. Esco.")
        return
    try:
        print("\nScarico equip + BiS...")
        res = analyze_character(region, realm, name, spec, token, bis_cache)
    except Exception as e:
        print("\nERRORE: " + str(e))
        return
    meta = {"name": name, "player": "", "realm": realm, "region": region,
            "spec": spec, "namespace": res["namespace"], "bis_url": res["bis_url"]}
    body = render_report(meta, res["rows"], quick=True)
    doc = "\n".join(doc_header() + ["", body])
    print("\n" + body)
    save_doc(doc, f"{name}_{region}")
    entry = {"pg": name, "player": "", "spec": spec, "realm": realm,
             "region": region, **res}
    save_data_js(build_export([entry], realm, region))


def run_batch(token, bis_cache):
    path = input("Percorso del file CSV (nome_pg, nome_player, class): ").strip(
    ).strip('"').strip("'")
    if not path:
        print("Nessun file indicato. Esco.")
        return
    if not os.path.exists(path):
        print(f"File non trovato: {path}")
        return
    realm_def = input(
        "Reame per tutti [Spineshatter]: ").strip() or "Spineshatter"
    region_def = (
        input("Regione per tutti (eu/us) [eu]: ").strip() or "eu").lower()

    try:
        chars = read_csv(path)
    except Exception as e:
        print(f"Errore nella lettura del CSV: {e}")
        return
    if not chars:
        print("Il CSV non contiene righe valide.")
        return

    results = []
    print()
    for i, c in enumerate(chars, 1):
        pg, player, spec = c["pg"], c["player"], c["spec"]
        realm = c["realm"] or realm_def
        region = c["region"] or region_def
        entry = {"pg": pg, "player": player or pg, "spec": spec,
                 "realm": realm, "region": region}
        print(f"[{i}/{len(chars)}] {pg} ({entry['player']}) - {spec or '?'} ... ",
              end="", flush=True)
        if c.get("bad"):
            entry["error"] = c["bad"]
            results.append(entry)
            print("SALTATO (" + c["bad"] + ")")
            continue
        try:
            entry.update(analyze_character(
                region, realm, pg, spec, token, bis_cache))
            print(f"OK  {entry['matched']}/{entry['total']}")
        except Exception as e:
            entry["error"] = str(e)
            print("ERRORE")
        results.append(entry)

    # Documento: intestazione + riepilogo complessivo + dettaglio per personaggio.
    lines = list(doc_header())
    lines.append(
        f"Personaggi: {len(results)}    Reame default: {realm_def} ({region_def.upper()})")
    lines.append("")
    lines += render_overview(results)
    lines.append("")
    lines.append("#" * 70)
    lines.append("DETTAGLIO PER PERSONAGGIO")
    lines.append("#" * 70)
    for r in results:
        lines.append("")
        if r.get("error"):
            lines.append(
                f"--- {r['pg']}  (player: {r['player']})  :  ERRORE ---")
            lines.append("    " + str(r["error"]).replace("\n", "\n    "))
            continue
        meta = {"name": r["pg"], "player": r["player"], "realm": r["realm"],
                "region": r["region"], "spec": r["spec"],
                "namespace": r["namespace"], "bis_url": r["bis_url"]}
        lines.append(render_report(meta, r["rows"], quick=False))
    doc = "\n".join(lines)

    # a video almeno il riepilogo
    print("\n" + "\n".join(render_overview(results)))
    save_doc(doc, f"batch_{region_def}")
    save_data_js(build_export(results, realm_def, region_def))


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

def main():
    # Per evitare problemi con accenti/simboli nel terminale di Windows.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=== BiS Diff - WoW TBC Anniversary ===\n")
    mode = input(
        "Quanti personaggi? [1 = uno solo / 2 = piu' da CSV]: ").strip()

    # Login una sola volta: vale per tutti i personaggi.
    try:
        cid, secret = load_credentials()
        print("\nLogin API Blizzard...")
        token = get_token(cid, secret)
    except Exception as e:
        print("\nERRORE: " + str(e))
        return

    bis_cache = {}
    if mode == "2":
        run_batch(token, bis_cache)
    else:
        run_single(token, bis_cache)


if __name__ == "__main__":
    main()
