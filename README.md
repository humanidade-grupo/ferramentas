# ferramentas — Grupo Humanidade

Utilitários avulsos do grupo: páginas estáticas, **sem dado por trás**, que alguém abre por link e usa.

## Por que este repositório existe

A arquitetura do grupo tem dois produtos — o **Pocket** (app do vendedor do Parque) e o **Painel Comercial** (gestão, Parque + Estrela). Um utilitário não é nenhum dos dois: não tem tela dentro de produto, não tem dono de produto, não escreve no Cofre.

Antes de existir este repositório, um utilitário só tinha dois destinos ruins: virar pasta dentro do repo do Pocket — o que o coloca **dentro do escopo do PWA**, fazendo o link abrir dentro da casca do app instalado — ou ganhar um repositório próprio, multiplicando repositório a cada ferramentinha.

Aqui eles ficam juntos, num caminho separado do Pocket.

## O que tem

| Ferramenta | URL | Para quem |
|---|---|---|
| **Emissor de Recibos** | `https://humanidade-grupo.github.io/ferramentas/recibos/` | Financeiro do Parque da Saudade |

## Regras

- **Página autossuficiente.** Todo CSS, JS e imagem embutidos no próprio HTML. Sem CDN, sem asset relativo — é o que permite mover a ferramenta de lugar sem quebrar.
- **Sem `manifest.webmanifest` e sem service worker.** Utilitário não é app instalável. Foi exatamente o escopo de PWA que trouxe o recibo para cá.
- **Nenhum segredo no HTML.** Se a ferramenta precisar de dado ou de token, ela deixou de ser utilitário — vira tela de um dos dois produtos, com o Cofre atrás.
- **Sem estado.** Se precisar guardar ou numerar algo de forma única (um contador de recibos, por exemplo), também deixa de ser utilitário.

## Publicação

GitHub Pages servindo a branch `main`, pasta `/docs`. Uma pasta por ferramenta dentro de `docs/`.

O `.nojekyll` em `docs/` impede o Jekyll de processar os arquivos.
