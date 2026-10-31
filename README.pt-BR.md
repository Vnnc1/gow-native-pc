<div align="center">

# God of War — Native PC

[English](README.md) · **Português (Brasil)**

Um port nativo para PC de *God of War* (PS2, NTSC-U `SCUS-97399`), feito recompilando estaticamente o código MIPS
R5900 para C++, com launcher instalador, compilação em um clique, suporte a traduções de fãs e meta de 60 fps.

![platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6)
![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![version](https://img.shields.io/badge/vers%C3%A3o-3.0.1-crimson)
![status](https://img.shields.io/badge/status-experimental-orange)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

> [!IMPORTANT]
> Este repositório **não contém arquivos do jogo**. Você precisa da sua própria cópia de God of War. O runtime nativo
> (**PS2Recomp**, ampliado por Waffle565, KIexster e pelo port Tobiichi) é **obrigatório**; o launcher o baixa, ele não
> fica guardado aqui. Atribuição completa: [`CREDITS.md`](CREDITS.md).

> [!WARNING]
> **O projeto ainda não está 100%.** O jogo é jogável, mas 60 fps travados ainda não são alcançados em todas as cenas,
> só as áreas iniciais foram medidas a fundo e alguns problemas continuam (veja [Limitações conhecidas](#limitações-conhecidas)).
> Ele melhora a cada versão, e mais coisas vão chegar conforme a necessidade da comunidade — **texture packs, port para
> Linux, mods de ISO** e outras adições estão planejadas (veja o [Roadmap](#roadmap)). Relatos de bugs com o relatório
> de sessão do launcher ajudam muito: [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Conteúdo

- [O que é](#o-que-é)
- [Novidades da 3.0.1](#novidades-da-301)
- [Novidades da 3.0.0](#novidades-da-300)
- [Obrigatório: o runtime PS2Recomp](#obrigatório-o-runtime-ps2recomp)
- [Requisitos](#requisitos)
- [Como usar](#como-usar)
- [No jogo](#no-jogo)
- [Atualizações e manutenção](#atualizações-e-manutenção)
- [Desempenho](#desempenho)
- [Upscaling e ferramentas externas](#upscaling-e-ferramentas-externas)
- [Traduções e idiomas](#traduções-e-idiomas)
- [Relatando problemas](#relatando-problemas)
- [Limitações conhecidas](#limitações-conhecidas)
- [Roadmap](#roadmap)
- [God of War II](#god-of-war-ii)
- [Estrutura](#estrutura)
- [Colaboradores](#colaboradores)
- [Créditos e licença](#créditos-e-licença)

## O que é

O executável do jogo (`SCUS_973.99`) é traduzido de MIPS para C++ pelo **PS2Recomp** e compilado como um programa de
Windows. O runtime cuida de gráficos, áudio, controles e cartão de memória, com código nativo de VU1/IOP, um JIT da VU1
para o código ainda não compilado e um interpretador como último recurso.
Este projeto junta o trabalho de vários autores (veja [`CREDITS.md`](CREDITS.md)) atrás de um único instalador:

- **Instalação em três passos**: baixar as ferramentas portáteis, escolher sua ISO e instalar. O runtime é baixado
  automaticamente; uma tela de carregamento mostra o progresso geral, o tempo restante e dicas.
- **Uma ISO basta**: a original (USA) ou uma tradução de fãs reconhecida. Com várias ISOs (ex.: a original e uma
  tradução), todos os idiomas ficam jogáveis e o launcher **pergunta em qual idioma você quer jogar**.
- **Feito para desempenho**: a preparação da primeira jogatina grava o código de VU1/IOP e um perfil de desempenho numa
  única execução e compila o jogo final com os dois (otimização guiada por perfil, PGO).
- **Controles configuráveis**: teclado e mouse totalmente configuráveis, layouts clássico ou moderno de controle e
  mapeamento botão a botão.
- **Menu no jogo (F1)**: ajustes gráficos ao vivo, truques e cópias do cartão de memória.

## Novidades da 3.0.1

Medido no PC de teste (Xeon E5-2666 v3 + RX 580, rota do save, tela cheia, pares alternados); detalhes em
[`docs/research/roteiro-60fps.pt-BR.md`](docs/research/roteiro-60fps.pt-BR.md):

- **Código da VU1 mais rápido**, com o mesmo resultado bit a bit (patch 43 do runtime): média de ~51 para ~57 FPS,
  combate pesado de ~51 para ~55 FPS.
- **Envio mais barato para a thread do GS** (patch 44): ~150 mil despertares de thread a menos por segundo, combate +3,5%.
- **Decodificação da VU1 sob demanda e uma cópia a menos por pacote GIF** (patches 45–46, do fork
  [gow-native-pc-optimization](https://github.com/huanghuangdaquan-beep/gow-native-pc-optimization)).
- **Instalação**: dependências baixadas uma vez só e sem histórico (a etapa do PGO não baixa mais ~1 GB de novo); CPUs
  de até 4 threads pulam o PGO e usam um compilador a mais; CPUs sem SSE4.2 são avisadas antes da instalação, não
  depois.
- **Atualizações**: o aviso de "recompilar" só some depois de recompilar com o runtime novo, e o launcher recomenda
  retreinar o PGO depois de uma atualização.

## Novidades da 3.0.0

Em relação à 2.0.0 (detalhes em [`docs/tested-hardware.md`](docs/tested-hardware.md) e na
[revisão desta versão](docs/research/revisao-2026-10-30.pt-BR.md)):

| Área | Mudança |
|---|---|
| Desempenho | **Early FINISH**: o jogo prepara o próximo quadro enquanto a VU1 desenha o atual — cerca de **+20% no combate pesado** (medido). Ligado por padrão, com opção em Launcher → Desempenho. |
| Desempenho | **PGO incluído na instalação**: a preparação da primeira jogatina já compila com otimização guiada por perfil (cerca de +5% na média, +13% no combate, medido). |
| Compilação | Preparação + PGO em cerca de **24 minutos** em vez de ~63; mais compiladores em paralelo em máquinas com menos RAM por núcleo; o maior arquivo gerado compila em 10 s em vez de 331 s. |
| Compilação | Toolchain única fixada (clang/llvm-mingw), geração de código com cache e testes de regressão (`build.cmd -Stages verify`). |
| No jogo | **Menu F1** com Gráficos (filtro, nitidez, FXAA, anisotrópico, limite de FPS, VSync, contador de FPS, esticar — tudo ao vivo), Truques e Save. O depurador do runtime foi para Ctrl+F1. |
| Imagem | O FXAA não desliga mais o filtro nítido; modo tela cheia sem bordas. |
| Launcher | Perfis gráficos rápidos (Desempenho / Equilibrado / Qualidade), seção honesta de Upscaling e ferramentas, atalho para o teclado na página Controles, opções que não faziam nada removidas, estado e recomendação do PGO. |
| Launcher | Página Saves, relatórios de sessão para bugs, menu do jogo em português. |
| VU1 | JIT x86-64 no próprio processo, encadeamento de blocos e caminhos rápidos de laços, captura de código faltante para compilar depois. |
| Correções | Memória/DMA, overflow na mixagem do SPU2, perfil de execução direta e várias correções menores, listadas por patch em [`engine/README.md`](engine/README.md). |

## Obrigatório: o runtime PS2Recomp

Sem o runtime nada pode ser recompilado ou executado. Ele **não faz parte deste repositório**: **Instalar e compilar**
no launcher ou a etapa `fetch` do `build.cmd` o clona em `engine/runtime/` na versão fixada em
[`engine/runtime.toml`](engine/runtime.toml) (Tobiichi-Port, que reúne o PS2Recomp de ran-j com as extensões de
Waffle565 e KIexster) e aplica [`engine/patches`](engine/patches) (01–41 nesta versão).

## Requisitos

| | |
|---|---|
| Sistema | Windows 10/11 64 bits |
| CPU | x86-64 com SSE4.2 (x86-64-v2); AVX/AVX2 são usados pelo JIT da VU1 quando existem. 4 núcleos ou mais recomendados |
| RAM | 8 GB (16 GB recomendados durante a compilação) |
| GPU | OpenGL 4.3+ |
| Armazenamento | **Menos de 10 GB, como estimativa**, para os arquivos preparados do jogo + uma compilação Release, conforme a edição da ISO. Veja as observações abaixo. |
| Ferramentas | Git, Python, CMake, Ninja e clang (llvm-mingw) são baixados automaticamente para `data/_tools`. Visual Studio não é necessário. |
| Internet | Necessária para baixar o runtime, as ferramentas, as dependências e as atualizações |
| Jogo | Sua ISO de **God of War (NTSC-U, SCUS-97399)** ou uma tradução reconhecida |

A estimativa cobre **um idioma preparado e uma compilação Release**, não é um limite fixo para toda ISO. A ISO é
extraída em `data/gow1/discs/`; mantê-la no mesmo disco ocupa o tamanho dela **além** dos arquivos instalados.
Ferramentas baixadas, o runtime, idiomas extras, a compilação de treino do PGO e o SDK do Qt para desenvolver o
launcher também ocupam espaço. A ISO não é necessária para jogar depois da preparação; guarde sua cópia à parte.

As compilações usam por padrão uma pasta curta no `C:`: `C:\gow-build-clang` para clang Release (a compilação de treino
do PGO usa `C:\gow-build-clang-pgogen`). Se outra cópia já usar essa pasta, o pipeline escolhe `C:\gow-build-<hash>-clang`.
O caminho fica registrado em `data/build-root.txt`; o launcher o lê automaticamente.

## Como usar

1. Obtenha o launcher:
   - **Instalador (mais fácil):** baixe `gow-native-pc-setup.exe` em
     [Releases](https://github.com/Vnnc1/gow-native-pc/releases), execute e clique em **INSTALAR** (sem permissão de
     administrador, só para o seu usuário). Ele cria atalhos no menu Iniciar / área de trabalho e uma entrada em
     *Aplicativos* do Windows para desinstalar.
2. No launcher → aba **Instalação**:
   1. **Baixar ferramentas** — cópias portáteis são baixadas uma vez, com verificação SHA-256, sem alterar seu PATH;
   2. **Adicionar ISO…** — escolha uma ou mais ISOs compatíveis; o launcher identifica o jogo e o idioma;
   3. **Instalar e compilar** — baixa o runtime, prepara o disco e compila o jogo. Deixe **Preparar a primeira jogatina
      (recomendado)** ligado: uma cópia de treino se joga sozinha por quatro minutos, **escondida e sem som**, grava o
      código de VU1/IOP e um perfil de desempenho, e o jogo final é compilado com os dois.
3. Escolha um **perfil gráfico** (página Gráficos), confira os **Controles** se for jogar no teclado e clique em **JOGAR**.

O tempo depende da CPU, da RAM, do disco e dos downloads. No PC de testes (Xeon E5-2666 v3, 20 threads, 16 GB) a
instalação completa com preparação e PGO leva **cerca de 30 minutos**; é uma referência, não um prazo. Um jogo instalado
com uma versão anterior mostra **"Otimização de FPS recomendada (PGO)"** na página Início.

### Pelo terminal

Execute na pasta do repositório (no PowerShell, use `.\build.cmd`):

```bat
build.cmd -Discs "D:\God of War (USA).iso" -Stages tools,fetch,discs,configure,recomp,sync,tune
```

É o que o launcher faz: ferramentas, runtime, preparação do disco, recompilação e a etapa `tune` (execução de treino +
compilação final com PGO). Sem a preparação da primeira jogatina, use o padrão `build.cmd -Discs "D:\God of War (USA).iso"`.
Para vários idiomas, passe `-Discs "D:\usa.iso|D:\ptbr.iso"`. Mais exemplos: [`build.cmd`](build.cmd).
`build.cmd -Stages verify` roda os testes de regressão sem precisar do disco.

### Compilar o launcher e o setup a partir do código

```bat
build.cmd -Stages launcher
build.cmd -Stages installer
```

A primeira compilação do launcher compila uma vez um Qt compatível a partir de fontes fixadas (pode demorar bem mais
que a do jogo) e cria **`God of War Launcher.lnk`** no repositório. `installer` gera `data\_package\gow-native-pc-setup.exe`.
Jogadores não precisam de Qt nem de compilador para o launcher.

## No jogo

| Tecla | Ação |
|---|---|
| **F1** | Menu do jogo: Gráficos (ao vivo), Truques, Save |
| **F2** | Menu do jogo na aba Truques |
| **F11** | Tela cheia / janela (sem bordas, quando esse modo estiver escolhido) |
| **Ctrl+F1** | Depurador do runtime (para desenvolvedores) |

As mudanças gráficas feitas no menu F1 valem para a sessão; o launcher guarda seus ajustes. Resolução interna e
widescreen são mudadas no launcher (exigem reiniciar o jogo).

## Atualizações e manutenção

O launcher procura novas versões nos Releases do GitHub ao abrir e as oferece abaixo do número de versão na barra
lateral. Atualizar preserva discos preparados, saves, ferramentas e código gravado. Se os patches do runtime mudarem,
**Instalação → Recompilar tudo** aplica e recompila.

Em **Instalação → Mais opções**:

| Ação | Para quê |
|---|---|
| Acelerar áreas visitadas | Compila o código de VU1/IOP gravado durante o jogo (`build.cmd -Stages native`) |
| Recompilação rápida | Sincroniza código gerado/overrides e compila o que mudou (`build.cmd -Stages sync,build`) |
| Otimização guiada por perfil | Para um jogo instalado sem ela: execução de treino + recompilação com o perfil (`build.cmd -Stages pgo`), cerca de 20 minutos; aparece como *ativa* ou *recomendada* |
| Runtime: Verificar / reparar | Baixa o runtime fixado e aplica os patches do projeto |

Os logs ficam em `data/gow1/logs/`; o cartão de memória compartilhado fica em `data/gow1/mc0/` em discos com suporte a
junções (como NTFS). Cópias do cartão: página Saves ou F1 → Save ([`docs/saves.md`](docs/saves.md)). Para personalizar a
tela de carregamento, coloque imagens PNG, JPG ou WebP em `data/gow1/loading/`.

## Desempenho

O jogo é limitado a 60 quadros por design (a lógica segue o VBlank de 60 Hz do PS2). Todas as medições, com o código e
os ajustes usados: [`docs/tested-hardware.md`](docs/tested-hardware.md). Os resultados variam entre máquinas — use-os
como referência.

No PC de testes do projeto, **Xeon E5-2666 v3 / 16 GB / Radeon RX 580 2048SP** (tela cheia 1080p, resolução interna 2×,
PGO, Early FINISH), o navio inicial fica em **cerca de 55 fps de média**, com trechos de combate pesado em torno de
**50–53 fps**; uma sessão de 30 minutos a partir de um save mais à frente teve média de 48 fps com memória estável.
**60 fps travados ainda não são alcançados**: o limite que resta é o trabalho da VU1 na CPU (cerca de 19 ms por quadro no
combate mais pesado; são necessários 16,7 ms). Baixar a resolução interna só ajuda quando a GPU é o limite. CPUs mais
fracas (ex.: i5 de notebook) ainda não foram medidas com esta versão; relatos são bem-vindos.

## Upscaling e ferramentas externas

- **Nativo:** resolução interna (o jogo desenha de verdade 2×, 3×… mais pixels), filtro nítido (bicúbico + nitidez
  adaptativa), FXAA e filtro anisotrópico — tudo em Launcher → Gráficos, a maior parte também ao vivo no menu F1.
- **DLSS / FSR 2–3 / XeSS:** indisponíveis. Exigem vetores de movimento e um renderizador DirectX 12/Vulkan; a unidade
  gráfica do PS2 (aqui em OpenGL) não fornece isso. O DLSS também exige placa NVIDIA RTX.
- **Ferramentas externas** como Lossless Scaling (escala / geração de quadros), ReShade (OpenGL) e OBS enxergam o jogo no
  modo **sem bordas** (Launcher → Gráficos → *Permitir ferramentas externas*). Não são testadas oficialmente e podem
  adicionar atraso; geração de quadros funciona melhor quando o jogo já roda num ritmo estável.

## Traduções e idiomas

A compatibilidade é verificada pelo **SHA-1 da seção `.text`** do executável em [`games/gow1/game.toml`](games/gow1/game.toml).
Traduções que preservam o código original podem ser aceitas mesmo sem uma edição cadastrada; o idioma é detectado pelos
textos do menu. Traduções que alteram código e outras regiões com código diferente não são suportadas.

| ISOs escolhidas | Resultado |
|---|---|
| Original USA | Jogo em inglês |
| Tradução compatível | Jogo traduzido com os vídeos presentes nesse disco |
| Original USA + tradução compatível | Vídeos originais, inclusive widescreen, com textos traduzidos |

Com mais de um idioma, o launcher pergunta qual usar. Detalhes de compatibilidade e preparação do disco:
[`docs/translations.md`](docs/translations.md).

## Relatando problemas

O launcher guarda um relatório limitado de cada sessão. Use **Outros → Marcar um problema durante o jogo** quando algo
acontecer e depois **Outros → Relatório de testes e erros** ao fechar o jogo para exportar o ZIP. Revise e anexe o ZIP ao seu relato, com a área e os
passos para reproduzir. Nada é enviado automaticamente; arquivos do jogo e saves ficam de fora. Diagnósticos detalhados
são opcionais e podem reduzir o FPS. Veja [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Limitações conhecidas

- 60 fps travados ainda não são alcançados no combate pesado (veja [Desempenho](#desempenho)).
- Só as áreas iniciais (o navio) foram medidas a fundo; áreas posteriores podem se comportar diferente.
- Pequenos engasgos com falhas de áudio podem ocorrer em transições de área; o áudio das cutscenes em PT-BR tem um
  problema conhecido de alinhamento de canais ([`docs/research/cutscene-audio-2026-10-26.md`](docs/research/cutscene-audio-2026-10-26.md)).
- Se notar falhas de imagem, desligue **Antecipar o fim do quadro** em Launcher → Desempenho e relate.
- Por enquanto, só Windows.

## Roadmap

O plano completo, com os critérios de medição de cada item: [`docs/research/roadmap-2026-10-27.md`](docs/research/roadmap-2026-10-27.md).

| Prioridade | Foco | Situação |
|---|---|---|
| 1 | Qualidade da compilação e da recompilação | Em grande parte feito na 3.0.0 (toolchain fixada, cache, verify, instalação mais rápida com PGO); próximo: instalação abaixo de 20 minutos |
| 2 | 60 fps estáveis | Early FINISH e PGO feitos; próximo: timing estático da VU1 (os ~14% que faltam no combate pesado) e instruções da VU1 ainda interpretadas |
| 3 | Áudio | Alinhamento das cutscenes PT-BR e falhas em transições |
| 4 | Mods e texture packs | Patches de ISO, substituição de arquivos e de texturas ([`docs/research/audio-standalone-mods-2026-10-26.md`](docs/research/audio-standalone-mods-2026-10-26.md)) |
| 5 | Port para Linux | O runtime e o launcher já têm caminhos para Linux; falta portar o pipeline de compilação e testar em hardware real |
| 6 | Qualidade de imagem | Upscaling espacial, correções do HUD em widescreen |
| 7 | Base para God of War II | Código específico do jogo isolado por perfil ([`games/gow2/README.md`](games/gow2/README.md)) |

Mais coisas serão adicionadas conforme a necessidade da comunidade. O avanço depende de verificações de correção e de
medições; não há datas prometidas.

## God of War II

Planejado: a arquitetura é por jogo (`games/<id>/`), mas um port de GoW II ainda não existe. O que ele precisa:
[`games/gow2/README.md`](games/gow2/README.md).

## Estrutura

```
engine/     runtime.toml (qual runtime baixar) + patches numerados (origem, motivo e medições em cada um)
games/      perfis por jogo: gow1 (jogável), gow2 (planejado)
launcher/   o launcher em Qt 6: instalação + jogo
installer/  o setup .exe da versão (Win32, empacota launcher + ferramentas num arquivo; build.cmd -Stages installer)
tools/      disc/ (identificar, extrair, preparar), pipeline/ (compilação + atualizações), profile/ (profiler), test/
docs/       arquitetura, hardware testado, traduções, saves, relatos de bugs, pesquisas e revisões
data/       (gerado, ignorado pelo git) discos preparados, saves, logs, código gravado, ferramentas portáteis
```

Mantenedores (incluindo agentes de IA): comecem por [`AGENTS.md`](AGENTS.md).

## Colaboradores

Este port se apoia no trabalho destes autores e de suas comunidades:

<table>
  <tr>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/YYOzcan"><img src="https://github.com/YYOzcan.png?size=160" width="80" height="80" alt="Avatar de YYOzcan"><br><strong>YYOzcan</strong></a><br>
      <a href="https://github.com/YYOzcan/Tobiichi-Port">Tobiichi-Port</a><br>
      Integração do runtime, launcher Qt, ajustes, controles, widescreen e filtros de imagem.
    </td>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/Waffle565"><img src="https://github.com/Waffle565.png?size=160" width="80" height="80" alt="Avatar de Waffle565"><br><strong>Waffle565</strong></a><br>
      <a href="https://github.com/Waffle565/God-Of-War-Native-Port">God-Of-War-Native-Port</a><br>
      Renderizador GS nativo, VU1/IOP compilados, som, controles, cartões de memória e otimizações de CPU.
    </td>
    <td align="center" width="33%" valign="top">
      <a href="https://github.com/KIexster"><img src="https://github.com/KIexster.png?size=160" width="80" height="80" alt="Avatar de KIexster"><br><strong>KIexster</strong></a><br>
      <a href="https://github.com/KIexster/god-of-war-recomp">god-of-war-recomp</a><br>
      Patches que chegaram ao gameplay USA, configuração do recompilador, mapa de funções e correções da captura de VU1.
    </td>
  </tr>
</table>

## Créditos e licença

- **[PS2Recomp](https://github.com/ran-j/PS2Recomp), de ran-j e colaboradores** — o recompilador MIPS R5900 → C++ e o
  runtime nativo que formam a base deste projeto.
- **[GoW2-nativo-PS2](https://github.com/cxldsakeb/GoW2-nativo-PS2), de cxldsakeb, DaniSBR1 e Alejrr2** — correções do
  runtime adaptadas do trabalho deles e do [fork DaniSBR1/PS2Recomp](https://github.com/DaniSBR1/PS2Recomp).
- **[Qt](https://www.qt.io/)** — o toolkit de interface do launcher, ligado dinamicamente sob LGPL-3.0.

Atribuição completa, componentes reutilizados e suas licenças: **[`CREDITS.md`](CREDITS.md)**. O código deste
repositório é distribuído sob a **GNU General Public License v3.0** — veja [`LICENSE`](LICENSE). God of War é uma marca
da Sony Interactive Entertainment; nenhum arquivo do jogo é distribuído aqui.

[Repositório do projeto](https://github.com/Vnnc1/gow-native-pc) · [Releases](https://github.com/Vnnc1/gow-native-pc/releases)
