<div align="center">

# God of War — Native PC

[English](README.md) · **Português (Brasil)**

Um port nativo para PC de *God of War* (PS2, NTSC-U `SCUS-97399`), feito recompilando estaticamente o código MIPS
R5900 para C++, com launcher instalador, compilação em um clique, suporte a traduções de fãs e meta de 60 fps.

![platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6)
![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![status](https://img.shields.io/badge/status-experimental-orange)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

> [!IMPORTANT]
> Este repositório **não contém arquivos do jogo**. Você precisa da sua própria cópia de God of War. O runtime nativo
> (**PS2Recomp**, ampliado por Waffle565, KIexster e pelo port Tobiichi) é **obrigatório**; o launcher o baixa, ele não
> fica guardado aqui. Atribuição completa: [`CREDITS.md`](CREDITS.md).

## Conteúdo

- [O que é](#o-que-é)
- [Obrigatório: o runtime PS2Recomp](#obrigatório-o-runtime-ps2recomp)
- [Requisitos](#requisitos)
- [Como usar](#como-usar)
- [Atualizações e manutenção](#atualizações-e-manutenção)
- [Desempenho](#desempenho)
- [Traduções e idiomas](#traduções-e-idiomas)
- [Roadmap](#roadmap)
- [God of War II](#god-of-war-ii)
- [Estrutura](#estrutura)
- [Colaboradores](#colaboradores)
- [Créditos e licença](#créditos-e-licença)

## O que é

O executável do jogo (`SCUS_973.99`) é traduzido de MIPS para C++ pelo **PS2Recomp** e compilado como um programa
Windows. O runtime fornece gráficos, áudio, controles e memory card, com código compilado para VU1/IOP e um
interpretador para os programas de VU1 ainda não compilados.
Este projeto junta o trabalho de vários autores (veja [`CREDITS.md`](CREDITS.md)) num instalador único:

- **Instalação em três etapas**: baixe as ferramentas portáteis, selecione sua ISO e instale. O runtime é baixado
  automaticamente; a tela de carregamento mostra o progresso geral, a estimativa de tempo restante e dicas.
- **Uma ISO basta**: a original (USA) ou uma tradução de fãs reconhecida. Com várias ISOs (ex.: a original e a
  traduzida) cada idioma fica jogável e o launcher **pergunta em qual idioma você quer jogar**.
- **Otimizado para 60 fps**: o código da VU1 e do IOP vira código nativo; enquanto você joga, o código novo é gravado
  e "Acelerar áreas visitadas" o compila.
- **Controles configuráveis**: atalhos de teclado/mouse, esquemas clássico ou moderno e mapeamento botão por botão.
- **Acessibilidade**: os minijogos que pedem apertos repetidos podem ser jogados segurando o botão ("Segurar em vez de
  apertar sem parar", na aba Controles).
- **Atualizações pelo launcher**: novas versões do GitHub Releases aparecem na barra lateral; alterações nos patches
  do runtime geram um aviso para recompilar o jogo.

## Obrigatório: o runtime PS2Recomp

Sem o runtime nada é recompilado nem roda. Ele **não faz parte deste repositório**: **Instalar e compilar**, no
launcher, ou a etapa `fetch` do `build.cmd` o baixa em `engine/runtime/`, na versão fixada em
[`engine/runtime.toml`](engine/runtime.toml) (Tobiichi-Port, que inclui o PS2Recomp de ran-j com as extensões de
Waffle565 e KIexster), e aplica [`engine/patches`](engine/patches).

## Requisitos

| | |
|---|---|
| Sistema | Windows 10/11 64 bits |
| Processador | x86-64 com **AVX2**; 4 núcleos ou mais recomendados |
| Memória | 8 GB (16 GB recomendado para compilar) |
| Placa de vídeo | OpenGL 4.3+ |
| Armazenamento | **Estimativa de menos de 10 GB** para os arquivos preparados do jogo + uma compilação Release, dependendo da edição da ISO. Veja os detalhes abaixo. |
| Ferramentas | Git, Python, CMake, Ninja e clang (llvm-mingw) são baixados automaticamente em `data/_tools`. Visual Studio só é necessário para `-Toolchain msvc` ou para compilar o launcher/instalador pelo código-fonte. |
| Internet | Necessária para baixar o runtime, as ferramentas, as dependências e as atualizações |
| Jogo | Sua ISO de **God of War (NTSC-U, SCUS-97399)** ou uma tradução reconhecida |

A estimativa considera **um idioma preparado e uma compilação Release**, não um limite fixo para qualquer ISO.
A ISO de origem é extraída em `data/gow1/discs/`; mantê-la no mesmo disco ocupa o tamanho dela **além** dos arquivos
instalados. As ferramentas baixadas, o código do runtime, idiomas extras, compilações PGO/debug e o SDK do Qt para
desenvolver o launcher também ocupam espaço. Depois da preparação, a ISO não é necessária para jogar; guarde seu backup
separadamente.

Por padrão, a compilação usa uma pasta curta em `C:`: `C:\gow-build-clang` para clang Release. Se outra cópia já usar
essa raiz, o pipeline escolhe `C:\gow-build-<hash>-clang`. O caminho-base fica em `data/build-root.txt`, lido
automaticamente pelo launcher. Considere espaço nas duas unidades se o projeto e a compilação estiverem em discos diferentes.

## Como usar

1. Tenha o launcher:
   - **Instalador (mais fácil):** baixe `gow-native-pc-setup.exe` em
     [Releases](https://github.com/Vnnc1/gow-native-pc/releases), execute e clique em **INSTALAR** (sem
     administrador, só para o seu usuário). Ele cria atalhos no Menu Iniciar / área de trabalho e uma entrada em
     *Aplicativos* do Windows para desinstalar.
   - **Pacote portátil:** extraia `gow-native-pc-windows.zip` da mesma release e abra
     `launcher\bin\gow-launcher.exe` dentro da pasta extraída.
2. No launcher → aba **Instalação**:
   1. **Baixar ferramentas** — cópias portáteis são baixadas uma vez, com verificação SHA-256, sem alterar o PATH;
   2. **Adicionar ISO…** — selecione uma ou mais ISOs compatíveis; o launcher identifica o jogo e o idioma;
   3. **Instalar e compilar** — baixa o runtime, prepara o disco e compila o jogo. Deixe
      **Preparar a primeira jogatina (recomendado)** ativado: uma partida automática de quatro minutos roda
      **oculta e sem som**, prepara o cache de shaders e grava código VU1/IOP, seguida de uma recompilação incremental.
3. **JOGAR**. Em **Outros → Idioma do jogo** você troca o idioma.

O tempo depende do processador, do armazenamento e dos downloads. Uma compilação completa com clang levou cerca de
**15 minutos no PC de teste**; a preparação inicial acrescenta a gravação e uma compilação incremental. É uma referência,
não um prazo garantido de instalação.

### Pelo terminal

Execute na pasta do repositório (no PowerShell, use `.\` antes de `build.cmd`):

```bat
build.cmd -Discs "D:\God of War (USA).iso"
build.cmd -Stages optimize
```

O primeiro comando baixa as ferramentas e o runtime, prepara o disco e compila o jogo. O segundo grava a partida
inicial e recompila o código nativo; ele **não** faz parte do comando padrão do terminal. Para vários idiomas, use
`-Discs "D:\usa.iso|D:\ptbr.iso"`. Mais exemplos: [`build.cmd`](build.cmd).

### Compilar o launcher pelo código-fonte

Instale o [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) com
**Desenvolvimento para desktop com C++**. Se o Qt não estiver instalado, também será necessária uma instalação
completa do [Python](https://www.python.org/downloads/windows/) com pip para o `aqtinstall`. Depois execute:

```bat
build.cmd -Stages launcher
```

O pipeline baixa o Qt 6 quando necessário (cerca de 1 GB) e cria **`God of War Launcher.lnk`** no repositório.
O launcher da release já inclui suas bibliotecas Qt; para jogar, não é preciso instalar o SDK do Qt nem o Visual Studio.

## Atualizações e manutenção

O launcher consulta o GitHub Releases ao abrir e oferece novas versões abaixo do número da versão, na barra lateral.
A atualização preserva discos preparados, saves, ferramentas e código gravado. Se os patches do runtime mudarem,
**Instalação → Recompilar o jogo** aplica as mudanças e recompila o jogo.

Em **Instalação → Mais opções**:

| Ação | Finalidade |
|---|---|
| Acelerar áreas visitadas | Compila código VU1/IOP gravado durante as partidas (`build.cmd -Stages native`) |
| Recompilação rápida | Sincroniza código gerado/overrides e compila arquivos alterados (`build.cmd -Stages sync,build`) |
| Otimização guiada por perfil | Treina uma compilação clang separada e recompila usando o perfil medido (`build.cmd -Stages pgo`) |
| Runtime: Verificar / reparar | Baixa o runtime fixado pelo projeto e aplica seus patches |

Os logs ficam em `data/gow1/logs/`; o memory card compartilhado fica em `data/gow1/mc0/` nas unidades que permitem
junções de diretório (como NTFS). Para personalizar a tela de carregamento, coloque imagens PNG, JPG ou WebP em
`data/gow1/loading/`.

## Desempenho

O jogo é limitado a 60 quadros por design (a lógica segue o VBlank de 60 Hz do PS2). Resultados medidos e relatados
em várias máquinas, com cada combinação de código testada: [`docs/tested-hardware.md`](docs/tested-hardware.md).
A mesma configuração pode dar resultados diferentes em outra máquina — trate a tabela como referência.

No PC de teste do projeto, com **Xeon E5-2666 v3 / 16 GB de RAM / Radeon RX 580 2048SP**, clang + PGO registrou
**59,4 fps de média / 57,9 de mínimo** no combate automático do navio. O perfil foi treinado nessa mesma cena;
isso não comprova 60 fps constantes no jogo inteiro. Preparar a primeira jogatina e compilar as áreas visitadas
ajuda a reduzir o uso do interpretador de VU1.

Clang é o compilador padrão. `-Toolchain msvc` seleciona o Visual Studio Build Tools; `data/toolchain.txt` guarda
a escolha, e cada compilador usa sua própria pasta de build. PGO é opcional e atualmente exige clang.

## Traduções e idiomas

A compatibilidade é verificada pelo **SHA-1 da seção `.text`** do executável em
[`games/gow1/game.toml`](games/gow1/game.toml). Traduções que preservam o código original podem ser aceitas mesmo
sem uma edição cadastrada; o idioma é detectado pelos textos dos menus. Traduções que modificam código e outras
regiões com código diferente não são suportadas.

| ISOs selecionadas | Resultado |
|---|---|
| Original USA | Jogo em inglês |
| Tradução compatível | Jogo traduzido com os vídeos presentes naquele disco |
| Original USA + tradução compatível | Vídeos originais, incluindo widescreen, com textos traduzidos |

O launcher pergunta qual idioma usar quando há mais de um disponível. Veja os detalhes de compatibilidade e
preparação em [`docs/translations.md`](docs/translations.md).

## Roadmap

O [roadmap de desenvolvimento de 27/10/2026](https://github.com/Vnnc1/gow-native-pc/blob/claude/keen-dirac-42wd1y/docs/research/roadmap-2026-10-27.md),
na branch `claude/keen-dirac-42wd1y`, define estas prioridades, nesta ordem:

| Prioridade | Foco | Trabalho planejado |
|---|---|---|
| 1 | Qualidade da compilação e recompilação | Melhorar código gerado, cache de compilação, treinamento PGO e verificações de correção |
| 2 | 60 fps estáveis | Reduzir custos de EE/VU1, engasgos no carregamento e irregularidade no tempo dos quadros |
| 3 | Áudio | Investigar o alinhamento dos canais nas cutscenes PT-BR e corrigir variações de tonalidade |
| 4 | Mods e pacotes de texturas | Patches de ISO, substituição de arquivos, cheats de dados e troca de texturas |
| 5 | Qualidade de imagem | Melhorias na renderização interna, upscaling espacial, apresentação e HUD em widescreen |
| 6 | Base para God of War II | Isolar código específico de cada jogo e preparar perfis, análise e suporte ao primeiro boot |

Essa branch já contém trabalho no JIT de VU1, melhorias de compilação/cache e uma aba de saves. Essas mudanças
**ainda não fazem parte desta branch `main`**. A tabela resume trabalho planejado, não recursos lançados;
upscalers temporais como DLSS continuam como pesquisa. O avanço depende de verificações de correção e medições,
sem datas de lançamento prometidas.

## God of War II

Planejado: a arquitetura é por jogo (`games/<id>/`), mas o port do GoW II ainda não existe. O que falta:
[`games/gow2/README.md`](games/gow2/README.md).

## Estrutura

```
engine/     runtime.toml (qual runtime baixar) + patches numerados (com origem e motivo em cada um)
games/      perfis por jogo: gow1 (jogável), gow2 (planejado)
launcher/   o launcher Qt 6: instalação + jogo
installer/  o instalador .exe da release (Win32, junta launcher + ferramentas num arquivo; build.cmd -Stages installer)
tools/      disc/ (identificar, extrair, preparar), pipeline/ (compilação + atualizações), profile/ (profiler)
docs/       arquitetura, hardware testado, traduções, como adicionar um jogo
data/       (gerado, fora do git) discos preparados, saves, logs, código gravado, ferramentas portáteis
```

Para quem for manter o código (inclusive IAs): [`AGENTS.md`](AGENTS.md).

## Colaboradores

Este port foi construído sobre o trabalho destes autores e de suas comunidades:

<table>
  <tr>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/YYOzcan"><img src="https://github.com/YYOzcan.png?size=160" width="80" height="80" alt="Avatar de YYOzcan"><br><strong>YYOzcan</strong></a><br>
      <a href="https://github.com/YYOzcan/Tobiichi-Port">Tobiichi-Port</a><br>
      Integração do runtime, launcher Qt, configurações, controles, widescreen e filtros de imagem.
    </td>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/Waffle565"><img src="https://github.com/Waffle565.png?size=160" width="80" height="80" alt="Avatar de Waffle565"><br><strong>Waffle565</strong></a><br>
      <a href="https://github.com/Waffle565/God-Of-War-Native-Port">God-Of-War-Native-Port</a><br>
      Renderizador GS nativo, VU1/IOP compilados, áudio, controles, memory card e otimizações de CPU.
    </td>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/KIexster"><img src="https://github.com/KIexster.png?size=160" width="80" height="80" alt="Avatar de KIexster"><br><strong>KIexster</strong></a><br>
      <a href="https://github.com/KIexster/god-of-war-recomp">god-of-war-recomp</a><br>
      Patches que permitiram jogar a versão USA, configuração do recompilador, mapa de funções e correções de captura VU1.
    </td>
  </tr>
</table>

## Créditos e licença

- **[PS2Recomp](https://github.com/ran-j/PS2Recomp), de ran-j e colaboradores** — recompilador MIPS R5900 → C++
  e runtime nativo que formam a base deste projeto.
- **[GoW2-nativo-PS2](https://github.com/cxldsakeb/GoW2-nativo-PS2), de cxldsakeb, DaniSBR1 e Alejrr2** — correções
  de runtime adaptadas do trabalho deles e do [fork DaniSBR1/PS2Recomp](https://github.com/DaniSBR1/PS2Recomp).
- **[Qt](https://www.qt.io/)** — toolkit da interface do launcher, vinculado dinamicamente sob LGPL-3.0.

Atribuição completa, componentes utilizados e suas licenças: **[`CREDITS.md`](CREDITS.md)**. O código deste
repositório é distribuído sob a **GNU General Public License v3.0** — veja [`LICENSE`](LICENSE). God of War é marca
registrada da Sony Interactive Entertainment; nenhum arquivo do jogo é distribuído aqui.

[Repositório do projeto](https://github.com/Vnnc1/gow-native-pc) · [Releases](https://github.com/Vnnc1/gow-native-pc/releases)
