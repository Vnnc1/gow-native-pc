# Launcher e recompilação: fluxo atual e o que melhorar (2026-10-31)

Levantamento feito depois da v3.0.1, com os tempos reais da instalação nova do `gow-test` (Xeon E5-2666 v3, 20 threads,
`data/gow1/logs/pipeline-20261031-044501-037.json`) e a leitura de `launcher/qml` e `tools/pipeline`.

## 1. Mapa do launcher

| Página | O que faz | Observações |
|---|---|---|
| Início | Capa, JOGAR, idioma do jogo, cartões (perfil, imagem, controles, tempo), aviso "PGO recomendado" | O aviso leva à página Instalação; o jogador ainda precisa abrir "Mais opções" e achar o PGO |
| Instalação | 3 passos (ferramentas → ISO → instalar e compilar), aviso de recompilar após update, "Mais opções" com 6 ações de manutenção | As ações de manutenção usam nomes técnicos (nativo, rápido, VU1 do disco, PGO, runtime) |
| Gráficos | Perfis rápidos, resolução, escala, filtro, FXAA, VSync, limite de FPS | — |
| Desempenho | Contador de FPS, Early FINISH, **VU rápida (patch 51, novo)**, compilação automática | — |
| Controles, Truques, Partidas, Outros | Mapeamento, trapaças, saves, relatórios | — |

Fluxos:

- **Instalação nova:** `tools,fetch,discs,configure,recomp,sync,tune` (ou `build,optimize` em CPUs de até 4 threads).
- **Atualização do launcher:** `update.ps1` grava `needs-rebuild.txt` e `pgo-stale.txt`. A Instalação mostra "Recompilar o
  jogo" (`…,sync,build`, uma build `-O3` completa) e depois o Início recomenda o PGO (`pgo`: build instrumentada, o jogo
  rodando sozinho, outra build completa). **Três compilações completas** do jogo para aplicar um update.

### Feito nesta sessão

- O botão de recompilar após um update passa a rodar `…,sync,tune` em CPUs com mais de 4 threads: a build com o runtime
  novo e o perfil retreinado na mesma passada, **duas** compilações em vez de três (~11 min a menos aqui, mais numa CPU
  menor). CPUs de até 4 threads mantêm a build simples, como na instalação. Texto do aviso atualizado nos 4 idiomas.
- Opção "VU rápida (experimental)" em Desempenho, desligada por padrão; o modo vai nos relatórios de sessão.

### Propostas (não feitas)

1. **Um clique para o PGO no Início**: o aviso "PGO recomendado" pode rodar a etapa direto (com a duração estimada) em vez
   de mandar o jogador procurar em "Mais opções".
2. **"Mais opções" em linguagem de jogador**: agrupar em "Otimizar de novo" (PGO), "Acelerar áreas visitadas" (native),
   "Reparar instalação" (runtime + rebuild); esconder `sync,build` e "VU1 do disco" atrás de um "Avançado".
3. **Estimativa de tempo antes de começar**, a partir de `cpuThreads()` e dos tempos medidos por etapa (os JSON de
   `data/gow1/logs/pipeline-*.json` já têm tudo).

## 2. Tempo de recompilação

Instalação nova no `gow-test` (20 threads): **30 min**.

| Etapa | Tempo | Natureza |
|---|---|---|
| runtime (fetch) | 57 s | download + aplicar patches |
| discs | 23 s | — |
| configure | **197 s** | clone das dependências + testes do compilador + CMake (reconfigurar uma pasta pronta: 28 s) |
| recompile (MIPS → C++) | 81 s | — |
| sync | 33 s | — |
| build instrumentada (PGO) | **508 s** | configure próprio (~70 s) + ~6.400 arquivos em `-O3` com instrumentação |
| o jogo roda sozinho | 245 s | perfil + microcódigo da VU1 |
| rebuild com o perfil | **664 s** | ~6.400 arquivos em `-O3` |

As duas compilações completas são 65% do total. Já descartado (medido): treino do PGO em `-O1` (compila 2,2× mais rápido,
mas o jogo final ficou mais lento, 45,0 vs 49,7 FPS). Também **não recomendado**: compilar em `-O1` o código que o perfil
não viu, porque o perfil cobre só o navio inicial e as fases seguintes ficariam mais lentas.

Propostas, da maior para a menor:

1. **Distribuir o perfil do PGO com cada release** — **implementado** (`Use-ReleaseProfile` em `tools/pipeline/modules/game.ps1`,
   estágio `package`, regras no `AGENTS.md`). O pacote leva `games/<id>/pgo/shipped.profdata` (+7 MB no zip) com um
   manifesto de identidade: `engine/runtime.toml`, conjunto de patches em ordem ordinal, arquivos de `games/<id>` e o
   SHA-256 do `.text` do ELF recompilado (o `.text` da tradução PT-BR é idêntico byte a byte ao americano; só `.data` e
   `.rodata` mudam). O `package` recusa um perfil sem manifesto correspondente (`-NoReleaseProfile` para empacotar sem).
   **Medido** (instalação do zero a partir do pacote, ISO PT-BR, mesmas etapas do launcher): **24,6 min contra 30,1 min**.
   O perfil foi reconhecido, a build saiu com `-fprofile-instr-use`, e o jogo chega ao gameplay.

   | Etapa | Antes | Com o perfil da release |
   |---|---|---|
   | build instrumentada + treino de 4 min | 12,6 min | — |
   | build com o perfil | 11,1 min | 8,1 min |
   | gravação da VU1 (o jogo roda sozinho) | (junto do treino) | 4,1 min |
   | código nativo da VU1/IOP + rebuild | — | 4,8 min |

   Próximo ganho possível: gravar o microcódigo da VU1 a partir do disco (etapa `vu1disc`) antes da build, em vez de
   rodar o jogo depois dela, eliminaria a gravação e o segundo rebuild (~9 min), se a varredura do disco cobrir o mesmo
   microcódigo. Proposta original: O código recompilado é o mesmo para todos (mesmo
   ELF americano, mesma versão do recompilador e dos patches), então o perfil treinado por nós vale para todo mundo.
   A instalação faria **uma** build com o perfil e não a instrumentada nem o treino: ~30 → ~17–22 min aqui, e as CPUs de
   até 4 threads ganham o PGO sem a hora extra. O microcódigo da VU1 continua vindo da máquina do jogador (o jogo rodando
   sozinho na build final, ou a etapa "VU1 do disco"). O arquivo `.profdata` tem nomes de funções e contadores, não código
   do jogo; mesmo assim, a regra do projeto de não publicar nada derivado do jogo precisa ser avaliada antes.
2. **Atualizações: `tune` direto** (feito acima): −1 build completa por update.
3. **Testes do compilador pré-preenchidos**: o toolchain é fixo (llvm-mingw 20261020), então os resultados dos testes
   de flags do CMake (`Testing if -Werror=… can be used`) podem ir num cache inicial (`-C`), poupando parte dos ~70 s em
   cada pasta nova (principal e a do PGO).
4. **Fontes das dependências compartilhadas entre cópias** (`data/_deps-src`), para uma instalação nova não clonar de
   novo o que outra cópia já baixou (~1 min e menos falha de rede).

A VU rápida (patch 51) acrescenta 6 arquivos gerados compilados uma segunda vez: ~1 min em paralelo.
