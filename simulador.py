#!/usr/bin/env python3
"""Simulador de redes de filas baseado em eventos discretos.

Simula um modelo com qualquer topologia de rede de filas G/G/c/K, descrito em
um arquivo .yml no mesmo estilo do simulador de referência da disciplina
(módulo 3).

Uso:
    python simulador.py modelo.yml
"""
import heapq
import sys

CHEGADA = "chegada"
SAIDA = "saida"


# ---------------------------------------------------------------------------
# Números pseudoaleatórios
# ---------------------------------------------------------------------------

class AleatoriosEsgotados(Exception):
    """Pedido de um número pseudoaleatório além da quantidade disponível."""


class GeradorCongruenteLinear:
    """Método congruente linear: x(i+1) = (a * x(i) + c) mod M."""

    A = 25214903917
    C = 11
    M = 2 ** 48

    def __init__(self, semente, limite):
        self.x = semente
        self.limite = limite
        self.usados = 0

    def tem_proximo(self):
        return self.usados < self.limite

    def proximo(self):
        if not self.tem_proximo():
            raise AleatoriosEsgotados()
        self.x = (self.A * self.x + self.C) % self.M
        self.usados += 1
        return self.x / self.M


class GeradorEmLista:
    """Consome uma lista de números pseudoaleatórios informada no modelo."""

    def __init__(self, numeros):
        self.numeros = numeros
        self.usados = 0

    def tem_proximo(self):
        return self.usados < len(self.numeros)

    def proximo(self):
        if not self.tem_proximo():
            raise AleatoriosEsgotados()
        numero = self.numeros[self.usados]
        self.usados += 1
        return numero


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

class Fila:
    def __init__(self, nome, servidores, capacidade=None,
                 chegada_min=None, chegada_max=None,
                 atendimento_min=0.0, atendimento_max=0.0):
        self.nome = nome
        self.servidores = servidores
        self.capacidade = capacidade  # None = capacidade infinita
        self.chegada_min = chegada_min
        self.chegada_max = chegada_max
        self.atendimento_min = atendimento_min
        self.atendimento_max = atendimento_max
        self.destinos = []  # [(Fila, probabilidade)]; o que falta para 1.0 sai do sistema
        self.populacao = 0
        self.perdas = 0
        self.tempos = {}  # estado (clientes na fila) -> tempo acumulado

    def notacao(self):
        notacao = "G/G/%d" % self.servidores
        if self.capacidade is not None:
            notacao += "/%d" % self.capacidade
        return notacao

    def adiciona_destino(self, fila, probabilidade):
        self.destinos.append((fila, probabilidade))
        # As faixas de roteamento seguem a ordem crescente de probabilidade,
        # como no simulador de referência (a ordenação é estável).
        self.destinos.sort(key=lambda destino: destino[1])


class Simulador:
    def __init__(self):
        self.filas = {}
        self.chegadas_iniciais = []  # [(Fila, tempo)]
        self.eventos = []
        self.sequencia = 0
        self.tempo = 0.0
        self.tempo_anterior = 0.0
        self.aleatorio = None

    # -- escalonador --------------------------------------------------------

    def agenda(self, tempo, tipo, fila, destino=None):
        # A sequência desempata eventos de mesmo tempo pela ordem de agendamento.
        self.sequencia += 1
        heapq.heappush(self.eventos, (tempo, self.sequencia, tipo, fila, destino))

    def sorteia(self, minimo, maximo):
        return (maximo - minimo) * self.aleatorio.proximo() + minimo

    def agenda_chegada(self, fila):
        self.agenda(self.tempo + self.sorteia(fila.chegada_min, fila.chegada_max),
                    CHEGADA, fila)

    def agenda_saida(self, fila):
        # O destino é sorteado antes do tempo de atendimento.
        destino = self.sorteia_destino(fila)
        self.agenda(self.tempo + self.sorteia(fila.atendimento_min, fila.atendimento_max),
                    SAIDA, fila, destino)

    def sorteia_destino(self, fila):
        """Devolve a fila de destino do cliente, ou None se ele sai do sistema."""
        if not fila.destinos:
            return None
        if len(fila.destinos) == 1 and fila.destinos[0][1] >= 1.0:
            return fila.destinos[0][0]
        sorteado = self.aleatorio.proximo()
        for destino, probabilidade in fila.destinos:
            if sorteado <= probabilidade:
                return destino
            sorteado -= probabilidade
        return None

    # -- eventos ------------------------------------------------------------

    def contabiliza_tempo(self):
        delta = self.tempo - self.tempo_anterior
        for fila in self.filas.values():
            fila.tempos[fila.populacao] = fila.tempos.get(fila.populacao, 0.0) + delta
        self.tempo_anterior = self.tempo

    def chegada(self, fila, do_exterior):
        self.contabiliza_tempo()
        if fila.capacidade is None or fila.populacao < fila.capacidade:
            fila.populacao += 1
            if fila.populacao <= fila.servidores:
                self.agenda_saida(fila)
        else:
            fila.perdas += 1
        if do_exterior:
            self.agenda_chegada(fila)

    def saida(self, fila):
        self.contabiliza_tempo()
        fila.populacao -= 1
        if fila.populacao >= fila.servidores:
            self.agenda_saida(fila)

    def passo(self):
        tempo, _, tipo, fila, destino = heapq.heappop(self.eventos)
        self.tempo_anterior = self.tempo
        self.tempo = tempo
        if tipo == CHEGADA:
            self.chegada(fila, True)
        else:
            self.saida(fila)
            if destino is not None:  # passagem: o cliente chega na fila de destino
                self.chegada(destino, False)

    def executa(self, aleatorio):
        """Simula até o último número pseudoaleatório ser utilizado.

        Devolve o tempo global da simulação.
        """
        self.aleatorio = aleatorio
        self.eventos = []
        self.tempo = 0.0
        self.tempo_anterior = 0.0
        for fila in self.filas.values():
            fila.populacao = 0
        for fila, tempo in self.chegadas_iniciais:
            self.agenda(tempo, CHEGADA, fila)
        try:
            while self.eventos and aleatorio.tem_proximo():
                self.passo()
        except AleatoriosEsgotados:
            pass
        return self.tempo


# ---------------------------------------------------------------------------
# Leitura do modelo (.yml)
# ---------------------------------------------------------------------------

class ErroDeModelo(Exception):
    pass


def _escalar(texto):
    texto = texto.strip()
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in "'\"":
        return texto[1:-1]
    for conversor in (int, float):
        try:
            return conversor(texto)
        except ValueError:
            pass
    return texto


def _linhas(texto):
    linhas = []
    for bruta in texto.splitlines():
        linha = bruta.split("#", 1)[0].rstrip().replace("\t", "    ")
        if not linha.strip() or linha.lstrip().startswith(("!", "---")):
            continue
        linhas.append((len(linha) - len(linha.lstrip()), linha.strip()))
    return linhas


def _bloco(linhas, i, recuo):
    """Lê o mapeamento ou a lista que começa em linhas[i] com o recuo dado."""
    if linhas[i][1].startswith("-"):
        lista = []
        while i < len(linhas) and linhas[i][0] == recuo and linhas[i][1].startswith("-"):
            conteudo = linhas[i][1][1:].lstrip()
            if ":" in conteudo:
                # item que é um mapeamento: suas chaves se alinham após o "-"
                recuo_item = recuo + len(linhas[i][1]) - len(conteudo)
                linhas[i] = (recuo_item, conteudo)
                item, i = _bloco(linhas, i, recuo_item)
            else:
                item, i = _escalar(conteudo), i + 1
            lista.append(item)
        return lista, i

    mapa = {}
    while i < len(linhas) and linhas[i][0] == recuo and not linhas[i][1].startswith("-"):
        if ":" not in linhas[i][1]:
            raise ErroDeModelo("linha inválida no modelo: '%s'" % linhas[i][1])
        chave, valor = linhas[i][1].split(":", 1)
        chave = chave.strip()
        i += 1
        if valor.strip():
            mapa[chave] = _escalar(valor)
        elif i < len(linhas) and (linhas[i][0] > recuo or
                                  (linhas[i][0] == recuo and linhas[i][1].startswith("-"))):
            mapa[chave], i = _bloco(linhas, i, linhas[i][0])
        else:
            mapa[chave] = None
    return mapa, i


def le_yml(caminho):
    with open(caminho, encoding="utf-8-sig") as arquivo:
        linhas = _linhas(arquivo.read())
    if not linhas:
        raise ErroDeModelo("o arquivo de modelo está vazio")
    dados, _ = _bloco(linhas, 0, linhas[0][0])
    return dados


def monta_simulador(dados):
    simulador = Simulador()

    filas = dados.get("queues") or {}
    if not filas:
        raise ErroDeModelo("o modelo não declara nenhuma fila em 'queues'")
    for nome, parametros in filas.items():
        parametros = parametros or {}
        for obrigatorio in ("servers", "minService", "maxService"):
            if obrigatorio not in parametros:
                raise ErroDeModelo("fila %s: falta o parâmetro '%s'" % (nome, obrigatorio))
        simulador.filas[nome] = Fila(
            nome,
            servidores=parametros["servers"],
            capacidade=parametros.get("capacity"),
            chegada_min=parametros.get("minArrival"),
            chegada_max=parametros.get("maxArrival"),
            atendimento_min=parametros["minService"],
            atendimento_max=parametros["maxService"],
        )

    def fila(nome):
        if nome not in simulador.filas:
            raise ErroDeModelo("a fila '%s' não foi declarada em 'queues'" % nome)
        return simulador.filas[nome]

    for rota in dados.get("network") or []:
        fila(rota["source"]).adiciona_destino(fila(rota["target"]), rota["probability"])
    for origem in simulador.filas.values():
        total = sum(probabilidade for _, probabilidade in origem.destinos)
        if total > 1.0 + 1e-9:
            raise ErroDeModelo("fila %s: as probabilidades de roteamento somam %g (> 1)"
                               % (origem.nome, total))

    for nome, tempo in (dados.get("arrivals") or {}).items():
        destino = fila(nome)
        if destino.chegada_min is None or destino.chegada_max is None:
            raise ErroDeModelo("fila %s: recebe chegadas do exterior, mas não define "
                               "'minArrival' e 'maxArrival'" % nome)
        simulador.chegadas_iniciais.append((destino, tempo))
    if not simulador.chegadas_iniciais:
        raise ErroDeModelo("o modelo não declara nenhuma chegada inicial em 'arrivals'")

    return simulador


def monta_geradores(dados):
    """Devolve [(descrição, gerador)], um por execução da simulação."""
    sementes = dados.get("seeds")
    if sementes:
        quantidade = dados.get("rndnumbersPerSeed")
        if not quantidade:
            raise ErroDeModelo("'seeds' exige o parâmetro 'rndnumbersPerSeed'")
        return [("semente %s, %d aleatórios" % (semente, quantidade),
                 GeradorCongruenteLinear(semente, quantidade)) for semente in sementes]
    numeros = dados.get("rndnumbers")
    if numeros:
        return [("lista de %d aleatórios do modelo" % len(numeros), GeradorEmLista(numeros))]
    raise ErroDeModelo("o modelo deve informar 'seeds' ou 'rndnumbers'")


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------

def imprime_relatorio(simulador, execucoes, tempo_total):
    barra = "=" * 62
    print(barra)
    print("RELATÓRIO DA SIMULAÇÃO")
    if execucoes > 1:
        print("(valores médios de %d execuções)" % execucoes)
    print(barra)
    for fila in simulador.filas.values():
        print()
        print("Fila %s (%s)" % (fila.nome, fila.notacao()))
        if fila.chegada_min is not None:
            print("  Chegadas:    %g .. %g" % (fila.chegada_min, fila.chegada_max))
        print("  Atendimento: %g .. %g" % (fila.atendimento_min, fila.atendimento_max))
        print("  %6s %20s %16s" % ("Estado", "Tempo acumulado", "Probabilidade"))
        total = sum(fila.tempos.values())
        for estado in sorted(fila.tempos):
            tempo = fila.tempos[estado]
            print("  %6d %20.4f %15.2f%%" % (estado, tempo / execucoes,
                                             100.0 * tempo / total if total else 0.0))
        print("  Clientes perdidos: %g" % (fila.perdas / execucoes))
    print()
    print(barra)
    print("Tempo global da simulação: %.4f" % (tempo_total / execucoes))
    print(barra)


def main(argumentos):
    if len(argumentos) != 2:
        print(__doc__)
        return 2
    try:
        dados = le_yml(argumentos[1])
        simulador = monta_simulador(dados)
        geradores = monta_geradores(dados)
    except FileNotFoundError:
        print("ERRO: arquivo '%s' não encontrado" % argumentos[1])
        return 1
    except ErroDeModelo as erro:
        print("ERRO: %s" % erro)
        return 1

    tempo_total = 0.0
    for numero, (descricao, gerador) in enumerate(geradores, 1):
        print("Execução %d: %s" % (numero, descricao))
        tempo_total += simulador.executa(gerador)
    print()
    imprime_relatorio(simulador, len(geradores), tempo_total)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv))
