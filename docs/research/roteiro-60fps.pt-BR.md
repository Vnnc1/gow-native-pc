# Roteiro para 60 FPS travados no combate

Documento vivo: o que falta, em que ordem, e como medir. Base: Xeon E5-2666 v3 + RX 580, rota do save, tela cheia,
2× de resolução interna, Early FINISH ligado. Medições e motivos detalhados em
[`revisao-2026-10-30.pt-BR.md`](revisao-2026-10-30.pt-BR.md) (seções 6, 8, 9 e 10).

## Onde estamos (2026-10-31, branch `feature/vu1-static-timing`)

- Média da rota ~57 FPS, combate ~55 FPS (patch 43).
- O gargalo é **um thread**: o worker VIF1/VU1, 100% ocupado no combate. ~78% dele é execução dos programas da VU1,
  ~12–15% envio de pacotes ao estágio GS, o resto unpack do VIF.
- Para 60 travados no combate faltam **~9%** de throughput no worker.

## Como medir (sempre)

1. **Bancada de replay** (tempo puro da VU1, bit a bit): gravar uma vez
   `GOW_VU1N_RECORD=<arquivo> GOW_VU1N_RECORD_N=4000 GOW_VU1N_RECORD_STRIDE=101 GOW_VU1N_RECORD_SKIP=3000000` na rota
   do save (arquivo local: é dado do jogo, nunca versionar) e reexecutar com `GOW_VU1N_REPLAY=<arquivo>
   GOW_VU1N_REPLAY_REPS=6`. Exigir `0 differ` e comparar medianas de rodadas alternadas.
2. **FPS em jogo**: pares alternados A/B (mínimo 3, de preferência 4) do mesmo save, mesmo roteiro de controle,
   tela cheia. Ruído entre execuções de ±3–5 FPS; só pares alternados valem.
3. **Equivalência**: `build.cmd -Stages fetch,verify` (inclui a equivalência do backend VU1 contra o motor exato).

## Fase 1 — patches exatos, incrementais (em andamento)

Cada um é um patch numerado em `engine/patches/`, medido sozinho antes de entrar.

| Patch | O quê | Teto / ganho medido | Situação |
|---|---|---|---|
| 43 | Código VU1 gerado mais enxuto (normalização barata, sem clamp redundante, operandos/ACC em locais) | VU1 −8,6%; FPS +11% (combate +8%) | **feito** |
| 44 | Fila em anel sem lock entre o worker e o estágio GS (acorda a thread do estágio só quando ela dorme) | corta ~150 mil trocas de contexto/s; sobre o 43: combate 52,8 → 54,7 FPS (+3,5%, 4 de 4 pares). Antes do 43 dava empate (o envio pesava menos). Falta medir numa CPU de 6 núcleos | **feito** |
| 45 | Transições entre blocos (`VU1NativeAccess::chain`) | medido direto (`rdtsc` em 1 de cada 64 chamadas): ~10–11 ns por transição, ~18 milhões/s, **~20% do worker**. Testado e descartado: tirar de linha os casos raros (`blockTiming`, `scalarStart`) — neutro; convenção `preserve_none` (sem salvar registradores) — **pior** (+7% sem PGO, +11% com PGO). O custo não está no prólogo, e sim no trabalho por transição | **a repensar**: reduzir o número de transições (traços/superblocos no gerador) |
| 46 | Envio de pacotes (XGKICK → estágio GS): cópia e cabeçalhos por pacote | parte dos ~12–15% do worker | a medir |
| 47 | Sobras de normalização: dados lidos da memória da VU usados como operandos | teto de normalização restante (~7%) | a estudar |

Descartados (medidos, não vale): timing estático completo da VU1 (teto ~5%, dias de trabalho no gerador); AVX2 no
código da VU1 (0%); checagem de overflow do `madd` mais barata (nenhuma forma exata mais barata que as 5 operações
atuais); lote de pacotes para o estágio GS (pior, perde sobreposição).

Notas de medição desta fase: o PGO sozinho vale ~9% na VU1 (replay 151,7 ms sem perfil vs ~138 ms com). Toda mudança
que move o corpo de uma função quente (novo nome, nova forma) perde o perfil no build de teste e parece pior do que é;
compare sem PGO nos dois lados (pasta de build sem `-fprofile-instr-use`) ou retreine o perfil.

## Fase 2 — modo "VU rápida" (opcional, depois da fase 1)

O PCSX2 roda a 60 porque, por padrão, não é exato: aproxima arredondamento, clamp, flags e timing da VU. O custo de
cada exatidão aqui (replay, sem a verificação):

| Exatidão | Custo na VU1 |
|---|---|
| Normalização de operandos (Inf/NaN → ±FLT_MAX) | até 13% |
| Checagem de overflow do `madd` (caminho largo em double) | 9,5% |
| Timing ciclo a ciclo e histórico | ~5,5% |
| Clamp | resolvido no 43 |

Plano: uma opção no launcher ("VU rápida", padrão desligado até validar) que gera uma segunda variante de cada bloco
sem normalização e sem a checagem do `madd`, e usa timing ocioso. Validar por comparação de capturas de tela
(`GOW_PAD_CAPTURAS`, `GOW_HOST_SHOT`) nas áreas do jogo contra o modo exato, e pelo menos uma sessão longa. Ganho
esperado: ~20–25% da VU1, o suficiente para passar de 60 no combate nesta máquina. Risco: defeito visual raro onde
o jogo dependa de Inf/NaN ou de overflow (por isso opcional e com o modo exato sempre disponível).

## Fase 3 — longo prazo

- Paralelismo da VU1 (hoje um worker roda todo o quadro; cada programa depende do estado do anterior).
- Medir em outras CPUs (Ryzen 5 5500 de 6 núcleos já em teste de instalação; CPUs mais rápidas por núcleo devem
  chegar perto de 60 com o que existe).
