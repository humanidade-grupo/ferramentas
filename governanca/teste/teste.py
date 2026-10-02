# Teste do guarda.py numa raiz de mentira (nunca toca o Drive): python teste/teste.py
import os, pathlib, subprocess, sys, tempfile, shutil

T = pathlib.Path(tempfile.mkdtemp())
R, C = T / 'raiz', T / 'copias'
R.mkdir()
env = dict(os.environ, GOV_RAIZ=str(R), GOV_COPIAS=str(C), PYTHONIOENCODING='utf-8')
G = str(pathlib.Path(__file__).parent.parent / 'guarda.py')


def run(*a):
    return subprocess.run([sys.executable, G, '--silencioso', *a], env=env, capture_output=True, text=True, encoding='utf-8')


def w(p, t):
    with open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(t)


def r_(p):
    with open(p, encoding='utf-8', newline='') as f:
        return f.read()


ok = 0


def caso(nome, cond):
    global ok
    assert cond, nome
    ok += 1
    print('✓', nome)


D = R / 'ESTADO ATUAL — Diario de Bordo.md'
CX = R / 'Diário — caixa de entrada do Cowork.md'
ENTRADA = ('\n## ENTRADA\ncabecalho: **01/10/2026, 22h (Cowork, teste)** — entrou\n'
           'linha: | **01/10, 22h (Cowork, teste)** | entrou pela caixa |\n')
corpo = ('# Diário\n\n> Última atualização: **01/10/2026, noite (Claude Code, x)** — y\n>\n> Anterior: **30/09/2026** — z\n\n'
         '## Linha do tempo\n\n| Data | O que mudou |\n|---|---|\n| **01/10, noite (Claude Code, x)** | y |\n' + 'linha antiga\n' * 500)
w(D, corpo)
for n in ['CLAUDE.md', 'INFRA.md', 'ARQUITETURA — Como tudo se encaixa.md']:
    w(R / n, 'doc ' * 100)

r = run()
caso('1ª rodada: cria as cópias (git) e a caixa vazia', r.returncode == 0 and (C / '.git').exists() and CX.exists())

w(CX, r_(CX) + ENTRADA)
r = run()
d = r_(D)
caso('junta a linha no topo da tabela', '|---|---|\n| **01/10, 22h (Cowork, teste)** | entrou pela caixa |\n| **01/10, noite' in d)
caso('cabeçalho novo; o antigo desce para Anterior',
     '> Última atualização: **01/10/2026, 22h (Cowork, teste)** — entrou\n>\n> Anterior: **01/10/2026, noite' in d)
caso('a caixa volta vazia', 'entrou pela caixa' not in r_(CX))
caso('esvaziar a caixa não toca alarme (falso alarme de 02/10)', r.returncode == 0 and 'regrediu' not in r.stdout)
r2 = run()
caso('e a rodada seguinte segue limpa', r2.returncode == 0 and 'regrediu' not in r2.stdout)
caso('a quebra de linha continua LF', '\r' not in d and '\r' not in r_(CX))

w(CX, r_(CX) + ENTRADA)
run()
caso('caixa regravada com entrada velha não duplica', r_(D).count('entrou pela caixa') == 1)

boa = r_(D)
w(D, corpo.replace('01/10/2026, noite', '24/09/2026, noite'))
r = run()
caso('data voltou no tempo: alarme e código 2', r.returncode == 2 and 'voltou' in r.stdout)
caso('a cópia boa não foi sobrescrita', r_(C / 'ESTADO ATUAL — Diario de Bordo.md') == boa)
w(CX, r_(CX) + '\n## ENTRADA\nlinha: | **x** | não pode entrar com alarme |\n')
run()
caso('com alarme a caixa não é juntada', 'não pode entrar' not in r_(D))

subprocess.run([sys.executable, G, '--restaurar'], env=env, capture_output=True, text=True, encoding='utf-8')
caso('--restaurar devolve a cópia boa', r_(D) == boa)

w(D, boa[:len(boa) // 2])
r = run()
caso('encolheu mais de 5%: alarme', r.returncode == 2 and 'encolheu' in r.stdout)
r = run('--aceitar')
caso('--aceitar aceita a limpeza deliberada', r.returncode == 0)

shutil.rmtree(T, ignore_errors=True)
print(f'tudo certo · {ok} casos')
