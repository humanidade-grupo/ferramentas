# Timbrado — documento em PDF no papel do Parque da Saudade

**"Timbrado", no vocabulário do grupo, é ESTE modelo** (decisão do Ricardo, 19/09/2026): sempre que ele
pedir um documento "timbrado", em qualquer sessão do Cowork ou do Claude Code, o PDF sai neste layout.

A referência visual é a **Tabela de Preços impressa** (`02-parque-da-saudade/sistemas/pocket/tabelas-preco/`,
a das Retomadas de 13/09/2026). As medidas do `timbrado.css` foram tiradas dela, ponto a ponto:

- A4, margem 34,5 pt · tinta `#111` · secundário `#666` · zebra `#F4F3EF` · fio das linhas `#E6E6E6`
- **Cabeçalho:** andorinha + `PARQUE DA SAUDADE` (PF Marlet 13,5 pt) + `CEMITÉRIO PARQUE · JUIZ DE FORA`
  (Ingra 6 pt, espaçado) à esquerda · título do documento (PF Marlet 11,2 pt) + subtítulo espaçado à direita ·
  fio preto de 0,75 pt embaixo
- **Rótulo de seção** em caixa alta espaçada, com um complemento à direita
- **Tabela:** cabeçalho preto com texto branco espaçado, linhas de 18 pt com zebra
- **Observações:** caixa de fio com título em PF Marlet espaçado e lista numerada
- **Rodapé:** fio preto e duas datas em caixa alta espaçada

## Como gerar

```bash
python gerar.py miolo.html saida.pdf --titulo "Ciclo de Vendas" --subtitulo "Do primeiro contato ao contrato"
```

- `miolo.html` é só o conteúdo, um fragmento com as classes do `timbrado.css`: `.lead`, `.destaques`,
  `.rotulo`, `table.tab` (`.r`, `.forte`, `.sec`, `tr.total`), `.texto`, `.obs`, `.rodape`, `.quebra`.
  O cabeçalho é montado pelo script. Exemplo completo: `exemplo_ciclo_de_vendas.html`.
- **As fontes não estão neste repositório**, porque ele é público: o script as lê na hora do
  `docs/index.html` do clone do `pocket-nps` (padrão `../../pocket-nps/docs/index.html`, ou `--pocket`).
- Imprime pelo Edge ou Chrome da máquina (Playwright `channel`), e só usa o Chromium do Playwright se
  nenhum dos dois existir. Ao terminar, avisa se alguma fonte não carregou e diz quantas páginas saíram.

## Quando a sessão não consegue rodar o script (Cowork sem Python/Chromium)

Montar o HTML à mão com o `timbrado.css` inteiro colado num `<style>`, as duas `@font-face` copiadas do
`docs/index.html` do Pocket e a `andorinha.png` em base64, e imprimir em A4 com fundo. **Não inventar outro
layout**: se algo do conteúdo não couber nos componentes acima, criar o componente novo no `timbrado.css`
com as mesmas medidas, e fazer o commit dele aqui.

## Armadilhas

- **Conferir o PDF renderizado, não o HTML.** O navegador pode cair na fonte de reserva sem dar erro
  nenhum. O script avisa, mas a prova é olhar a página.
- `print_background` precisa estar ligado, senão o cabeçalho preto das tabelas sai branco.
