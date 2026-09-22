# d4sign-lote — contratos da D4Sign, uma vez por mês

A conta da D4Sign é gratuita: **sem API e sem download em lote pela tela.** Estes dois scripts baixam os
contratos **FINALIZADOS** de um mês e renomeiam cada `.zip` com o jazigo e o cliente.

Diferente das outras ferramentas deste repo, **não é página publicada**: roda na máquina do Ricardo
(Python + Playwright + Edge). Mora aqui porque código mora no GitHub.

## Onde ficam os dados — nunca neste repo

Tudo o que não é código fica em `%USERPROFILE%\Documents\d4sign-lote\` (ou na pasta de `D4SIGN_DADOS`):

| Arquivo | O que é |
|---|---|
| `cofre.txt` | endereço do cofre na D4Sign (uma linha). **Obrigatório.** Fica fora porque este repo é público. |
| `perfil\` | sessão do Edge do script. O login é feito à mão, uma vez; o script nunca vê a senha. |
| `downloads\AAAA-MM\` | os contratos. **Têm CPF e contatos.** |
| `log.csv` · `renomear_previa.csv` | registro do download e prévia dos nomes. |

## Uso

```
python baixar.py --mes 2026-09            # baixa os finalizados com Cadastro em set/2026
python baixar.py --mes 2026-09 --listar   # só lista
python baixar.py --mes 2026-09 --limite 1 # teste
python renomear.py 2026-09                # gera a prévia, NÃO renomeia
python renomear.py 2026-09 --aplicar      # renomeia conforme a prévia
```

No Claude Code, a rotina inteira é a skill **`/contratos-d4sign AAAA-MM`**
(`Grupo Humanidade\.claude\skills\contratos-d4sign\`), que para antes de renomear.

## O que o script faz e não faz na D4Sign

- Clica **só** em "Próxima" e em "Download (original e assinaturas)", um contrato por vez.
- Pula o que já foi baixado, reconhecendo pelo código de 8 caracteres entre parênteses no nome. Se cair, basta rodar de novo.
- Nome final: `M-19-155 - Cliente - 2026-08-12 JAZIGO PERPÉTUO (cb520b4c).zip`. A Reserva não tem jazigo físico e sai como `RESERVA - …`.

Requisitos: `pip install playwright pymupdf` e o Microsoft Edge instalado.

## `status.py` — o status de assinatura no Cofre, sem baixar nada (19/09/2026)

Lê a **tela** do cofre (listagem paginada + o modal de signatários de cada documento) e grava
na aba `Contratos_D4Sign` do Cofre do Parque pela rota POST `?app=d4sign&fn=gravar`. Nenhum PDF
é baixado; só abre o modal de signatários, nunca clica em Download, ASSINAR, editar ou TAGs.

```
python status.py --dry-run            # varre e imprime o payload; NÃO envia
python status.py                      # varre e envia (reescreve o espelho inteiro)
python status.py --limite 5 --dry-run # só os 5 mais novos, para teste
python status.py --so-pendentes       # modal só dos não finalizados (sem e-mail, os finalizados casam só pelo jazigo)
```

- **Precisa de `token.txt`** na pasta de dados, com o token de gestão do Cofre. Nunca neste repo.
- Em disco escreve só `status_log.csv` (contagens por fase, nenhum nome ou e-mail).
- 🖱️ **`atualizar-d4sign.cmd` é a passada MANUAL** — atalho **"Atualizar D4Sign"** na área de
  trabalho do Ricardo. Abre a janela, espera o login se precisar, mostra o resultado e fica
  aberto no fim. É o caminho que funciona quando a sessão caiu, porque tem gente na frente.
  ⚠️ **Editar esse .cmd só em ASCII e CRLF**: com LF o `cmd.exe` come o primeiro caractere de
  cada linha (custou uma execução torta em 22/09/2026).
- **Roda sozinho** pela tarefa agendada do Windows **"D4Sign - status diario"** — **8h, 14h e
  20h** desde 21/09 (se o PC estava desligado, roda quando ligar; duas execuções nunca se
  atropelam). **Se a sessão da D4Sign cair, a passada agendada aborta em segundos** (22/09):
  esperar login que ninguém vai digitar só deixa uma janela aberta na frente de quem trabalha.
  O motivo vai para o Cofre (`?app=d4sign&fn=falha`), a tarja da PonteApp passa a dizer
  "a sessão da D4Sign caiu", e sai **e-mail** (destinatário em `sync.email` da Config, no
  máximo um a cada 6 h por motivo). O conserto é clicar no atalho e logar.
- 🔁 **O que é passageiro tem retry, porque a leitura custa ~10 min:** a 1ª página recarrega uma
  vez se a tabela não vier em 30 s; o envio de cada lote tenta 3× (o `/exec` devolveu **404** em
  22/09) e também quando o Cofre responde "outra escrita em andamento" (a importação do Facilita
  segurando a trava — foi o lote 6/6 recusado em 22/09). Reenviar o mesmo lote é idempotente.
- 🙈 **`--escondido` (headless) NÃO é o padrão:** medido em 22/09, a tabela da D4Sign às vezes
  não renderiza sem janela — sessão viva, página abre, ZERO linhas. Em 21/09 às 20:43 funcionou;
  no dia seguinte, não.
- O e-mail do cliente vai para o Cofre só para casar com a venda (vira Deal ID) e não é
  gravado. O nome do documento sai por lista fechada de palavras, porque ele traz o nome do cliente.
- O que a tela ensinou (19/09): uma `<tr>` por signatário no modal; "assinou" = ícone
  `color-verde`; o modal seguinte precisa esperar a animação do anterior fechar; o
  `wait_for_function` do Playwright não funciona nesta página.
