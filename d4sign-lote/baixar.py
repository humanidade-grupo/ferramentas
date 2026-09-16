"""Baixa em lote os contratos de um cofre da D4Sign (uso local).

Uso:
  python baixar.py --limite 1           # teste com 1 contrato
  python baixar.py                      # lote de agosto/2026
  python baixar.py --mes 2026-07        # outro mês
  python baixar.py --listar             # só lista os contratos do mês, sem baixar

Nunca digita senha: se a sessão não estiver salva em .\\perfil, abre o site
e espera você logar (Enter no terminal).

Dados em %USERPROFILE%\\Documents\\d4sign-lote (ou D4SIGN_DADOS); ali precisa existir cofre.txt.

Só clica em paginação ("Próxima") e no link "Download (original e assinaturas)".
"""
import argparse
import csv
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# O código mora no repo; dados, sessão e contratos (com CPF) moram fora dele.
BASE = Path(os.environ.get("D4SIGN_DADOS", Path.home() / "Documents" / "d4sign-lote"))
PERFIL = BASE / "perfil"
LOG = BASE / "log.csv"
# Endereço do cofre fica em cofre.txt, fora do repo (o repo é público).
_COFRE_TXT = BASE / "cofre.txt"
TEXTO_LINK = "Download (original e assinaturas)"
TIMEOUT_DOWNLOAD = 10 * 60 * 1000
SINAL_OK = BASE / "ok"  # alternativa ao Enter quando não há terminal interativo

MESES = {"jan": 1, "feb": 2, "fev": 2, "mar": 3, "apr": 4, "abr": 4, "may": 5, "mai": 5,
         "jun": 6, "jul": 7, "aug": 8, "ago": 8, "sep": 9, "set": 9, "oct": 10, "out": 10,
         "nov": 11, "dec": 12, "dez": 12}
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def ler_data(txt):
    """'16 Sep 2026, 15:42:54' -> datetime"""
    m = re.search(r"(\d{1,2})\s+([A-Za-zç]{3})\w*\s+(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})", txt)
    if not m or m.group(2).lower() not in MESES:
        return None
    d, mes, a, h, mi, s = m.groups()
    return datetime(int(a), MESES[mes.lower()], int(d), int(h), int(mi), int(s))


def nome_arquivo(nome):
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome).strip(" .")
    return nome[:150] or "sem_nome"


def log(nome, data, status, tempo):
    novo = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if novo:
            w.writerow(["nome", "data", "status", "tempo_s", "registrado_em"])
        w.writerow([nome, data, status, f"{tempo:.0f}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])


def abrir_cofre(page):
    page.goto(COFRE, wait_until="domcontentloaded")
    if "login" in page.url:
        return False
    page.wait_for_selector("tbody tr", timeout=60_000)
    return True


def esperar_login(page):
    if sys.stdin.isatty():
        input("\n>>> Faça login na janela do navegador e aperte Enter aqui... ")
    else:
        print(f">>> Faça login na janela. Sigo quando entrar no cofre (ou existir {SINAL_OK}).", flush=True)
        fim = time.time() + 15 * 60
        while time.time() < fim and "/desk/" not in page.url and not SINAL_OK.exists():
            time.sleep(3)


def linhas_da_pagina(page):
    """Lê a tabela: [{uuid, nome, data_txt, tem_link}] — só leitura."""
    return page.evaluate("""(texto) => [...document.querySelectorAll('tbody tr')].map(tr => {
        const td = tr.querySelectorAll('td');
        if (td.length < 5) return null;
        const doc = (td[2].innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
        const uuid = ((td[2].innerText || '').match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/) || [''])[0];
        const tem = [...tr.querySelectorAll('a')].some(a => a.innerText.trim() === texto
                      && (a.getAttribute('href') || '').includes('gerardownload'));
        return {uuid, nome: doc[0] || '', data_txt: (td[1].innerText || '').replace(/\\s+/g, ' ').trim(),
                fase: (td[4].innerText || '').trim().split('\\n')[0], tem_link: tem};
    }).filter(Boolean)""", TEXTO_LINK)


def proxima_pagina(page):
    """Clica em 'Próxima'. Devolve False se não houver."""
    prox = page.locator(".pagination a", has_text=re.compile(r"^\s*Próxima\s*$"))
    if prox.count() == 0:
        return False
    li = prox.first.locator("xpath=..")
    if "disabled" in (li.get_attribute("class") or ""):
        return False
    ler = "() => { const tr = document.querySelector('tbody tr'); return tr ? tr.innerText : null; }"
    primeiro = page.evaluate(ler)
    prox.first.click()
    for _ in range(90):  # espera a tabela trocar (leitura sem espera embutida: tela em branco não trava)
        time.sleep(0.5)
        try:
            atual = page.evaluate(ler)
            if atual and atual != primeiro:
                return True
        except Exception:
            pass
    return False


def coletar(page, ano, mes):
    """Percorre as páginas (lista vem da mais nova para a mais velha) e junta as do mês."""
    alvo, pagina, vistos = [], 1, set()
    while True:
        linhas = linhas_da_pagina(page)
        datas = []
        for l in linhas:
            dt = ler_data(l["data_txt"])
            if dt is None:
                sys.exit(f"Data em formato inesperado na página {pagina}: {l['data_txt']!r}. Parando.")
            datas.append(dt)
            if (dt.year, dt.month) == (ano, mes) and l["uuid"] not in vistos:
                vistos.add(l["uuid"])  # doc novo durante a leitura empurra linhas: não duplicar
                alvo.append({**l, "data": dt, "pagina": pagina})
        print(f"  página {pagina}: {len(linhas)} linhas, {datas[-1]:%d/%m} a {datas[0]:%d/%m}", flush=True)
        if datas and max(datas) < datetime(ano, mes, 1):
            break
        if not proxima_pagina(page):
            break
        pagina += 1
    return alvo


def ir_para_pagina(page, n):
    if not abrir_cofre(page):
        sys.exit("A sessão caiu (voltou para o login). Rode de novo: os já baixados são pulados.")
    for _ in range(n - 1):
        if not proxima_pagina(page):
            return False
    return True


def baixar(page, item, destino):
    linha = page.locator("tbody tr", has_text=item["uuid"])
    if linha.count() != 1:
        return "linha_nao_encontrada"
    link = linha.locator("a[href*='gerardownload']", has_text=TEXTO_LINK)
    if link.count() == 0:
        return "sem_link"
    with page.expect_download(timeout=TIMEOUT_DOWNLOAD) as info:
        # o link fica num menu fechado; o clique via DOM dispara o mesmo javascript:eModalO(...)
        link.first.evaluate("a => a.click()")
    dl = info.value
    ext = Path(dl.suggested_filename).suffix or ".zip"
    dl.save_as(destino.parent / (destino.name + ext))
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="baixa no máximo N contratos")
    ap.add_argument("--mes", default="2026-08", help="AAAA-MM (padrão 2026-08)")
    ap.add_argument("--listar", action="store_true", help="só lista, não baixa")
    args = ap.parse_args()
    if not _COFRE_TXT.exists():
        sys.exit(f"Falta {_COFRE_TXT} com o endereço do cofre (https://secure.d4sign.com.br/desk/cofres/...).")
    global COFRE
    COFRE = _COFRE_TXT.read_text(encoding="utf-8").strip()
    ano, mes = map(int, args.mes.split("-"))
    pasta = BASE / "downloads" / f"{ano:04d}-{mes:02d}"
    pasta.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PERFIL), channel="msedge", headless=False, accept_downloads=True,
            viewport={"width": 1366, "height": 850})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(60_000)

        if not abrir_cofre(page):
            esperar_login(page)
            if not abrir_cofre(page):
                sys.exit("Não cheguei à tabela do cofre depois do login. Parando.")

        print(f"Lendo o cofre atrás de {mes:02d}/{ano}...", flush=True)
        itens = coletar(page, ano, mes)
        print(f"\n{len(itens)} documento(s) de {mes:02d}/{ano}; "
              f"{sum(1 for i in itens if i['fase'].upper().startswith('FINALIZADO'))} finalizado(s).\n", flush=True)
        if args.listar:
            for i in itens:
                print(f"  p{i['pagina']}  {i['data']:%d/%m %H:%M}  {i['fase'][:22]:22}  {i['nome']}")
            ctx.close()
            return

        feitos = 0
        for i in itens:
            if args.limite and feitos >= args.limite:
                break
            # quase todos se chamam "JAZIGO PERPÉTUO pdf": data + uuid tornam o nome único e estável
            nome = re.sub(r"\s+pdf$", "", i["nome"], flags=re.I)
            base = nome_arquivo(f"{i['data']:%Y-%m-%d_%H%M} {nome} ({i['uuid'][:8]})")
            destino = pasta / base
            data = f"{i['data']:%Y-%m-%d %H:%M:%S}"
            # procura pelo código: o renomear.py troca o resto do nome (jazigo e cliente na frente)
            if any(pasta.glob(f"*({i['uuid'][:8]}).*")):
                print(f"= já existe: {base}")
                log(i["nome"], data, "ja_existia", 0)
                continue
            if not i["fase"].upper().startswith("FINALIZADO"):
                print(f"- não finalizado ({i['fase']}): {base}")
                log(i["nome"], data, "nao_finalizado", 0)
                continue
            if not i["tem_link"]:
                print(f"- finalizado sem link de assinaturas: {base}")
                log(i["nome"], data, "sem_link_assinaturas", 0)
                continue
            print(f"> baixando: {base} ...", flush=True)
            t0 = time.time()
            try:
                status = "pagina_nao_encontrada"
                if ir_para_pagina(page, i["pagina"]):
                    status = baixar(page, i, destino)
                    # documentos novos no cofre empurram as linhas para as páginas seguintes
                    for _ in range(2):
                        if status != "linha_nao_encontrada" or not proxima_pagina(page):
                            break
                        status = baixar(page, i, destino)
            except PWTimeout:
                status = "timeout"
            except Exception as e:
                status = f"erro: {type(e).__name__}: {str(e)[:120]}"
            dt = time.time() - t0
            print(f"  {status} ({dt:.0f}s)", flush=True)
            log(i["nome"], data, status, dt)
            feitos += 1

        ctx.close()


def glob_escape(s):
    return re.sub(r"([\[\]*?])", r"[\1]", s)


if __name__ == "__main__":
    main()
