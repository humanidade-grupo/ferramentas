"""Renomeia os .zip com jazigo e cliente lidos da página 1 do contrato original.

  python renomear.py 2026-08            # só prévia -> renomear_previa.csv
  python renomear.py 2026-08 --aplicar  # renomeia conforme a prévia

Nada sai desta máquina; só jazigo e nome são extraídos (CPF, endereço etc. são ignorados).
"""
import csv
import os
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import pymupdf

BASE = Path(os.environ.get("D4SIGN_DADOS", Path.home() / "Documents" / "d4sign-lote"))
PREVIA = BASE / "renomear_previa.csv"


def texto_pag1(zpath):
    z = zipfile.ZipFile(zpath)
    pdfs = [n for n in z.namelist() if n.startswith("originais/") and n.lower().endswith(".pdf")]
    if not pdfs:
        pdfs = [n for n in z.namelist() if n.lower().endswith(".pdf")]
    doc = pymupdf.open(stream=z.read(sorted(pdfs)[0]), filetype="pdf")
    return " ".join(doc[i].get_text() for i in range(min(2, len(doc))))


def extrair(t):
    t = re.sub(r"\s+", " ", t)
    jazigo = None
    m = re.search(r"Jazigo\s*n[º°o.]*\s*([A-Z]{1,3})\s*-\s*(\d{1,3})\s*-+\s*(\d{1,4})", t, re.I)
    if m:
        jazigo = f"{m.group(1).upper()}-{m.group(2)}-{m.group(3)}"
    else:
        m = re.search(r"jazigo\s*n[º°o.]*\s*(\d{1,4}),?\s*do\s*jardim-quadra\s*([A-Z]{1,3})\s*-\s*(\d{1,3})", t, re.I)
        if m:
            jazigo = f"{m.group(2).upper()}-{m.group(3)}-{m.group(1)}"
    if not jazigo and re.search(r"Jazigo\s*n[º°o.]*\s*Reserva", t, re.I):
        jazigo = "RESERVA"  # reserva não tem jazigo físico
    cliente = None
    m = re.search(r"(?:CESSION[ÁA]RI[AO]\(?[AO]?\)?(?:\s*\(RESERVANTE\))?|CONTRATANTE|RESERVANTE|COMPRADOR\(?A?\)?)\s*:\s*([^,]{3,80}),", t)
    if m:
        cliente = m.group(1).strip()
    return jazigo, cliente


def seguro(s):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")


def main():
    mes = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else "2026-08"
    pasta = BASE / "downloads" / mes
    if "--aplicar" in sys.argv:
        feitos = 0
        with PREVIA.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f, delimiter=";"):
                if not r["novo"]:
                    continue
                de, para = pasta / r["atual"], pasta / r["novo"]
                if de.exists() and not para.exists():
                    de.rename(para)
                    feitos += 1
        print(f"{feitos} arquivo(s) renomeado(s).")
        return

    linhas = []
    for z in sorted(pasta.glob("*.zip")):
        m = re.match(r"(\d{4}-\d{2}-\d{2})_\d{4} (.*) \(([0-9a-f]{8})\)\.zip$", z.name)
        if not m:  # já renomeado ou fora do padrão
            linhas.append({"atual": z.name, "jazigo": "", "cliente": "", "novo": "", "obs": "fora do padrão"})
            continue
        data, tipo, uid = m.groups()
        try:
            jazigo, cliente = extrair(texto_pag1(z))
        except Exception as e:
            jazigo, cliente = None, None
        obs = ", ".join(x for x, ok in (("SEM JAZIGO", jazigo), ("SEM CLIENTE", cliente)) if not ok)
        novo = ""
        if jazigo and cliente:
            novo = seguro(f"{jazigo} - {cliente} - {data} {tipo} ({uid})") + ".zip"
        linhas.append({"atual": z.name, "jazigo": jazigo or "", "cliente": cliente or "", "novo": novo, "obs": obs})

    with PREVIA.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["atual", "jazigo", "cliente", "novo", "obs"], delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    for l in linhas:
        print(f"{l['jazigo'] or '???':12} {l['cliente'] or '???':40} {l['obs']}")
    print(f"\n{sum(1 for l in linhas if l['novo'])} de {len(linhas)} prontos. Prévia em {PREVIA.name}")


if __name__ == "__main__":
    main()
