# Próximos passos: 60 FPS, God of War II e outras plataformas (2026-11-01)

O item A (recompilação em no máximo 10 minutos) está em andamento em
[`launcher-e-recompilacao-2026-10-31.pt-BR.md`](launcher-e-recompilacao-2026-10-31.pt-BR.md). Este documento guarda os
outros três para quando forem retomados. Medições e números citados são deste projeto (Xeon E5-2666 v3 + RX 580).

## B. 60 FPS: o que ainda pode mudar o resultado

O limite atual é **uma thread de VU1 ocupada 100% do tempo** no combate pesado (perfil do worker: transição entre blocos
27%, blocos gerados 35%, espera 8%). Já descartado por medição: AVX2 no código da VU1 (0%), baixar a resolução (o
gargalo é CPU), timing estático completo (teto ~5%), caminho rápido de auto-laços e `chain` em linha (patch 49, empate).

| Ideia | O que é | Ganho esperado | Custo | Como medir |
|---|---|---|---|---|
| **PGO treinado no modo VU rápida** | Hoje o treino roda no modo exato: as partes `vu1n_fast<k>.cpp` ficam sem perfil. Treinar com `GOW_VU1_FAST=1` (ou nos dois modos, juntando os `.profraw`) | ~5–9% da VU1 no modo rápido (o PGO vale ~9% na VU1) | baixo: ajuste no estágio `pgo`/`tune` (`optimize.ps1`) | replay de combate com `GOW_VU1_FAST=1`, sem e com perfil |
| **VU rápida, etapa 2: timing ocioso** | No modo rápido, `readsEntryFlags` passa a usar a tabela ociosa (`sl.idle`) em vez de `blockTiming` | ~5,5% da VU1 (teto medido) | médio; risco visual (sombras dependem de flags) | replay + capturas nas áreas |
| **ThinLTO** (`-Ltcg`, patch 31) | Otimização entre o código gerado da VU1 e o runtime (inclusive `VU1NativeAccess::chain`, chamado entre unidades de compilação) | desconhecido: nunca medido em FPS | só tempo de compilação (mais lento) | pares A/B no save de combate, PC ocioso |
| **Paralelizar a VU1** (fase 3) | Dividir o trabalho de VU1 de um quadro entre duas threads (memória da VU duplicada, programas independentes em paralelo, ordem dos pacotes do GS preservada) | o único que muda o teto: pode dar folga real acima de 60 | alto: análise de dependência entre programas, sincronização do GIF | replay (equivalência bit a bit) + FPS |

Ordem sugerida: PGO no modo rápido → ThinLTO (A/B) → timing ocioso → estudo de paralelização.

## C. God of War II: até os primeiros sinais de gameplay

Ponto de partida: `games/gow2/game.toml` (`status = "planned"`, serial SCUS-97481, `text_sha1` vazio), correções de runtime
já no patch 05 (`05-gow2-runtime-fixes`) e casos do GoW II já tratados no renderizador (bloom com imagens de 64/128/256 px
lado a lado, `gs_hw_backend.cpp`). Mesmo motor do primeiro jogo: VU1 e GS devem servir em grande parte. Guia geral:
[`docs/adding-a-game.md`](../adding-a-game.md).

1. **Identificação**: `python -I tools/disc/identify.py "<ISO do GoW II>"` → nome do ELF, CRC, SHA-1 do `.text` no
   `game.toml`.
2. **Mapa de funções**: gerar com o `ps2xAnalyzer` (no PS2Recomp) a partir do ELF, no formato de `config/funcmap.csv`.
3. **Configuração do recompilador**: um `recomp.template.toml` próprio (stubs, entry points, MMIO), partindo do do GoW I.
4. **Disco**: TOC e PAKs (`[disc]` no perfil), módulos IOP, vídeos.
5. **Overrides do jogo**: começar vazio; adicionar só o que travar o boot.
6. **Marco 1**: boot com logs (IOP carregando os módulos, primeiros quadros do GS). **Marco 2**: tela de título.
   **Marco 3**: gameplay.

Precisa da ISO do GoW II do jogador (só local). Cada recompilação completa ~25 min; o marco 1 pode ser atingido com
builds `Release` sem PGO.

## D. Outras plataformas

| Plataforma | Viabilidade | Trabalho |
|---|---|---|
| **Linux / Steam Deck** | alta | O runtime e o launcher (Qt) já têm caminhos de Linux; OpenGL 4.3 roda em Mesa e NVIDIA. Falta: pipeline fora do PowerShell/ferramentas de Windows (bash ou PowerShell 7 + clang do sistema), memória executável POSIX no JIT x64 da VU1 (`mmap`/`mprotect` no lugar de `VirtualAlloc`), empacotamento (AppImage ou tarball), testes num Steam Deck. |
| **macOS** | baixa sem um novo backend | OpenGL parado na 4.1 (sem compute shader nem texture barrier): o renderizador GLSL 430 não roda. Exige backend Vulkan (via MoltenVK) ou Metal. Apple Silicon é ARM64: sem o JIT x64; o código AOT funciona via `sse2neon` (já é dependência). |
| **Android** | baixa | O PS2Recomp tem `android/` e `PS2X_IS_ANDROID`. O jogo teria de ser compilado no PC e instalado como APK; renderizador em GLES 3.2/Vulkan; a VU1 numa única thread já é o gargalo num Xeon, então 60 FPS só em celulares topo de linha, e incerto. |

Recomendação: Linux primeiro (é o que mais entrega com menos trabalho, e o Steam Deck vem junto). macOS e Android ficam
para depois de um backend Vulkan, que é um projeto próprio.

Regra que vale para todas: o jogador compila o jogo a partir da própria ISO; nada do jogo é distribuído.
