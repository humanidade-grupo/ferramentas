# ============================================
# grupo-humanidade / ferramentas / governanca / guarda.py
# Criado em: 01/10/2026.
#
# As duas travas do Diário de Bordo, depois de o Cowork regravar o Diário com
# uma cópia de 24/09 (28/09 12h55 e 01/10 21h10): ele grava pelo caminho de
# rascunho e o Drive recebe uma versão antiga do mesmo nome.
#
#   TRAVA 1 — o Cowork não grava mais o Diário. Ele escreve na
#   "Diário — caixa de entrada do Cowork.md", e este script junta as entradas
#   no Diário: a linha no topo da Linha do tempo, o cabeçalho em "Última
#   atualização" (o anterior desce para "Anterior"). Linha que já está no
#   Diário não entra de novo, então uma caixa regravada com entradas velhas não
#   duplica nada.
#
#   TRAVA 2 — cópia com alarme. Os 4 documentos da raiz (e a caixa) vão para um
#   repositório git local, com um commit a cada mudança. Se o Diário voltar no
#   tempo (data de "Última atualização" mais antiga que a da cópia) ou encolher
#   mais de 5%, a cópia NÃO é sobrescrita, a junção não roda e o alarme toca
#   (aviso do Windows + o texto que o hook de início de sessão mostra).
#
# Uso:
#   python guarda.py              — guarda, confere e junta a caixa (tarefa agendada)
#   python guarda.py --silencioso — o mesmo, sem aviso do Windows (o hook usa)
#   python guarda.py --aceitar    — aceita um encolhimento DELIBERADO (limpeza do Diário)
#   python guarda.py --restaurar  — devolve ao Drive a última cópia boa do Diário
#
# Teste: python teste/teste.py (raiz de mentira; GOV_RAIZ e GOV_COPIAS só servem a ele).
# ============================================

import datetime
import os
import pathlib
import re
import shutil
import subprocess
import sys

RAIZ = pathlib.Path(os.environ.get("GOV_RAIZ", "G:/Meu Drive/Grupo Humanidade"))
COPIAS = pathlib.Path(os.environ.get("GOV_COPIAS", "C:/Users/ricar/Documents/GitHub/governanca-copias"))
DIARIO = "ESTADO ATUAL — Diario de Bordo.md"
CAIXA = "Diário — caixa de entrada do Cowork.md"
DOCS = [DIARIO, "CLAUDE.md", "INFRA.md", "ARQUITETURA — Como tudo se encaixa.md", CAIXA]
ENCOLHE_MAX = {DIARIO: 0.05}          # o resto: 20%
ANCORA_TABELA = "| Data | O que mudou |\n|---|---|\n"   # o Diário mora com LF (conferido em 01/10)

CAIXA_MODELO = """# Diário — caixa de entrada do Cowork

> **O Cowork NÃO grava o `ESTADO ATUAL — Diario de Bordo.md`.** Desde 01/10/2026 ele escreve aqui,
> e o `guarda.py` (repo `ferramentas/governanca`) junta as entradas no Diário — a cada início de
> sessão do Claude Code e de hora em hora. Depois de juntar, esta caixa volta a ficar vazia.
>
> **Por quê:** em 28/09 e em 01/10 a gravação do Cowork entregou ao Drive uma cópia antiga do Diário
> e apagou uma semana de registro. Uma caixa pequena perdida custa uma linha; o Diário custa a semana.
>
> **Formato — uma entrada por mudança, acrescentada no FIM do arquivo (nunca apagar a de outro):**
>
> ```
> ## ENTRADA
> cabecalho: **DD/MM/AAAA, período (Cowork, assunto)** — o que mudou, em uma linha
> linha: | **DD/MM, período (Cowork, assunto)** | o que mudou, com ponteiros |
> ```
>
> A `linha:` é a linha da Linha do tempo, já no formato da tabela (começa e termina com `|`, sem
> quebra de linha dentro). O `cabecalho:` vira a "Última atualização". Releia o arquivo antes de
> gravar e grave só acrescentando.

<!-- entradas abaixo desta linha -->
"""


def ler(p):
    # newline="": sem isso o Windows leria e gravaria CRLF, e a primeira junção
    # trocaria a quebra de linha do Diário inteiro.
    if not p.exists():
        return None
    with open(p, encoding="utf-8", newline="") as f:
        return f.read()


def gravar(p, txt):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(txt)


def data_cabecalho(txt):
    m = re.search(r"Última atualização: \*\*(\d\d)/(\d\d)/(\d{4})", txt or "")
    return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def git(*args):
    return subprocess.run(["git", "-C", str(COPIAS), *args], capture_output=True, text=True, encoding="utf-8")


def avisar(titulo, texto, silencioso):
    print(f"🔴 {titulo}\n   {texto}")
    if silencioso:
        return
    t = texto.replace("'", "")[:240]
    ps = ("Add-Type -AssemblyName System.Windows.Forms; $n=New-Object System.Windows.Forms.NotifyIcon; "
          "$n.Icon=[System.Drawing.SystemIcons]::Warning; $n.Visible=$true; "
          f"$n.ShowBalloonTip(30000,'{titulo}','{t}',[System.Windows.Forms.ToolTipIcon]::Warning); Start-Sleep 31; $n.Dispose()")
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps])


def preparar_repo():
    if not (COPIAS / ".git").exists():
        COPIAS.mkdir(parents=True, exist_ok=True)
        git("init", "-q")
        git("config", "core.autocrlf", "false")   # a cópia tem de ser byte a byte a do Drive (LF)
        gravar(COPIAS / ".gitignore", "guarda.log\n_diario_substituido_.md\n")
        gravar(COPIAS / "README.md",
               "# Cópias da governança do Grupo Humanidade\n\nGeradas por `ferramentas/governanca/guarda.py`. "
               "Só local — não tem remoto. Uma cópia por mudança dos 4 documentos da raiz do Drive e da caixa de "
               "entrada do Cowork. Restaurar o Diário: `python guarda.py --restaurar`.\n")
        git("add", "README.md")
        git("commit", "-q", "-m", "início das cópias")


def regrediu(nome, atual, copia):
    """Devolve o motivo do alarme, ou None."""
    if nome == CAIXA:
        return None   # a caixa esvazia por desenho a cada junção: encolher é o normal dela
    if atual is None:
        return "o arquivo sumiu do Drive" if copia is not None else None
    if copia is None:
        return None
    if nome == DIARIO:
        da, dc = data_cabecalho(atual), data_cabecalho(copia)
        if da and dc and da < dc:
            return f"a 'Última atualização' voltou de {dc:%d/%m/%Y} para {da:%d/%m/%Y}"
    lim = ENCOLHE_MAX.get(nome, 0.20)
    ta, tc = len(atual.encode("utf-8")), len(copia.encode("utf-8"))
    if tc and ta < tc * (1 - lim):
        return f"encolheu de {tc:,} para {ta:,} bytes".replace(",", ".")
    return None


def guardar(aceitar, silencioso):
    preparar_repo()
    alarmes, mudou = [], []
    for nome in DOCS:
        atual = ler(RAIZ / nome)
        copia = ler(COPIAS / nome)
        if atual is None and nome == CAIXA:
            continue
        motivo = None if aceitar else regrediu(nome, atual, copia)
        if motivo:
            alarmes.append(f"{nome}: {motivo}")
            continue
        if atual is not None and atual != copia:
            gravar(COPIAS / nome, atual)
            mudou.append(nome)
    if mudou:
        git("add", "-A")
        git("commit", "-q", "-m", "cópia: " + ", ".join(mudou))
    for a in alarmes:
        avisar("Governança: documento regrediu", a + " — a cópia boa foi mantida. Rode guarda.py --restaurar.", silencioso)
    return alarmes, mudou


def entradas_da_caixa(txt):
    corpo = txt.split("<!-- entradas abaixo desta linha -->", 1)[-1]
    out = []
    for b in re.split(r"^## ENTRADA\s*$", corpo, flags=re.M):
        cab = re.search(r"^cabecalho:\s*(.+?)\s*$", b, re.M)
        lin = re.search(r"^linha:\s*(\|.+\|)\s*$", b, re.M)
        if lin:
            out.append((cab.group(1) if cab else None, lin.group(1)))
    return out


def juntar_caixa():
    caixa_p, diario_p = RAIZ / CAIXA, RAIZ / DIARIO
    caixa = ler(caixa_p)
    if caixa is None:
        gravar(caixa_p, CAIXA_MODELO)
        return 0
    entradas = entradas_da_caixa(caixa)
    if not entradas:
        return 0
    diario = ler(diario_p)
    assert diario and ANCORA_TABELA in diario, "Diário sem a tabela da Linha do tempo — nada feito"
    novas = [(c, l) for c, l in entradas if l not in diario]
    if novas:
        # a caixa é cronológica e a tabela é decrescente: a entrada mais nova fica no topo
        bloco = "".join(l + "\n" for _, l in reversed(novas))
        diario = diario.replace(ANCORA_TABELA, ANCORA_TABELA + bloco, 1)
        cab = next((c for c, _ in reversed(novas) if c), None)
        if cab:
            diario = re.sub(r"^> Última atualização: ", lambda m: "> Última atualização: " + cab + "\n>\n> Anterior: ",
                            diario, count=1, flags=re.M)
        gravar(diario_p, diario)
        relido = ler(diario_p)
        assert all(l in relido for _, l in novas), "releitura do Diário não achou as linhas — conferir"
    gravar(caixa_p, CAIXA_MODELO)
    return len(novas)


def restaurar():
    copia = ler(COPIAS / DIARIO)
    assert copia, "não há cópia do Diário"
    atual = ler(RAIZ / DIARIO)
    if atual:
        gravar(COPIAS / "_diario_substituido_.md", atual)
    shutil.copyfile(COPIAS / DIARIO, RAIZ / DIARIO)
    print(f"Diário restaurado da cópia ({len(copia.encode('utf-8')):,} bytes). ".replace(",", ".") +
          "O que estava no Drive ficou em governanca-copias/_diario_substituido_.md.")


def main():
    a = sys.argv[1:]
    if sys.stdout is None:   # pythonw (tarefa agendada, sem janela): a saída vai para o log
        COPIAS.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(COPIAS / "guarda.log", "a", encoding="utf-8")
        print(f"--- {datetime.datetime.now():%d/%m/%Y %H:%M}")
    if "--restaurar" in a:
        restaurar()
        return 0
    alarmes, mudou = guardar("--aceitar" in a, "--silencioso" in a)
    if alarmes:
        print("   A caixa do Cowork NÃO foi juntada enquanto houver alarme.")
        return 2
    n = juntar_caixa()
    if n:
        guardar(False, True)   # a cópia já leva o Diário com as linhas juntadas
    print(f"✅ Cópias em dia ({len(mudou)} documento(s) mudaram) · caixa do Cowork: {n} entrada(s) juntada(s) ao Diário.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
