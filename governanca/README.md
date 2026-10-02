<!-- ============================================
 grupo-humanidade / ferramentas / governanca
 Criado em: 01/10/2026.
============================================ -->

# Governança — as travas do Diário

O Diário de Bordo (`G:\Meu Drive\Grupo Humanidade\ESTADO ATUAL — Diario de Bordo.md`) perdeu uma
semana de registro duas vezes (28/09 e 01/10): a gravação do Cowork entregou ao Drive uma cópia
antiga do arquivo inteiro. `guarda.py` são as duas travas (CLAUDE.md, regra 13).

| Trava | O que faz |
|---|---|
| **1 · caixa de entrada** | O Cowork não grava o Diário: escreve na `Diário — caixa de entrada do Cowork.md` (raiz do Drive). O `guarda.py` junta as entradas no topo da Linha do tempo e no cabeçalho "Última atualização", sem duplicar linha que já está lá, e esvazia a caixa |
| **2 · cópia com alarme** | Os 4 documentos da raiz e a caixa vão para o repositório **local** `C:\Users\ricar\Documents\GitHub\governanca-copias` (sem remoto), um commit por mudança. Diário com data voltando no tempo ou encolhendo mais de 5% (os outros, 20%): a cópia boa fica, a junção não roda, aviso do Windows e a primeira linha do hook |

**Quando roda:** no início de toda sessão do Claude Code (hook `G:\Meu Drive\Grupo Humanidade\.claude\governanca-check.sh`, parte 0)
e de hora em hora pela tarefa do Windows **"Governança — guarda"** (`pythonw`, sem janela; saída em
`governanca-copias/guarda.log`).

```bash
python guarda.py --restaurar
```
Devolve ao Drive a última cópia boa do Diário (a que estava lá fica em `_diario_substituido_.md`).

```bash
python guarda.py --aceitar
```
Aceita um encolhimento deliberado (limpeza do Diário) — sem isso o alarme trava as cópias.

**Teste:** `python teste/teste.py` — 12 casos numa raiz de mentira (`GOV_RAIZ`/`GOV_COPIAS`); nunca toca o Drive.
