"""gerar.py — documento TIMBRADO do Parque da Saudade em PDF (19/09/2026).

"Timbrado", no vocabulário do grupo, é este modelo: o mesmo layout das Tabelas
de Preço impressas (andorinha + PARQUE DA SAUDADE à esquerda, título do
documento em PF Marlet à direita, fio preto, tabelas de cabeçalho preto com
zebra, caixa de observações, rodapé com fio e datas).

Uso:
    python gerar.py conteudo.html saida.pdf --titulo "Ciclo de Vendas" --subtitulo "Funil do Parque"

`conteudo.html` é só o MIOLO (um fragmento com as classes do timbrado.css:
.rotulo, table.tab, .destaques, .texto, .lead, .obs, .rodape, .quebra).
O cabeçalho é montado aqui, a partir de --titulo e --subtitulo.

As fontes (Ingra e PF Marlet Display) não são copiadas para este repositório,
que é público: são lidas, na hora, do docs/index.html do clone do pocket-nps
(onde já moram embutidas). Caminho padrão: ../../pocket-nps/docs/index.html,
ou o que vier em --pocket.
"""
import argparse, base64, pathlib, re, sys
from playwright.sync_api import sync_playwright

AQUI = pathlib.Path(__file__).resolve().parent


def fontes(pocket_index: pathlib.Path) -> str:
    html = pocket_index.read_text(encoding="utf-8")
    faces = re.findall(r'@font-face\{font-family:"(?:Ingra|PF Marlet Display)"[^}]*\}', html)
    if len(faces) < 2:
        sys.exit(f"Fontes não encontradas em {pocket_index} (esperava Ingra e PF Marlet Display).")
    return "\n".join(faces)


def montar(miolo: str, titulo: str, subtitulo: str, pocket_index: pathlib.Path) -> str:
    logo = base64.b64encode((AQUI / "andorinha.png").read_bytes()).decode()
    css = (AQUI / "timbrado.css").read_text(encoding="utf-8")
    cab = f"""
<header class="cab">
  <div class="marca">
    <img src="data:image/png;base64,{logo}" alt="">
    <div><div class="nome">Parque da Saudade</div><div class="sub">Cemitério Parque · Juiz de Fora</div></div>
  </div>
  <div class="doc"><div class="titulo">{titulo}</div><div class="sub">{subtitulo}</div></div>
</header>"""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo}</title><style>{fontes(pocket_index)}
{css}</style></head><body>{cab}
{miolo}
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("conteudo")
    ap.add_argument("saida")
    ap.add_argument("--titulo", required=True)
    ap.add_argument("--subtitulo", default="")
    ap.add_argument("--pocket", default=str(AQUI.parent.parent / "pocket-nps" / "docs" / "index.html"))
    a = ap.parse_args()

    html = montar(pathlib.Path(a.conteudo).read_text(encoding="utf-8"), a.titulo, a.subtitulo, pathlib.Path(a.pocket))
    tmp = pathlib.Path(a.saida).with_suffix(".montado.html")
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        # Edge/Chrome já instalados na máquina (o d4sign-lote faz igual); o
        # Chromium próprio do Playwright só se nenhum dos dois existir.
        b = None
        for canal in ("msedge", "chrome", None):
            try:
                b = p.chromium.launch(channel=canal) if canal else p.chromium.launch()
                break
            except Exception:
                continue
        if b is None:
            sys.exit("Nenhum navegador: instale o Edge/Chrome ou rode `playwright install chromium`.")
        pg = b.new_page()
        pg.goto(tmp.resolve().as_uri())
        pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        faltando = pg.evaluate("""[...document.fonts].filter(f=>f.status!=='loaded').map(f=>f.family)""")
        pg.pdf(path=a.saida, format="A4", print_background=True, prefer_css_page_size=True)
        b.close()
    tmp.unlink()
    if faltando:
        print("ATENÇÃO: fontes não carregadas:", faltando)
    try:
        import pymupdf
        print(f"{a.saida}: {pymupdf.open(a.saida).page_count} página(s)")
    except ImportError:
        print(a.saida)


if __name__ == "__main__":
    main()
