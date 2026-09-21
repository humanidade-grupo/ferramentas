"""Espelha no Cofre do Parque o STATUS DE ASSINATURA dos contratos da D4Sign (uso local).

SÓ LEITURA na D4Sign: nada é baixado, nada é clicado além de abrir o modal de
signatários. Nunca clica em "Download (original e assinaturas)", "ASSINAR",
"editar" nem "Cadastrar TAGs".

Uso:
  python status.py --dry-run            # varre e imprime o que seria enviado; não envia
  python status.py                      # varre e envia à rota ?app=d4sign&fn=gravar
  python status.py --limite 5 --dry-run # só os 5 documentos mais novos (teste)
  python status.py --so-pendentes       # abre o modal só dos não finalizados (ver abaixo)

Por que o modal abre em TODOS os documentos, e não só nos pendentes: a chave de
casamento com a venda é o E-MAIL do signatário, e ele só existe no modal. Sem ele,
os 62 documentos "JAZIGO PERPÉTUO pdf" ficariam sem Deal ID. Custa ~1 requisição por
documento (~123 em 19/09). `--so-pendentes` faz o recorte barato quando só a fase
interessa.

Dados em %USERPROFILE%\\Documents\\d4sign-lote (ou D4SIGN_DADOS), os mesmos do baixar.py:
  cofre.txt   endereço do cofre (o repo é público; o endereço fica fora dele)
  token.txt   token de gestão do Cofre (NUNCA no repo)
  perfil\\     sessão do Edge
Em disco esta ferramenta só escreve status_log.csv — contagens, nenhum nome, nenhum e-mail.

A ordem é a de 24/08: ler -> validar -> montar -> enviar. Varredura com zero
documentos, página que caiu no login ou documento com fase desconhecida ABORTA
antes de enviar qualquer coisa.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = Path(os.environ.get("D4SIGN_DADOS", Path.home() / "Documents" / "d4sign-lote"))
PERFIL = BASE / "perfil"
LOG = BASE / "status_log.csv"
_COFRE_TXT = BASE / "cofre.txt"
_TOKEN_TXT = BASE / "token.txt"
SINAL_OK = BASE / "ok"
# O /exec do Cofre já é público (está no código do Painel); o que é segredo é o token.
API = os.environ.get("D4SIGN_API", "https://script.google.com/macros/s/"
                     "AKfycbydLmUEX3g6FeojFGAcVHfNKoPsr4d9oTBUdi7GtcfsirQL6xHJM0BELVGcCrcqrICY/exec")
LOTE = 25
MAX_PAGINAS = 60
FASES = ["EDITANDO", "AGUARDANDO SIGNATÁRIOS", "AGUARDANDO ASSINATURAS", "FINALIZADO", "CANCELADO"]
INTERNOS = ("parquedasaudadejf.com.br", "estrelaurbanidade.com.br")

MESES = {"jan": 1, "feb": 2, "fev": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "mai": 5,
         "jun": 6, "jul": 7, "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "out": 10,
         "nov": 11, "dec": 12, "dez": 12}
RX_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
RX_PCT = re.compile(r"(\d+)\s*%\s*\(\s*(\d+)\s+de\s+(\d+)\s*\)", re.I)


class Aborta(Exception):
    """Qualquer coisa que torna a passada não confiável. Nada é enviado."""


# ------------------------------------------------------------------ datas

def ler_data(txt):
    """'16 Sep 2026, 15:42:54' ou '16/09/2026 15:42(:54)' -> datetime | None"""
    m = re.search(r"(\d{1,2})\s+([A-Za-zç]{3})\w*\s+(\d{4}),?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?", txt)
    if m and m.group(2).lower() in MESES:
        d, mes, a, h, mi, s = m.groups()
        return datetime(int(a), MESES[mes.lower()], int(d), int(h), int(mi), int(s or 0))
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?", txt)
    if m:
        d, mes, a, h, mi, s = m.groups()
        return datetime(int(a), int(mes), int(d), int(h), int(mi), int(s or 0))
    return None


def fase_base(txt):
    s = re.sub(r"\s+", " ", (txt or "").upper()).strip().replace("SIGNATARIOS", "SIGNATÁRIOS")
    return next((f for f in FASES if s.startswith(f)), "")


def levou(fase_txt, cadastro):
    """'FINALIZADO LEVOU 8 HORAS PARA SER FINALIZADO' -> cadastro + 8 h.
    Aproximação da tela (a D4Sign arredonda para a maior unidade), mas o modal de um
    documento finalizado não mostra a hora de cada assinatura — é o que há."""
    up = (fase_txt or "").upper()
    m = re.search(r"LEVOU\s+(\d+)\s+(DIA|HORA|MINUTO|SEGUNDO|M[EÊ]S|SEMANA)", up)
    if not m:
        # "LEVOU MENOS DE 1 ..." e parecidos: terminou no dia do cadastro
        return cadastro.strftime("%Y-%m-%d %H:%M") if "LEVOU" in up else None
    n, u = int(m.group(1)), m.group(2)
    delta = {"DIA": timedelta(days=n), "HORA": timedelta(hours=n), "MINUTO": timedelta(minutes=n),
             "SEGUNDO": timedelta(seconds=n), "SEMANA": timedelta(weeks=n)}.get(u, timedelta(days=30 * n))
    return (cadastro + delta).strftime("%Y-%m-%d %H:%M")


# ------------------------------------------------------------------ navegador

def ir(page, url, tentativas=1):
    """True quando a tabela apareceu. `tentativas` > 1 recarrega antes de desistir: em 21/09/2026
    a passada das 20h abortou com 'ZERO documentos' porque a PRIMEIRA página passou de 30 s —
    dez minutos depois a mesma leitura rodou inteira. Lentidão passageira não pode derrubar a
    passada. Nas páginas seguintes fica em 1 tentativa de propósito: ali o tempo esgotado é o
    fim da paginação, e repetir custaria 30 s em cada passada."""
    for t in range(max(1, tentativas)):
        page.goto(url, wait_until="domcontentloaded")
        if "login" in page.url:
            raise Aborta("a página caiu no login no meio da varredura")
        try:
            page.wait_for_selector("tbody tr", timeout=30_000)
            return True
        except PWTimeout:
            if "login" in page.url:
                raise Aborta("a página caiu no login no meio da varredura")
            if t + 1 < max(1, tentativas):
                print("  a tabela não veio em 30 s — recarregando uma vez...", flush=True)
                time.sleep(3)
    return False


def abrir(p, escondido):
    """Um contexto por vez no MESMO perfil do Edge (a sessão vive nele)."""
    ctx = p.chromium.launch_persistent_context(
        str(PERFIL), channel="msedge", headless=escondido, viewport={"width": 1366, "height": 850})
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(60_000)
    return ctx, page


def esperar_login(page):
    if sys.stdin.isatty():
        input("\n>>> Faça login na janela do navegador e aperte Enter aqui... ")
        return
    print(f">>> Faça login na janela. Sigo quando entrar no cofre (ou existir {SINAL_OK}).", flush=True)
    fim = time.time() + 15 * 60
    while time.time() < fim and "/desk/" not in page.url and not SINAL_OK.exists():
        time.sleep(3)
    # Pela tarefa agendada NÃO há quem digite a senha: sem isto, a espera acabava, o resto
    # quebrava com um erro que não é Aborta e NADA era registrado (21/09/2026).
    if "/desk/" not in page.url and not SINAL_OK.exists():
        raise Aborta("a sessão da D4Sign caiu e ninguém logou na janela em 15 min")


def linhas_da_pagina(page):
    """Só leitura: uuid, nome, cadastro, porcentagem e fase de cada linha da tabela."""
    return page.evaluate(r"""() => [...document.querySelectorAll('tbody tr')].map(tr => {
        const td = [...tr.querySelectorAll('td')].map(c => (c.innerText || '').trim());
        const tudo = td.join('\n');
        const uuid = (tudo.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/) || [''])[0];
        if (!uuid) return null;
        const doc = td.find(t => t.includes(uuid)) || '';
        return {uuid, nome: doc.split('\n').map(s => s.trim()).filter(Boolean)[0] || '',
                cadastro_txt: (td[1] || '').replace(/\s+/g, ' '), celulas: td};
    }).filter(Boolean)""")


def varrer(page, cofre, limite):
    docs, vistos = [], set()
    # k=0 é o endereço .html (página 1); depois ?p=0, ?p=1... Não se sabe se ?p=0 repete a
    # página 1 ou já é a 2, então a primeira página sem novidade é tolerada e a segunda encerra.
    for k in range(MAX_PAGINAS):
        p = k - 1
        url = cofre if k == 0 else f"{cofre}?p={p}&f=&fase="
        if not ir(page, url, tentativas=2 if k == 0 else 1):
            break
        linhas = linhas_da_pagina(page)
        novos = 0
        for l in linhas:
            if l["uuid"] in vistos:
                continue
            vistos.add(l["uuid"])
            novos += 1
            cad = ler_data(l["cadastro_txt"])
            if not cad:
                raise Aborta(f"cadastro em formato inesperado ({url.split('?')[-1]}): {l['cadastro_txt']!r}")
            # a célula inteira: "FINALIZADO\n\nLEVOU 8 HORAS PARA SER FINALIZADO" — o tempo vem na 2ª linha
            fase_txt = next((re.sub(r"\s+", " ", c) for c in l["celulas"] if fase_base(c)), "")
            if not fase_txt:
                raise Aborta(f"documento {l['uuid']} sem fase reconhecível — a D4Sign mudou a tela?")
            m = next((RX_PCT.search(c) for c in l["celulas"] if RX_PCT.search(c)), None)
            if m:
                assinadas, total = int(m.group(2)), int(m.group(3))
            elif fase_base(fase_txt) in ("EDITANDO", "AGUARDANDO SIGNATÁRIOS"):
                assinadas, total = 0, 0
            else:
                raise Aborta(f"documento {l['uuid']} ({fase_txt}) sem a Porcentagem 'N% (x de y)'")
            docs.append({"uuid": l["uuid"], "nome": l["nome"], "cadastro": cad,
                         "fase_txt": fase_txt, "fase": fase_base(fase_txt),
                         "assinadas": assinadas, "total": total})
        print(f"  {'página 1 (.html)' if k == 0 else f'p={p}'}: {len(linhas)} linhas, {novos} novas", flush=True)
        if not novos and k >= 2:
            break
        if limite and len(docs) >= limite:
            break
    return docs[:limite] if limite else docs


# Sondado em 19/09: o .modal-body tem uma <table> com UMA <tr> por signatário. Quem assinou
# tem o ícone `fa-check-circle-o color-verde` (pendente: `color-cinza`); o texto ASSINOU só
# aparece depois de assinado. Sem a tabela, cai no "maior bloco com exatamente um e-mail".
LER_MODAL = r"""() => {
  const rx = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
  const body = [...document.querySelectorAll('.modal-body')].find(b => /@/.test(b.innerText || ''));
  if (!body) return null;
  const n = el => ((el.innerText || '').match(rx) || []).length;
  const verde = el => [...el.querySelectorAll('i.fa-check-circle-o, i.fa-check-circle')]
                        .some(i => /color-verde/.test(i.className));
  let blocos = [...body.querySelectorAll('table tr')].filter(tr => n(tr) === 1);
  if (!blocos.length)
    blocos = [...body.querySelectorAll('*')]
      .filter(el => n(el) === 1 && (el.parentElement === body || n(el.parentElement) !== 1));
  return blocos.map(el => ({txt: el.innerText, verde: verde(el)}));
}"""

FECHAR_MODAL = r"""() => {
  try { if (window.jQuery) jQuery('.modal').modal('hide'); } catch (e) {}
  document.querySelectorAll('.modal-body').forEach(b => { b.innerHTML = ''; });
  document.querySelectorAll('.modal-backdrop').forEach(b => b.remove());
  document.body.classList.remove('modal-open');
}"""


def ler_signatarios(page, uuid):
    """Abre o modal de signatários (o mesmo javascript da tela) e lê o .modal-body."""
    for tentativa in range(3):
        page.evaluate(FECHAR_MODAL)
        # O fechamento do anterior é animado (bootstrap "fade"): abrir o próximo antes de ele
        # terminar deixa o modal novo escondido, e o e-mail nunca fica visível (medido em 19/09).
        time.sleep(1.2)
        page.evaluate(f"eModalO('/desk/listsignatarios/{uuid}','S','fa-users','lg')")
        # Espera em Python, não com wait_for_function: nesta página ele estoura o prazo
        # mesmo com o modal pronto em ~1 s (medido em 19/09 — provavelmente a CSP da D4Sign).
        pronto = False
        for _ in range(40):
            time.sleep(0.5)
            if page.evaluate(r"""() => [...document.querySelectorAll('.modal-body')].some(b => /@/.test(b.innerText || ''))"""):
                pronto = True
                break
        if not pronto:
            if "login" in page.url:
                raise Aborta("a sessão caiu no meio da leitura dos signatários")
            continue
        time.sleep(0.5)   # a tabela termina de montar logo depois do primeiro e-mail
        cartoes = page.evaluate(LER_MODAL) or []
        page.evaluate(FECHAR_MODAL)
        sigs = [cartao(c) for c in cartoes]
        sigs = [s for s in sigs if s]
        if sigs:
            return sigs
    raise Aborta(f"não consegui ler os signatários de {uuid} depois de 3 tentativas")


def cartao(bloco):
    txt, verde = bloco["txt"], bloco["verde"]
    email = (RX_EMAIL.search(txt) or [None])[0]
    if not email:
        return None
    up = txt.upper()
    if "COMO TESTEMUNHA" in up:
        papel = "ASSINAR COMO TESTEMUNHA"
    elif "COMO PARTE" in up:
        papel = "ASSINAR COMO PARTE"
    else:
        papel = "ASSINAR"
    assinou = verde or (bool(re.search(r"\bASSINOU\b", up)) and not re.search(r"N[ÃA]O\s+ASSINOU", up))
    datas = [d for d in (ler_data(l) for l in txt.split("\n")) if d]
    nome = ""
    for l in (x.strip() for x in txt.split("\n")):
        if (len(l) > 2 and "@" not in l
                and not re.search(r"ASSIN|TESTEMUNHA|PARTE|POSSUI CONTA|AUTENTICA|OPCIONAL|EDITAR|\d{2}/\d{2}/\d{4}",
                                  l.upper())
                and not ler_data(l)):
            nome = l
            break
    return {"email": email.lower(), "nome": nome, "papel": papel, "assinou": assinou, "datas": datas}


def interno(email):
    return email.split("@")[-1] in INTERNOS


# O nome do documento traz o nome do cliente ("CONTRATO FULANO JAZIGO M-19-450 pdf"), e
# quando o cliente "Não possui conta" o modal nem mostra o nome dele para tirar. Então o
# nome sai por LISTA FECHADA: só palavras de tipo de documento, o jazigo e números.
PALAVRAS_DOC = {"CONTRATO", "JAZIGO", "PERPETUO", "PERPÉTUO", "TEMPORARIO", "TEMPORÁRIO", "RESERVA",
                "RETOMADA", "PDF", "DE", "DO", "DA", "E", "TERMO", "ADITIVO", "CESSAO", "CESSÃO",
                "TRANSFERENCIA", "TRANSFERÊNCIA", "QUADRA", "UNIDADE", "PET", "HUMANO", "GAVETA",
                "DISTRATO", "RENEGOCIACAO", "RENEGOCIAÇÃO", "COMPRA", "VENDA", "PROMESSA"}
RX_JAZ_DOC = r"M\s*-?\s*\d{1,2}\s*-\s*\d{1,4}[A-Z]?|R-\d{1,4}"


def nome_seguro(doc):
    out = []
    for tok in re.findall(RX_JAZ_DOC + r"|\S+", doc or "", flags=re.I):
        limpo = tok.strip(".,;:()[]").upper()
        if limpo in PALAVRAS_DOC or re.fullmatch(r"[\d/.-]+|" + RX_JAZ_DOC, limpo):
            out.append(tok)
        elif not out or out[-1] != "…":
            out.append("…")
    return " ".join(out).strip()


def tirar_nomes(doc, nomes):
    for nome in nomes:
        for p in nome.split():
            if len(p) >= 2:
                doc = re.sub(rf"(?<![^\W\d_]){re.escape(p)}(?![^\W\d_])", "", doc, flags=re.I)
    return re.sub(r"\s*-\s*(-\s*)+", " - ", re.sub(r"\s{2,}", " ", doc)).strip(" -")


# ------------------------------------------------------------------ montar e enviar

def montar(d, sigs):
    fin = ""
    if d["fase"] == "FINALIZADO":
        datas = [x for s in (sigs or []) for x in s["datas"] if x >= d["cadastro"]]
        if sigs and datas and all(s["assinou"] for s in sigs):
            fin = max(datas).strftime("%Y-%m-%d %H:%M")
        else:
            fin = levou(d["fase_txt"], d["cadastro"]) or ""
        if not fin:
            raise Aborta(f"{d['uuid']} FINALIZADO sem data de fim (nem no modal nem em '{d['fase_txt']}')")
    externos = [s["nome"] for s in (sigs or []) if not interno(s["email"]) and s["nome"]]
    return {
        "uuid": d["uuid"],
        "documento": nome_seguro(tirar_nomes(d["nome"], externos)),
        "cadastro": d["cadastro"].strftime("%Y-%m-%d %H:%M"),
        "finalizado_em": fin,
        "fase": d["fase"],
        "assinadas": d["assinadas"],
        "total": d["total"],
        # o e-mail trafega (é a chave do casamento) e o Cofre NÃO o grava;
        # nome só de signatário interno — o do cliente nem sai daqui
        "signatarios": [{"email": s["email"], "nome": s["nome"] if interno(s["email"]) else "",
                         "papel": s["papel"], "assinou": s["assinou"]} for s in (sigs or [])],
    }


def enviar(token, payload):
    corpo = json.dumps({**payload, "token": token}).encode("utf-8")
    req = urllib.request.Request(f"{API}?app=d4sign&fn=gravar", data=corpo, method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    with urllib.request.urlopen(req, timeout=300) as r:   # o 302 do Apps Script vira GET sozinho
        txt = r.read().decode("utf-8", "replace")
    try:
        return json.loads(txt)
    except ValueError:
        return {"ok": False, "error": "resposta não é JSON (a página 'Não foi possível abrir o arquivo'?) — "
                                      "rode de novo: o reenvio é idempotente"}


def avisar_falha(token, motivo):
    """Manda o MOTIVO para o Cofre, para a tarja da PonteApp dizer por que o espelho envelheceu.
    Nunca derruba a execução: se o aviso falhar, o log local continua sendo a fonte."""
    if not token:
        return
    try:
        req = urllib.request.Request(
            f"{API}?app=d4sign&fn=falha",
            data=json.dumps({"token": token, "motivo": motivo}).encode("utf-8"),
            headers={"Content-Type": "text/plain;charset=utf-8"})
        with urllib.request.urlopen(req, timeout=30) as r:
            json.loads(r.read().decode("utf-8"))
        print(">>> motivo avisado ao Cofre (a tela vai dizer por que o espelho está velho).", flush=True)
    except Exception as e:
        print(f">>> não consegui avisar o Cofre do motivo ({type(e).__name__}) — fica só no log.", flush=True)


def registrar(modo, docs, enviados, resultado):
    novo = not LOG.exists()
    por = {f: sum(1 for d in docs if d["fase"] == f) for f in FASES}
    with LOG.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["executado_em", "modo", "documentos"] + FASES + ["enviados", "resultado"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), modo, len(docs)]
                   + [por[x] for x in FASES] + [enviados, resultado[:200]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="imprime o payload e não envia")
    ap.add_argument("--limite", type=int, default=0, help="só os N documentos mais novos")
    ap.add_argument("--so-pendentes", action="store_true",
                    help="abre o modal só dos não finalizados (os finalizados vão sem e-mail e casam só pelo jazigo no nome)")
    args = ap.parse_args()

    if not _COFRE_TXT.exists():
        sys.exit(f"Falta {_COFRE_TXT} com o endereço do cofre.")
    cofre = _COFRE_TXT.read_text(encoding="utf-8").strip()
    token = ""
    if not args.dry_run:
        if not _TOKEN_TXT.exists():
            sys.exit(f"Falta {_TOKEN_TXT} com o token de gestão do Cofre (ou rode com --dry-run).")
        token = _TOKEN_TXT.read_text(encoding="utf-8").strip()
    if args.limite and not args.dry_run:
        print("⚠️  --limite sem --dry-run REESCREVE o espelho só com esses documentos "
              "(o Cofre recusa se for menos da metade da passada anterior).", flush=True)

    modo = "dry-run" if args.dry_run else "envio"
    docs = []
    try:
        with sync_playwright() as p:
            # A JANELA SÓ APARECE QUANDO PRECISA DE VOCÊ (21/09/2026).
            # Primeiro tenta ESCONDIDO: com a sessão viva, a passada roda sem janela nenhuma e
            # não interrompe o dia de ninguém. Se a sessão caiu, ou se a leitura escondida não
            # trouxe documento, abre a janela e tenta de novo — aí a janela é o sinal de que
            # alguém precisa logar. O perfil do Edge é o mesmo, e só um contexto por vez.
            ctx, page = abrir(p, escondido=True)
            docs, motivo_janela = [], ""
            try:
                page.goto(cofre, wait_until="domcontentloaded")
                if "login" in page.url:
                    motivo_janela = "a sessão da D4Sign caiu"
                else:
                    print("Lendo a listagem do cofre (sem janela)...", flush=True)
                    docs = varrer(page, cofre, args.limite)
                    if not docs:
                        motivo_janela = "a leitura sem janela não achou documento"
            except Aborta as e:
                motivo_janela = str(e)
            except Exception as e:
                motivo_janela = f"{type(e).__name__} na leitura sem janela"

            if motivo_janela:
                print(f">>> {motivo_janela}: abrindo a janela do Edge para tentar de novo.", flush=True)
                ctx.close()
                ctx, page = abrir(p, escondido=False)
                page.goto(cofre, wait_until="domcontentloaded")
                if "login" in page.url:
                    esperar_login(page)
                print("Lendo a listagem do cofre...", flush=True)
                docs = varrer(page, cofre, args.limite)
            if not docs:
                raise Aborta(f"a varredura achou ZERO documentos ({motivo_janela or 'sem janela'}, "
                             "e também com a janela aberta)")

            print(f"\n{len(docs)} documento(s). Lendo signatários...", flush=True)
            montados = []
            for i, d in enumerate(docs, 1):
                # sem signatário cadastrado (Editando / Aguardando Signatários) o modal não tem e-mail
                precisa = d["total"] > 0 and (not args.so_pendentes or d["fase"] != "FINALIZADO")
                sigs = ler_signatarios(page, d["uuid"]) if precisa else None
                if precisa and d["total"] and len(sigs) < d["total"]:
                    raise Aborta(f"{d['uuid']}: o modal trouxe {len(sigs)} signatário(s) e a tabela diz {d['total']}")
                montados.append(montar(d, sigs))
                if i % 10 == 0:
                    print(f"  {i}/{len(docs)}", flush=True)
            ctx.close()
    except Aborta as e:
        registrar(modo, docs, 0, f"ABORTADO: {e}")
        if not args.dry_run:
            avisar_falha(token, str(e))
        sys.exit(f"\nABORTADO, nada enviado: {e}")

    # validar (o Cofre valida de novo; aqui é para falhar antes de gastar a rede)
    por = {f: sum(1 for d in montados if d["fase"] == f) for f in FASES}
    print("\nPor fase: " + " · ".join(f"{f} {n}" for f, n in por.items() if n), flush=True)

    passada = datetime.now().strftime("%Y%m%d%H%M%S")
    lotes = [montados[i:i + LOTE] for i in range(0, len(montados), LOTE)]
    if args.dry_run:
        for n, l in enumerate(lotes, 1):
            print(json.dumps({"passada": passada, "lote": n, "de": len(lotes), "documentos": l},
                             ensure_ascii=False, indent=1))
        registrar(modo, montados, 0, "dry-run: nada enviado")
        print(f"\n--dry-run: {len(montados)} documentos em {len(lotes)} lote(s), NADA enviado.")
        return

    r = {}
    for n, l in enumerate(lotes, 1):
        r = enviar(token, {"passada": passada, "lote": n, "de": len(lotes), "documentos": l})
        if not r.get("ok"):
            registrar(modo, montados, n - 1, f"lote {n}/{len(lotes)} recusado: {r.get('error')}")
            sys.exit(f"\nLote {n}/{len(lotes)} recusado: {r.get('error')}\nO espelho no Cofre ficou como estava.")
        print(f"  lote {n}/{len(lotes)} ok", flush=True)
    registrar(modo, montados, len(montados),
              f"ok: {r.get('gravadas')} gravadas, casou {json.dumps(r.get('casou'))}")
    print(f"\nGravado no Cofre: {r.get('gravadas')} documentos · casamento {r.get('casou')} · {r.get('carimbo')}")


if __name__ == "__main__":
    # Falha que NÃO é Aborta também vira linha no log. Em 21/09/2026 a tarefa agendada saiu com
    # erro e o status_log.csv não ganhou linha nenhuma: quem olhasse o log concluiria que ela
    # nem tinha rodado. Log que só registra a falha prevista mente por omissão.
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        motivo = f"{type(e).__name__}: {str(e).splitlines()[0][:140]}"
        try:
            registrar("erro", [], 0, f"FALHOU: {motivo}")
        except Exception:
            pass
        try:   # o Cofre tambem precisa saber: e o que a tarja da PonteApp mostra
            if _TOKEN_TXT.exists():
                avisar_falha(_TOKEN_TXT.read_text(encoding="utf-8").strip(), f"a passada quebrou ({motivo})")
        except Exception:
            pass
        raise
