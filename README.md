# django-nplus1-guard

[![CI](https://github.com/Rafaelcarvalho320/django-nplus1-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/Rafaelcarvalho320/django-nplus1-guard/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-4.2%20%7C%205.x-092E20)](https://www.djangoproject.com/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Encontra consultas N+1 no Django e **aponta a linha do seu código** que as
causou. Middleware para desenvolvimento, plugin de pytest para a CI.

> *[English summary below](#english-summary)*

## O problema

N+1 é o bug de performance mais comum do ORM e o mais fácil de não perceber.
Local, com 20 registros de teste, a página abre instantaneamente. Em produção,
com 20 mil, ela trava — e o código parece perfeitamente inocente:

```python
for author in Author.objects.all():          # 1 consulta
    print(author.publisher.name)             # + 1 consulta por autor
```

Você não vê o problema no código; vê no log de consultas. E ninguém lê o log de
consultas até alguém reclamar.

## O que ele mostra

Saída real de `python examples/demo.py`:

```console
=== before: the obvious implementation ===

N+1 report: catalogue_naive()
------------------------------------------------------------
  41 queries in 2.0 ms  (threshold: more than 5 of one shape)

  [1] 20x on `book` (1.1 ms total)
    from examples/demo.py:78 in catalogue_naive()
    SELECT "book"."id", "book"."title", "book"."author_id" FROM "book" WHERE ...

  [2] 20x on `publisher` (0.9 ms total)
    from examples/demo.py:79 in catalogue_naive()
    SELECT "publisher"."id", "publisher"."name" FROM "publisher" WHERE ...

  38 of the 41 queries look avoidable.
  Usual fix: select_related() for forward FK/one-to-one, prefetch_related() for
  reverse and many-to-many.


=== after: select_related + prefetch_related ===

N+1 report: catalogue_fixed()
------------------------------------------------------------
  2 queries in 0.3 ms  (threshold: more than 5 of one shape)
  no repeated query shapes


Same 20 lines of output, 41 queries down to 2 (39 fewer round trips).
```

O `from examples/demo.py:78` é o ponto inteiro do projeto. Saber que uma
consulta rodou 20 vezes é interessante; saber **de qual linha** ela saiu é o
que permite consertar.

## Instalação

```bash
pip install git+https://github.com/Rafaelcarvalho320/django-nplus1-guard.git
```

## Middleware

```python
# settings.py
MIDDLEWARE = [
    "nplus1_guard.middleware.NPlusOneMiddleware",   # o mais alto possível
    ...
]

NPLUS1_GUARD = {
    "THRESHOLD": 5,       # mais de 5 consultas da mesma forma é suspeito
    "RAISE": DEBUG,       # estoura local, só registra em log fora dali
}
```

Sem configuração nenhuma, ele **segue o `DEBUG`**: ligado em desenvolvimento,
desligado em produção. Um detector que roda em produção é um detector que
deixa a produção mais lenta.

Toda resposta ganha um header `X-NPlusOne-Queries` com a contagem, o que torna
o custo visível no devtools do navegador sem precisar abrir log nenhum.

## Pytest

Três granularidades, da mais estreita para a mais ampla:

```python
def test_um_bloco(assert_no_nplus1):
    with assert_no_nplus1(threshold=2):
        serializar(queryset)


@pytest.mark.nplus1(threshold=3)
def test_a_view_inteira(client):
    client.get("/pedidos/")
```

```bash
pytest --nplus1                 # falha qualquer teste com N+1
pytest --nplus1-report          # só lista os suspeitos, sem reprovar nada
pytest --nplus1-threshold 10
```

`--nplus1-report` é como você descobre o tamanho do problema **antes** de
ligar o portão:

```
================================ N+1 suspects =================================
    41x on `book` at views.py:78   tests/test_views.py::test_catalogo
    12x on `user` at serializers.py:31   tests/test_api.py::test_lista
```

E para provar que uma correção funcionou, o que é o teste de regressão que
normalmente ninguém escreve:

```python
def test_a_correcao_valeu(nplus1_report):
    with nplus1_report() as depois:
        listar_catalogo()
    assert depois[0].total_queries == 2
```

## Como funciona

```
  consulta executa
        │
        ├─ execute_wrapper do Django  ── funciona com DEBUG=False
        │
        ├─ fingerprint: literais viram ?, IN (...) colapsa
        │     WHERE author_id = 1  ─┐
        │     WHERE author_id = 2  ─┼─►  WHERE AUTHOR_ID = ?
        │     WHERE author_id = 3  ─┘
        │
        ├─ origem: sobe a pilha até sair de site-packages
        │
        └─ agrupa por forma; mais de N da mesma forma = suspeito
```

**Usa `connection.execute_wrapper`, não `connection.queries`.** O
`connection.queries` só é populado com `DEBUG=True` — ou seja, fica vazio
exatamente onde isso mais importa: nos testes e na CI. O `execute_wrapper` é o
hook suportado do Django e funciona nos dois casos.

**A origem é o diferencial.** No momento em que a consulta roda, a pilha é
quase toda Django. O detector sobe os quadros até encontrar o primeiro que não
é biblioteca e reporta esse — é a diferença entre "20 consultas em `book`" e
"20 consultas em `book`, vindas de `views.py:78`".

## Decisões de projeto

**A heurística é deliberadamente burra.** Agrupa por forma e conta. Sem
aprendizado, sem pontuação de confiança, sem exceções espertas. Um detector com
heurística complicada é um detector em que ninguém confia quando ele fica
quieto.

**O limiar é "mais que N", não "N ou mais".** Ou seja, `THRESHOLD: 5` permite
exatamente 5 consultas da mesma forma. Um limite que você pode encostar sem
disparar é mais fácil de calibrar.

**Um teste que já falhou não recebe relatório de N+1 por cima.** Se o teste
levanta exceção, a verificação nem roda. Empilhar um relatório de performance
sobre o erro real só enterraria o erro real.

**Instruções de transação não contam.** `BEGIN`, `COMMIT`, `SAVEPOINT` e
`PRAGMA` são executadas normalmente, mas não entram na contagem de formas — do
contrário todo teste com transação pareceria um N+1.

**Dígito dentro de identificador é preservado.** Se `address2` virasse
`address?`, colidiria com a coluna `address` e duas consultas diferentes
viraram uma forma só. O regex de números só apaga números isolados.

**O rótulo da tabela sai de um regex, não de um parser de SQL.** Errar o rótulo
numa instrução exótica custa um relatório um pouco pior; adicionar uma
dependência de parser a uma ferramenta de desenvolvimento custa para sempre,
para todo mundo que instalar.

## Configuração

| Chave | Padrão | O quê |
| --- | --- | --- |
| `ENABLED` | segue `DEBUG` | Liga o middleware |
| `THRESHOLD` | `5` | Mais que isso da mesma forma é suspeito |
| `RAISE` | `False` | Estourar em vez de registrar em log |
| `LOG_LEVEL` | `WARNING` | Nível do log quando não estoura |
| `IGNORE_PATHS` | `[]` | Regexes de caminhos a ignorar |
| `IGNORE_TABLES` | `[]` | Tabelas cujo acesso por linha é aceitável |
| `HEADER` | `True` | Header `X-NPlusOne-Queries` na resposta |

## Desenvolvimento

```bash
python -m venv .venv && source .venv/Scripts/activate   # Linux/macOS: .venv/bin/activate
pip install -e ".[dev]"

pytest                  # 81 testes
ruff check . && ruff format --check .
mypy                    # strict, com django-stubs
python examples/demo.py
```

```
src/nplus1_guard/
    fingerprint.py     reduz SQL à sua forma
    origin.py          sobe a pilha até o seu código
    recorder.py        captura via execute_wrapper
    report.py          agrupa, ordena e redige
    conf.py            settings
    middleware.py      vigia requisições
    pytest_plugin.py   marker, opções de linha de comando e fixtures
tests/                 81 testes, incluindo execuções aninhadas de pytest
examples/demo.py       antes e depois, executável
```

Os testes do plugin rodam um **pytest dentro do pytest**: a coisa sob teste é
"a execução falha?", que não dá para verificar de dentro da execução que está
sendo testada.

## English summary

Finds N+1 queries in Django and **points at the line of your code** that caused
them. A middleware for development and a pytest plugin for CI.

- Built on `connection.execute_wrapper`, not `connection.queries`, so it works
  with `DEBUG = False` — which is exactly where it matters, in tests and CI.
- **Locating the origin is the point.** At the moment a query runs the stack is
  almost all Django; the detector walks out to the first frame that is not
  library code. "20 queries on `book`" is interesting; "20 queries on `book`,
  from `views.py:78`" is actionable.
- Queries are grouped by **fingerprint**: literals become `?` and `IN (...)`
  collapses, so the same statement with different ids is one shape.
- The heuristic is deliberately dumb — group and count. A detector with clever
  heuristics is one nobody trusts when it stays silent.
- A test that already failed never gets an N+1 report stacked on top of it.
- Off unless `DEBUG`, because a detector running in production is a detector
  slowing production down.

Code and docstrings are in English; the sections above are in Portuguese.

## Licença

MIT. Veja [LICENSE](LICENSE).
