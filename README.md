# Simulador de Rede de Filas

T1 da disciplina Simulação e Métodos Analíticos (4611G-04, PUCRS, 2026/2).

Simulador baseado em eventos discretos para redes de filas G/G/c/K com
qualquer topologia. O modelo é lido de um arquivo `.yml` no mesmo formato do
simulador de referência do módulo 3 (`simulator.jar`).

Autor: Marcus Margarites F.

## Como executar

Requer apenas Python 3.8 ou superior (não usa bibliotecas externas).

```
python simulador.py modelo_t1.yml
```

O relatório é impresso na saída padrão. Para guardar em arquivo:

```
python simulador.py modelo_t1.yml > resultado_t1.txt
```

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `simulador.py` | Código-fonte do simulador |
| `modelo_t1.yml` | Modelo de validação pedido no T1 |
| `resultado_t1.txt` | Resultado da simulação de `modelo_t1.yml` |

## Formato do modelo

```yaml
!PARAMETERS
arrivals:            # tempo da primeira chegada do exterior em cada fila
   Q1: 2.0

queues:
   Q1:
      servers: 1          # número de servidores
      capacity: 5         # capacidade da fila; omitir para capacidade infinita
      minArrival: 2.0     # intervalo entre chegadas do exterior (só para filas em 'arrivals')
      maxArrival: 4.0
      minService: 1.0     # tempo de atendimento
      maxService: 2.0

network:             # roteamento entre filas
-  source: Q1
   target: Q2
   probability: 0.2

rndnumbersPerSeed: 100000   # quantidade de aleatórios por execução
seeds:                      # uma execução por semente
- 1
```

- O que falta para as probabilidades de saída de uma fila somarem 1.0 é a
  probabilidade de o cliente sair do sistema. Uma fila sem rotas sempre envia
  o cliente para o exterior.
- Em vez de `seeds` e `rndnumbersPerSeed`, pode-se informar em `rndnumbers` a
  lista de números pseudoaleatórios a utilizar. Se `seeds` estiver presente,
  `rndnumbers` é ignorado.
- Com mais de uma semente, o relatório mostra a média das execuções.

## Funcionamento

- As filas começam vazias e a simulação começa com as chegadas de `arrivals`,
  que não consomem número pseudoaleatório.
- A simulação termina quando o último número pseudoaleatório é utilizado. O
  evento em andamento é concluído até onde não precise de outro número.
- Os números são gerados pelo método congruente linear
  `x = (25214903917 * x + 11) mod 2^48`, normalizados por `2^48`.
- Ao iniciar um atendimento, sorteia-se primeiro o destino do cliente e depois
  o tempo de atendimento. Não há sorteio de destino quando a fila não tem
  rotas ou tem uma única rota com probabilidade 1.0.
- As faixas de roteamento são montadas em ordem crescente de probabilidade,
  com o exterior por último.
- Um cliente roteado para uma fila cheia é perdido e contado nas perdas da
  fila de destino.
- Eventos agendados para o mesmo instante são tratados na ordem em que foram
  agendados.

Essas regras são as mesmas do simulador de referência do módulo 3. Com a mesma
semente e a mesma quantidade de aleatórios, os dois simuladores produzem os
mesmos tempos acumulados, probabilidades, perdas e tempo global.
