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
