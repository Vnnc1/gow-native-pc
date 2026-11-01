# Texture packs do PCSX2 e mods de ISO: testes (2026-11-01)

Continuação de [`audio-standalone-mods-2026-10-26.md`](audio-standalone-mods-2026-10-26.md) (seção "Texture packs").
Material do teste: um pack no formato do PCSX2 (2.179 PNGs, 804 MB) e o patch "God of War Definitive Edition 2.0"
(`.xdelta`, 3,4 GB), ambos do jogador e fora do repositório.

## 1. Texture packs do PCSX2: compatíveis com o nosso renderizador

O PCSX2 nomeia cada substituição (`GSTextureCache::HashCacheKey`, `GSTextureReplacements.cpp`):

- `<hash da textura>-<hash da paleta>-<bits>.png` (formatos com paleta) ou `<hash da textura>-<bits>.png`;
- hash da textura = XXH3-64 dos blocos de 256 bytes da textura **como estão na memória do GS** (layout embaralhado),
  percorridos linha de blocos por linha de blocos;
- hash da paleta = XXH3-64 das 16 / 256 entradas da paleta em 32 bits, na ordem dos índices;
- bits = PSM | TW << 6 | TH << 10 (+ TEXA nos formatos de cor de 16/24 bits); o bit 14 (antigo TCC) é ignorado ao ler.

A nossa VRAM do GS (`ps2_gs_memory.h`) usa o mesmo layout do hardware, então o mesmo cálculo vale aqui. Protótipo
([`texture-pack-prototype-2026-11-01.diff`](texture-pack-prototype-2026-11-01.diff), contra `gs_hw_backend.cpp` da
cadeia 01–51; precisa do `xxhash.h` v0.8.3, BSD-2):

- `GOW_TEX_PCSX2_NAMES=<arquivo>` lista o nome PCSX2 de cada textura enviada pelo jogo que um draw usa;
- `GOW_TEXTURE_PACK=<pasta>` indexa os PNGs (qualquer subpasta) e, quando o nome bate, desenha com a imagem do pack
  pelo caminho de cor direta (inclusive as texturas com paleta), na resolução do PNG. O alpha do PNG está nas unidades do
  GS (128 = opaco), como o PCSX2 grava e carrega: sobe sem conversão.

Resultados no save de combate do navio:

| Medição | Resultado |
|---|---|
| Texturas distintas usadas pelo jogo | 84 |
| Com PNG de nome idêntico no pack | **69 (82%)** |
| PNGs carregados e aplicados | 69, nenhuma falha de leitura |
| Visual | madeira do convés com veios e tábuas nítidas no lugar da textura de baixa resolução |

As 15 restantes: texturas que o pack não cobre ou caminhos do PCSX2 ainda não reproduzidos.

### O que falta para virar recurso

1. **Carregamento em segundo plano**: hoje o PNG é lido na primeira vez que a textura aparece, na thread do GS (engasgo).
   O PCSX2 usa uma thread de carga e injeta a textura depois.
2. **Limite de VRAM** (LRU): 804 MB de PNG ocupam bem mais na GPU.
3. **Caminhos que faltam**: texturas menores que um bloco, formatos com máscara (T8H, T4HL, T4HH, CT24), regiões
   (`-r<w>x<h>` no nome), mipmaps (`-mip<n>`).
4. **Launcher**: pasta `data/<jogo>/mods/texturas/<pack>`, ativar/desativar por pack, sem recompilar.
5. **Desempenho**: medir o custo do hash (só quando a textura é reenviada) e o FPS com e sem pack.

## 2. Mod de ISO "Definitive Edition 2.0" (`.xdelta`)

- **Formato:** VCDIFF puro do Delta Patcher, sem compressão secundária. A origem é a **ISO americana**: os checksums
  adler32 das janelas batem com ela e não com a PT-BR. [`tools/disc/vcdiff.py`](../../tools/disc/vcdiff.py) lê e aplica
  o patch sem programas externos. A saída tem 3,62 GB e 463 janelas, todas com checksum conferido, em ~6 min.
- **O nosso `identify.py` recusa a ISO resultante**: o executável não é o código para o qual o port foi feito.
- **Diferenças no executável**:
  - o `.text` passa a começar em `0x96000` (era `0x100000`) e termina no mesmo endereço;
  - do código original (421.609 instruções), só **uma** mudou: o `jal` em `0x1001a0`, no início do programa, que agora
    chama `0xd02ec`;
  - o código novo ocupa `0xd0000`–`0xd1f0c` (~7,7 KB) e é um **carregador de mods do PCSX2**, pelas strings:
    `host0:/mod/%s.wad`, "Opening %s from mod folder!", "HUD WIDESCREEN BY FLUKERBR", `Blood_Value`, `ControllerType`;
  - `.data` e `.rodata` não mudam; o resto do mod está nos dados do disco.
- **Para suportar**:
  1. aceitar no `identify.py` uma edição "mod" cujo código original é idêntico salvo poucos ganchos;
  2. recompilar o ELF do mod, incluindo o código novo, e conferir se os overrides por endereço continuam valendo
     (o código original não mudou de lugar);
  3. ver se o carregador do mod funciona com os arquivos do próprio disco ou exige o `host0:` do PCSX2, que o runtime
     precisaria mapear para uma pasta;
  4. não haverá perfil PGO da release para ele: o `.text` é outro, então a instalação treina o próprio.
- **Ferramenta no launcher**: "Aplicar patch .xdelta" com o `vcdiff.py`. Trabalho pequeno, útil para qualquer mod
  distribuído assim.

Regra que continua valendo: não distribuir packs, ISOs nem patches de terceiros; o jogador traz os seus.

## 3. O que virou recurso (mesmo dia)

- **Patch 52 (`52-gs-texture-packs`)**:
  - nomes PCSX2 pelos dois caminhos, o direto (blocos) e o desembaralhado (texturas menores que um bloco, T8H, T4HL,
    T4HH e CT24);
  - PNGs lidos numa thread própria: até cada imagem ficar pronta, o jogo desenha a textura original;
  - memória de GPU limitada (`GOW_TEXTURE_PACK_MB`, padrão 1024), descartando primeiro o que foi usado há mais tempo,
    e mipmaps gerados na GPU;
  - xxHash v0.8.3 via FetchContent.
  - **Medido** no combate do navio: **81** imagens aplicadas (69 no protótipo), 73 MB, nenhum descarte, FPS dentro
    do ruído. `verify` passa com a cadeia 01–52.
- **Launcher → Gráficos → "Pacote de texturas (formato PCSX2)"**: escolher a pasta e ligar/desligar; passa
  `GOW_TEXTURE_PACK` ao jogo, sem recompilar. O liga/desliga entra nos relatórios de sessão (a pasta não, por ser
  pessoal).
- **Etapa `xdelta`** (`build.cmd -Stages xdelta -Xdelta <patch> -Discs <ISO base>`) e **Launcher → Instalação → Mais
  opções → "Aplicar patch de ISO (.xdelta)"**:
  - aplica o patch em `data/mods/isos/<nome>.iso`, publicada só quando completa;
  - com a ISO base errada, falha na primeira janela ("the patch was made for a different ISO"), sem deixar arquivo;
  - a ISO gerada entra na lista de ISOs, e a etapa `discs` decide se dá para compilar.

## 4. Definitive Edition: o que falta (próximo trabalho)

- **Identificação**: um tipo de edição "mod", aceito quando o código original (nos endereços originais) é idêntico salvo
  poucos ganchos.
- **Funções novas**: o recompilador usa `config/funcmap.csv`, que só tem o código americano. O código do mod
  (`0xd0000`–`0xd1f0c`) precisa ter as funções descobertas (prólogos, alvos de `jal`) e acrescentadas para a recompilação.
- **`host0:`**: o runtime já tem o dispositivo `host0` (`g_ps2_cwd_device`, `ps2_path.cpp`). Falta conferir para onde
  ele aponta e onde o mod espera os `.wad` (`host0:/mod/`).
- Cada tentativa é uma recompilação completa (~25 min).
