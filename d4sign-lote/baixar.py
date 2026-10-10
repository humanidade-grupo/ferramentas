"""Baixa em lote os contratos FINALIZADOS de um mês, pela API da D4Sign (uso local).

Uso:
  python baixar.py --mes 2026-09              # baixa os finalizados com cadastro no mês
  python baixar.py --mes 2026-09 --listar     # só lista, não baixa
  python baixar.py --mes 2026-09 --limite 1   # teste com 1 contrato
  python baixar.py --tudo                     # todos os finalizados da pasta, de qualquer mês

10/10/2026: a D4Sign ganhou API, e este script deixou de abrir o Edge. Sem navegador, sem login,
sem sessão que cai. SÓ LEITURA na D4Sign: lista a pasta, lê os signatários e pede o download
(original + assinaturas, o mesmo .zip do link da tela). Nada é enviado, assinado ou apagado.

Dados em %USERPROFILE%\\Documents\\d4sign-lote (ou D4SIGN_DADOS), FORA do repo (o repo é público):
  cofre.txt      endereço do cofre na D4Sign — o script tira dele o id do cofre e da pasta
  chave_api.txt  a chave da API: 1ª linha tokenAPI, 2ª linha cryptKey (ou as variáveis de
                 ambiente D4SIGN_TOKEN_API e D4SIGN_CRYPT_KEY). NUNCA no repo.

O mês é o do CADASTRO do documento. A API não dá essa data: ela sai da inclusão do primeiro
signatário, que em 10/10 bateu com o Cadastro da tela em até 20 min nos 199 documentos.
O nome do arquivo é o de antes ("AAAA-MM-DD_HHMM <nome> (<8 do uuid>).zip"), e o renomear.py
segue igual. Já baixado (pelo código de 8 caracteres) é pulado.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

BASE = Path(os.environ.get("D4SIGN_DADOS", Path.home() / "Documents" / "d4sign-lote"))
LOG = BASE / "log.csv"
_COFRE_TXT = BASE / "cofre.txt"
_CHAVE_TXT = BASE / "chave_api.txt"
API = "https://secure.d4sign.com.br/api/v1/"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FINALIZADO = "4"   # statusId da D4Sign
ESPERA_LIMITE_S = 5 * 60


class Limite(Exception):
    """A D4Sign limitou o método (vem como HTTP 401 "já atingiu o tempo limite para este método").
    Não é chave recusada: os outros métodos seguem respondendo. Em 10/10 o download travou
    depois de ~15 pedidos em meia hora."""


def chave():
    tok, cry = os.environ.get("D4SIGN_TOKEN_API", "").strip(), os.environ.get("D4SIGN_CRYPT_KEY", "").strip()
    if not (tok and cry) and _CHAVE_TXT.exists():
        linhas = [l.strip() for l in _CHAVE_TXT.read_text(encoding="utf-8").splitlines() if l.strip()]
        if len(linhas) >= 2:
            tok, cry = linhas[0], linhas[1]
    if not (tok and cry):
        sys.exit(f"Falta a chave da API: crie {_CHAVE_TXT} com o tokenAPI na 1ª linha e o cryptKey na 2ª.")
    return tok, cry


def cofre_e_pasta():
    if not _COFRE_TXT.exists():
        sys.exit(f"Falta {_COFRE_TXT} com o endereço do cofre (https://secure.d4sign.com.br/desk/cofres/...).")
    ids = UUID.findall(_COFRE_TXT.read_text(encoding="utf-8"))
    if len(ids) < 2:
        sys.exit(f"{_COFRE_TXT} não tem o id do cofre e o da pasta.")
    return ids[0], ids[1]


class D4:
    """A API da D4Sign. Toda mensagem de erro sai daqui sem a chave."""

    def __init__(self, tok, cry):
        self.q = "tokenAPI=" + urllib.parse.quote(tok) + "&cryptKey=" + urllib.parse.quote(cry)
        self._seg = (tok, cry)

    def _limpa(self, s):
        for v in self._seg:
            s = s.replace(v, "***")
        return s

    def chamar(self, caminho, corpo=None, tentativas=3):
        url = API + caminho + ("&" if "?" in caminho else "?") + self.q
        dados = json.dumps(corpo).encode() if corpo is not None else None
        for n in range(tentativas):
            req = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json",
                                                                   "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                msg = e.read()[:200].decode("utf-8", "replace")
                if e.code in (401, 429) and re.search(r"tempo limite|limit", msg, re.I):
                    raise Limite(self._limpa(msg))
                if e.code in (401, 403):
                    sys.exit(f"A D4Sign recusou a chave da API (HTTP {e.code}): {self._limpa(msg)}")
                if (e.code != 429 and e.code < 500) or n == tentativas - 1:
                    raise RuntimeError(f"HTTP {e.code} em {caminho.split('?')[0]}: {self._limpa(msg)}") from None
            except urllib.error.URLError as e:
                if n == tentativas - 1:
                    raise RuntimeError(f"sem resposta da D4Sign: {self._limpa(str(e.reason))}") from None
            time.sleep(3 * (n + 1))

    def documentos(self, cofre, pasta):
        docs, pg = [], 1
        while True:
            j = self.chamar(f"documents/{cofre}/safe/{pasta}?pg={pg}")
            docs += [d for d in j[1:] if d.get("uuidDoc")]
            if pg >= int(j[0].get("total_pages") or 1):
                if len(docs) != int(j[0].get("total_documents") or 0):
                    sys.exit(f"A API anunciou {j[0].get('total_documents')} documentos e entregou {len(docs)}. Parando.")
                return docs
            pg += 1

    def cadastro(self, uuid):
        """A inclusão do 1º signatário: o Cadastro da tela, em até ~20 min."""
        j = self.chamar(f"documents/{uuid}/list")
        sigs = (j[0].get("list") if j and isinstance(j[0], dict) else None) or []
        datas = sorted(d for d in (str(s.get("date") or "") for s in sigs)
                       if re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", d))
        return datetime.strptime(datas[0][:19], "%Y-%m-%d %H:%M:%S") if datas else None

    def baixar(self, uuid, destino):
        j = self.chamar(f"documents/{uuid}/download", {"type": "ZIP", "language": "pt"})
        url = j.get("url") or ""
        if not url.startswith("https://"):
            return "sem_url"
        with urllib.request.urlopen(url, timeout=600) as r:
            corpo = r.read()
        if corpo[:2] != b"PK":
            return "nao_e_zip"
        destino.parent.joinpath(destino.name + ".zip").write_bytes(corpo)
        return "ok"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", help="AAAA-MM (cadastro no mês)")
    ap.add_argument("--tudo", action="store_true", help="todos os finalizados, cada um na pasta do seu mês")
    ap.add_argument("--limite", type=int, default=0, help="baixa no máximo N contratos")
    ap.add_argument("--listar", action="store_true", help="só lista, não baixa")
    ap.add_argument("--esperar-limite", type=int, default=180,
                    help="minutos que o lote espera, no total, quando a D4Sign limita o download (padrão 180)")
    args = ap.parse_args()
    if not (args.mes or args.tudo):
        sys.exit("Diga o mês (--mes AAAA-MM) ou --tudo.")
    alvo = tuple(map(int, args.mes.split("-"))) if args.mes else None

    d4 = D4(*chave())
    cofre, pasta = cofre_e_pasta()
    print("Lendo a pasta pela API...", flush=True)
    finalizados = [d for d in d4.documentos(cofre, pasta) if str(d.get("statusId")) == FINALIZADO]
    print(f"{len(finalizados)} finalizado(s) na pasta. Lendo a data de cadastro de cada um...", flush=True)
    with ThreadPoolExecutor(max_workers=6) as ex:
        cads = list(ex.map(lambda d: d4.cadastro(d["uuidDoc"]), finalizados))

    itens = []
    for d, cad in zip(finalizados, cads):
        if cad is None:
            print(f"! sem data de cadastro (sem signatários?): ({d['uuidDoc'][:8]}) — fora do lote")
            continue
        if alvo and (cad.year, cad.month) != alvo:
            continue
        itens.append({"uuid": d["uuidDoc"], "nome": d.get("nameDoc") or "", "data": cad})
    itens.sort(key=lambda i: i["data"])
    rot = f"{alvo[1]:02d}/{alvo[0]}" if alvo else "todos os meses"
    print(f"\n{len(itens)} finalizado(s) — {rot}.\n", flush=True)
    if args.listar:
        for i in itens:
            print(f"  {i['data']:%d/%m %H:%M}  ({i['uuid'][:8]})  {i['nome']}")
        return

    feitos, esperado = 0, 0
    for i in itens:
        if args.limite and feitos >= args.limite:
            break
        dest_pasta = BASE / "downloads" / f"{i['data']:%Y-%m}"
        dest_pasta.mkdir(parents=True, exist_ok=True)
        # a tela mostrava "JAZIGO PERPÉTUO pdf"; a API, "JAZIGO PERPÉTUO.pdf" — o mesmo nome de antes
        nome = re.sub(r"[\s.]+pdf$", "", i["nome"], flags=re.I)
        base = nome_arquivo(f"{i['data']:%Y-%m-%d_%H%M} {nome} ({i['uuid'][:8]})")
        data = f"{i['data']:%Y-%m-%d %H:%M:%S}"
        # procura pelo código: o renomear.py troca o resto do nome (jazigo e cliente na frente)
        if any(dest_pasta.glob(f"*({i['uuid'][:8]}).*")):
            print(f"= já existe: {base}")
            log(i["nome"], data, "ja_existia", 0)
            continue
        print(f"> baixando: {base} ...", flush=True)
        t0 = time.time()
        while True:
            try:
                status = d4.baixar(i["uuid"], dest_pasta / base)
            except Limite:
                if esperado >= args.esperar_limite * 60:
                    print(f"  a D4Sign segue limitando o download depois de {esperado // 60} min. Parando: "
                          f"rode de novo mais tarde (os já baixados são pulados).", flush=True)
                    log(i["nome"], data, "limite_d4sign", time.time() - t0)
                    return
                print(f"  a D4Sign limitou o download; espero {ESPERA_LIMITE_S // 60} min e tento de novo "
                      f"(já esperei {esperado // 60} min)...", flush=True)
                time.sleep(ESPERA_LIMITE_S)
                esperado += ESPERA_LIMITE_S
                continue
            except Exception as e:
                status = f"erro: {type(e).__name__}: {str(e)[:120]}"
            break
        dt = time.time() - t0
        print(f"  {status} ({dt:.0f}s)", flush=True)
        log(i["nome"], data, status, dt)
        feitos += 1


if __name__ == "__main__":
    main()
