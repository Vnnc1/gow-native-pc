# Ponto de retomada — desempenho, combate e áudio

Trabalho pausado a pedido do usuário em **04/11/2026**. Não iniciar testes ou
compilações automaticamente. [Contexto técnico completo e rascunhos](resume-checkpoint.md).

## O que está pronto

- O jogo instalado continua na versão validada até o patch 71. As opções
  experimentais 66/67/68/71 continuam desligadas por padrão.
- A cena curta de chegada ao navio já pode ser comparada por frames, com métricas
  de intervalos e áudio. Isso ainda não resolve a comparação do combate prolongado.
- Os testes anteriores dessa versão passaram, incluindo 13 grupos CTest e
  equivalência da VU1. Não significam validação das novas experiências.
- Os testes desta etapa usaram cartões privados e confirmaram os saves originais
  intactos. Não ficou jogo de teste ou amostrador rodando ao pausar.

## Última descoberta

O custo da VU1 continua concentrado no encadeamento dos blocos e na atualização de
seu histórico. Uma nova candidata retira as rotinas de agendamento escalar do
corpo principal desse encadeamento, preservando os cálculos e a ordem de execução.

Em cinco pares com as mesmas 32 tarefas capturadas, o custo mediano agregado caiu
de **561,8 para 507,8 microssegundos: redução de 9,61%**. Todos os pares favoreceram
a candidata e os resultados das tarefas permaneceram iguais aos de referência.

**Esse resultado é de CPU em replay isolado com JIT. Não representa 9,61% mais FPS
no jogo.** Ainda faltam testes de equivalência mais amplos, compilação completa e
comparação no combate. A candidata não foi instalada nem ativada. O código ativo
foi restaurado e a alteração ficou guardada em um rascunho separado.

## O que ainda falha

| Problema ou limitação | Próximo trabalho |
|---|---|
| O combate diverge entre execuções | Criar um marco no início efetivo do encontro, depois da chegada; verificar posição, estado, zona e inimigos ativos. |
| O teste para o canto do navio foi rejeitado | Manter o registro da falha; não aumentar a tolerância para fazê-lo passar. |
| Oscilações e áudio ruim em sessões longas | Reproduzir e correlacionar intervalos longos, produção de áudio, consumo pelo dispositivo e IOP. |
| GPU perto de 99% | Separar pressão de GPU de CPU, espera de driver e limites térmicos; uso alto sozinho não identifica a causa. |
| A otimização escalar só passou no replay pequeno | Repetir medições e validar todos os caminhos antes de promover. |

Ainda não comprovamos 60 FPS estáveis neste notebook, correção do áudio no combate
ou redução de consumo de energia. O comparativo anterior da opção do patch 71
teve apenas +0,68% de FPS e piora no p95, por isso permaneceu desligada.

## Como continuar com outra IA

Forneça primeiro o [checkpoint técnico](resume-checkpoint.md), o `AGENTS.md` e o
[ROADMAP](../roadmap-2026-10-27.md). Há rascunhos separados para a candidata escalar
e para o marco do encontro; o segundo está incompleto e nunca foi compilado.

Pedidos úteis e delimitados:

1. **Revisão da VU1:** “Revise o rascunho `vu1-scalar-outline.patch`, verifique a
   equivalência do agendamento escalar, repita os replays e apresente evidências
   antes de propor sua integração. Não converta ganho de replay em ganho de FPS.”
2. **Teste de combate:** “Complete e teste o marco de encontro descrito no
   checkpoint. Preserve relógio, física e IA; exija execuções equivalentes e
   rejeite cenas divergentes. Use cartões privados e capturas separadas das
   medições de desempenho.”
3. **Áudio:** “Investigue a origem da falta de amostras no combate usando logs
   sincronizados. Diferencie falha de produção, atraso de IOP e atraso de consumo;
   não aumente buffers apenas para esconder o problema.”
4. **GPU e oscilação:** “Com uma cena validada, compare resolução e tempos de
   trabalho/espera. Registre carga concorrente e, quando disponível, clocks e
   temperatura. Não altere o plano de energia nem encerre outros programas.”

Peça sempre: arquivos alterados, reprodução exata, testes executados, resultados
brutos e limitações. Não execute compilações ou benchmarks de várias IAs ao mesmo
tempo neste notebook. Os arquivos de jogo, capturas e corpus devem permanecer
locais; não são necessários para compartilhar este resumo ou os rascunhos de código.

## Onde tudo ficou

- [Checkpoint completo, estado da instalação e sequência de retomada](resume-checkpoint.md).
- [Rascunho da otimização escalar](drafts/vu1-scalar-outline.patch).
- [Rascunho incompleto do marco do encontro](drafts/encounter-anchor-incomplete.patch).
- Evidências locais: `data/vu1-combat-followup/`.
- O executável normal permanece em `C:/gow-build-clang/ps2xRuntime/ps2EntryRunner.exe`.

O diretório de compilação dos testes contém um binário experimental: reconstruí-lo
antes de usá-lo como referência. As cópias de referência e candidata já medidas
estão preservadas no diretório de evidências. Não sobrescrevê-las.
