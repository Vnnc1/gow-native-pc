<div align="center">

# God of War — Native PC

[English](README.md) · **Português (Brasil)**

Um port nativo para PC de *God of War* (PS2, NTSC-U `SCUS-97399`), feito recompilando estaticamente o código MIPS
R5900 para C++, com launcher instalador, compilação em um clique, suporte a traduções de fãs e meta de 60 fps.

![platform](https://img.shields.io/badge/platform-Windows%20x64-0078D6)
![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?logo=cplusplus&logoColor=white)
![build](https://img.shields.io/badge/build-CMake%20%2B%20Ninja-064F8C?logo=cmake&logoColor=white)
![based on](https://img.shields.io/badge/based%20on-PS2Recomp-8A2BE2)
![version](https://img.shields.io/badge/vers%C3%A3o-0.6.0-crimson)
![status](https://img.shields.io/badge/status-experimental-orange)
![license](https://img.shields.io/badge/license-GPL--3.0-blue)

</div>

**Candidata 0.6.0 para testes:** menu com pausa e ajustes persistentes, carregamento de slots nativos, backups nos altares, ícones/QTEs remapeados, assistências opcionais e escolha da pasta da build. Veja [todas as mudanças](CHANGELOG.pt-BR.md) e [validações da candidata](docs/research/release-0.6.0-candidate.md). Distribuída apenas como v0.6.0-rc.1 para testes; v0.5.0 continua estável.

**Linux / Steam Deck (experimental):** launcher nativo, pipeline e instalador Linux disponíveis para testes.
Veja [instalação e validações pendentes](docs/linux.md). Hardware e desempenho no Steam Deck ainda não validados.

> [!IMPORTANT]
> Este repositório **não contém arquivos do jogo**. Você precisa da sua própria cópia de God of War. O runtime nativo
> (**PS2Recomp**, ampliado por Waffle565, KIexster e pelo port Tobiichi) é **obrigatório**; o launcher o baixa, ele não
> fica guardado aqui. Atribuição completa: [`CREDITS.md`](CREDITS.md).

> [!WARNING]
> **O projeto ainda não está 100%.** O jogo é jogável, mas 60 fps travados ainda não são alcançados em todas as cenas,
> só as áreas iniciais foram medidas a fundo e alguns problemas continuam (veja [Limitações conhecidas](#limitações-conhecidas)).
> Texture packs, patches de ISO e Linux experimental já estão disponíveis; as próximas melhorias estão no
> [Roadmap](#roadmap). Relatos de bugs com o relatório
> de sessão do launcher ajudam muito: [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Conteúdo

- [O que é](#o-que-é)
- [Novidades da 0.5.0](#novidades-da-050)
- [Novidades da 0.4.0](#novidades-da-040)
- [Novidades da 0.3.1](#novidades-da-031)
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
- **Feito para desempenho**: builds Windows podem usar um perfil de otimização (PGO) compatível. O pacote 0.5.0
  não inclui perfil pré-treinado; o treinamento local continua disponível. A preparação da
  primeira jogatina grava o código de VU1/IOP numa única execução e o compila como código nativo.
- **Controles configuráveis**: teclado e mouse totalmente configuráveis, layouts clássico ou moderno de controle e
  mapeamento botão a botão.
- **Acessibilidade**: os minijogos que pedem apertos repetidos podem ser jogados segurando o botão
  ("Segurar em vez de apertar sem parar" na aba Acessibilidade), junto dos gestos de analógico e texture packs.
- **Menu no jogo (F1 / Select + Start)**: pausa a partida; gráficos, controles, áudio, acessibilidade, packs,
  cheats e saves. Ajustes suportados persistem e sincronizam com o launcher.
- **Launcher em nove idiomas**: inglês, português, espanhol, turco, francês, alemão, italiano, russo e chinês
  simplificado.

## Novidades da 0.5.0

Para a candidata 0.6.0 mais recente, veja o [changelog completo](CHANGELOG.pt-BR.md). A seção abaixo é da versão anterior.

- **Linux experimental:** launcher nativo, pipeline de compilação e instalador `.run` para testes em PCs Linux e
  Steam Deck. Compilação e testes iniciais feitos no WSL; compatibilidade e desempenho no Deck real ainda não validados.
- **Importação de ISO e CHD:** conversão verificada de CHD para um cache local de ISO antes da recompilação,
  preservando a imagem original.
- **Edições regionais:** EUA e a imagem Asia testada, cujo código é compatível com USA; Japão e Europa têm builds
  Windows isoladas, validadas no início do jogo. Elas exigem uma build correspondente registrada e não são compiladas
  automaticamente pela pipeline USA. Demos ficam de fora. Veja [compatibilidade regional](docs/disc-import.md).
- **Nova tela de Acessibilidade:** seleção de texture packs e assistência aos controles no mesmo lugar. Texturas PNG
  no formato PCSX2 permitem modificar o visual do jogo; packs não acompanham o projeto e sua compatibilidade varia.
- **Teclado e mouse:** preservados os comandos segurados Ctrl + Espaço e Ctrl + WASD; esquiva padrão em Alt + WASD.
  Gestos opcionais de analógico (G por padrão) ajudam nos minijogos. Repetição de L1/L2/R1/R2 ativada individualmente.
- **Som nas cutscenes:** corrigido o áudio antigo de um vídeo que corrompia as vozes PT-BR do vídeo seguinte (patch 54).
  As correções anteriores de efeitos sonoros foram mantidas; isso não significa que toda cutscene ou transição esteja corrigida.
- **Tempo de compilação:** módulos IOP grandes divididos em partes paralelas (patch 55). No Xeon medido, a unidade mais
  demorada caiu de 126,5 s para 24,5 s; não é o tempo total da instalação. Reduzir mais esse tempo segue como meta rumo à 1.0.0.
- **Gráficos:** mantidos resolução interna, nitidez, FXAA e modo sem bordas para ferramentas externas.
  DLSS, inclusive DLSS 5, não está integrado. Veja [upscaling](#upscaling-e-ferramentas-externas).

A meta continua sendo **60 FPS reais do jogo estáveis**, com melhorias contínuas para computadores mais fracos.
As medições registradas não comprovam 60 FPS cravados em toda a categoria intermediária nem na campanha inteira.
Veja [hardware testado](docs/tested-hardware.md) e o [changelog completo da 0.5.0](CHANGELOG.pt-BR.md#v050--2026-11-02).

Configuração e diagnóstico: [Acessibilidade, assistência de teclado e texture packs](docs/accessibility.md) (em inglês).

### Download Linux experimental

Em [Releases](https://github.com/Vnnc1/gow-native-pc/releases), baixe
`gow-native-pc-linux-x86_64-ubuntu26.04-experimental.run` e seu `.sha256`, depois execute:

```sh
bash gow-native-pc-linux-x86_64-ubuntu26.04-experimental.run
bash "$HOME/.local/share/gow-native-pc-0.5.0/start-linux.sh"
```

Instale antes as dependências de sistema correspondentes; o pacote usa bibliotecas do Ubuntu 26.04 e não é um
AppImage universal. O instalador recusa pastas existentes para preservar jogos e saves. Importe sua própria imagem
compatível no launcher para recompilar o jogo. SteamOS e outras distribuições podem exigir recompilar o launcher;
veja [instalação e limites no Linux](docs/linux.md). No Windows, os passos abaixo usam `gow-native-pc-setup.exe`.

## Novidades da 0.4.0

> [!NOTE]
> **Vem da v0.3.1 ou anterior? Rode o setup da 0.4.0 uma vez por cima da sua instalação.** As versões foram
> renumeradas em 31/10/2026 (v1.0.0, v2.0.0, v3.0.0 e v3.0.1 agora são v0.1.0, v0.2.0, v0.3.0 e v0.3.1, os mesmos
> arquivos), e um launcher de antes da renumeração não enxerga a 0.4.0 como atualização. A compilação do jogo, os
> discos e os saves são mantidos; a partir da 0.4.0 as atualizações automáticas voltam a funcionar. Todas as versões:
> [`CHANGELOG.pt-BR.md`](CHANGELOG.pt-BR.md).

- **Perfil PGO na versão**: a instalação usa direto o perfil da versão — sem build instrumentado nem execução de
  treino — e CPUs de até 4 threads, que antes ficavam sem PGO, agora também recebem.
- **Modo VU rápida** (desligado por padrão; Launcher → Desempenho): código da VU1 sem as correções exatas de ponto
  flutuante, como nas configurações padrão do PCSX2. Cerca de 12% menos trabalho de VU1 num replay de combate gravado
  (patch 51 do runtime). Mais útil em CPUs mais lentas, onde a VU1 é o limite.
- **Segurar em vez de apertar sem parar** (acessibilidade, Launcher → Controles), por
  [ThisIsAkill](https://github.com/ThisIsAkill) (PR #10, patch 53).
- **Launcher em francês, alemão, italiano, russo e chinês simplificado**; o idioma do sistema é escolhido na primeira
  abertura.
- **Correções**: efeitos sonoros sumindo depois de uns 35 s de combate (patch 48); a tela rosa congelada quando o
  renderizador da GPU não inicia agora explica o motivo (sem OpenGL 4.3, driver genérico, Área de Trabalho Remota;
  patch 52); um script de instalação posto em quarentena pelo antivírus é avisado como tal, em vez de "Falhou (código
  1)"; instalações numa pasta com espaço no nome não falham mais.

## Novidades da 0.3.1

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
- **GPUs mais antigas**: placas cujo driver para no OpenGL 4.3–4.5 (como Intel HD 4000–4600) agora conseguem um
  contexto OpenGL para o renderizador por GPU, em vez de não conseguir iniciá-lo (patch 47).
- **Atualizações**: o aviso de "recompilar" só some depois de recompilar com o runtime novo, e o launcher recomenda
  retreinar o PGO depois de uma atualização.

Versões anteriores (0.3.0: Early FINISH, PGO na instalação, menu F1, JIT da VU1): [`CHANGELOG.pt-BR.md`](CHANGELOG.pt-BR.md).

## Obrigatório: o runtime PS2Recomp

Sem o runtime nada pode ser recompilado ou executado. Ele **não faz parte deste repositório**: **Instalar e compilar**
no launcher ou a etapa `fetch` do `build.cmd` o clona em `engine/runtime/` na versão fixada em
[`engine/runtime.toml`](engine/runtime.toml) (Tobiichi-Port, que reúne o PS2Recomp de ran-j com as extensões de
Waffle565 e KIexster) e aplica [`engine/patches`](engine/patches) (01–58 nesta versão).

## Requisitos

| | |
|---|---|
| Sistema | Windows 10/11 64 bits |
| CPU | x86-64 com SSE4.2 (x86-64-v2); AVX/AVX2 são usados pelo JIT da VU1 quando existem. 4 núcleos ou mais recomendados: CPUs de notebook com 2 núcleos/4 threads rodam o jogo devagar (veja [Desempenho](#desempenho)) |
| RAM | 8 GB (16 GB recomendados durante a compilação) |
| GPU | OpenGL 4.3+ (no 4.3 é preciso `NV_texture_barrier` ou `ARB_texture_barrier`, que os drivers das Intel HD 4000–4600 têm), com o driver do fabricante instalado. O renderizador por GPU é o único: sem OpenGL 4.3 (ou com o driver de vídeo genérico do Windows, ou pela Área de Trabalho Remota) a janela do jogo avisa isso em vez de mostrar o jogo |
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
No setup, use **Pasta da build → Alterar** para escolher um caminho local curto, como `D:\gow-build`
(até 40 caracteres). A mesma opção aparece ao atualizar uma instalação existente.
Alterar exige compilar novamente; os saves e a build anterior são preservados.
O instalador não move caches compilados do CMake. Atualizar sem escolher outra pasta mantém o caminho atual.

## Como usar

1. Obtenha o launcher:
   - **Instalador (mais fácil):** baixe `gow-native-pc-setup.exe` em
     [Releases](https://github.com/Vnnc1/gow-native-pc/releases), execute e clique em **INSTALAR** (sem permissão de
     administrador, só para o seu usuário). Ele cria atalhos no menu Iniciar / área de trabalho e uma entrada em
     *Aplicativos* do Windows para desinstalar.
2. No launcher → aba **Instalação**:
   1. **Baixar ferramentas** — cópias portáteis são baixadas uma vez, com verificação SHA-256, sem alterar seu PATH;
   2. **Adicionar ISO / CHD…** — escolha uma ou mais imagens compatíveis; o launcher identifica o jogo e o idioma;
   3. **Instalar e compilar** — baixa o runtime, prepara o disco e compila o jogo. Usa um perfil PGO da versão quando disponível (a 0.5.0 não inclui um). Deixe
      **Preparar a primeira jogatina (recomendado)** ligado: uma cópia do jogo se joga sozinha por quatro minutos,
      **escondida e sem som**, gravando o código de VU1/IOP que usa, e esse código é compilado no jogo.
3. Escolha um **perfil gráfico** (página Gráficos), confira os **Controles** se for jogar no teclado e clique em **JOGAR**.

A importação CHD verifica e extrai a imagem para um cache local de ISO, exigindo espaço adicional.
A imagem Asia fornecida, com executável idêntico ao USA, foi compilada e testada. As imagens Japan e Europe
verificadas já têm builds Windows separadas, testadas no início do jogo e selecionáveis no launcher após o registro.
Elas não usam a recompilação/PGO da USA. Demos continuam excluídas; a compatibilidade depende do conteúdo, não do nome.
Veja [formatos de disco e compatibilidade regional](docs/disc-import.md).

O tempo depende da CPU, da RAM, do disco e dos downloads; as ~6.400 funções recompiladas do jogo são compiladas no seu
PC. No PC de testes (Xeon E5-2666 v3, 20 threads, 16 GB) a instalação completa levava **cerca de 30 minutos** quando
ainda treinava o próprio perfil PGO (0.3.x). Um perfil distribuído compatível pode evitar esse treino, mas a v0.5.0 não inclui um.
Numa CPU de notebook com 2 núcleos/4 threads (i3-10110U) uma instalação levou **cerca de 75
minutos**. São referências históricas, não prazos. Um jogo instalado com uma versão anterior mostra **"Otimização de FPS
recomendada (PGO)"** na página Início.

### Pelo terminal

Execute na pasta do repositório (no PowerShell, use `.\build.cmd`):

```bat
build.cmd -Discs "D:\God of War (USA).iso" -Stages tools,fetch,discs,configure,recomp,sync,tune
```

É o que o launcher faz: ferramentas, runtime, preparação do disco, recompilação e a etapa `tune` (execução de gravação +
compilação final com o perfil PGO da versão; sem um perfil compatível, ela também treina um). Sem a preparação da primeira jogatina, use o padrão `build.cmd -Discs "D:\God of War (USA).iso"`.
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
| **F1 / Select + Start** | Menu com pausa: Gráficos, Controles, Áudio, Texture packs, Cheats, Saves |
| **F2** | Menu do jogo na aba Truques |
| **F11** | Tela cheia / janela (sem bordas, quando esse modo estiver escolhido) |
| **Ctrl+F1** | Depurador do runtime (para desenvolvedores) |

Mudanças suportadas de gráficos, áudio, controles e acessibilidade persistem e sincronizam com o launcher.
Opções do renderer lidas na inicialização ainda exigem reiniciar. Saves mostra slots do cartão ativo com local,
miniatura e horário; carregar descarta o progresso desde o último altar após confirmação. Restaurar o histórico
do cartão completo continua exigindo jogo fechado. Veja [documentação dos saves](docs/saves.md).

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

Por padrão, o jogo mantém o ritmo original de 60 Hz. Todas as medições, com o código e
os ajustes usados: [`docs/tested-hardware.md`](docs/tested-hardware.md). Os resultados variam entre máquinas — use-os
como referência.

Há um **experimento de lógica a 120/240** para testes de desenvolvimento, desativado por padrão.
Os testes locais no notebook não atingiram essas taxas de jogabilidade; a frequência de apresentação do host não é o FPS do jogo.
Veja [instruções, resultados e validações pendentes](docs/research/experimental-logic-rate.md).

No PC de testes do projeto, **Xeon E5-2666 v3 / 16 GB / Radeon RX 580 2048SP** (tela cheia 1080p, resolução interna 2×,
PGO, Early FINISH), o navio inicial fica em **cerca de 55 fps de média**, com trechos de combate pesado em torno de
**50–53 fps**; uma sessão de 30 minutos a partir de um save mais à frente teve média de 48 fps com memória estável.
**60 fps travados ainda não são alcançados**: o limite que resta é o trabalho da VU1 na CPU (cerca de 19 ms por quadro no
combate mais pesado; são necessários 16,7 ms). Baixar a resolução interna só ajuda quando a GPU é o limite.

Numa **CPU de notebook com 2 núcleos/4 threads (Core i3-10110U, Intel UHD Graphics)** a imagem sai correta, mas o jogo
fica lento: menus a 40–48 fps e **cerca de 20 fps em combate** no navio (resolução interna 1×, sem PGO, build de teste
da 0.4.0). O relatório de diagnóstico mostra a thread da VU1 ocupada mais de 90% do tempo, então o limite é a CPU, não
a GPU. O modo VU rápida deu cerca de 10% lá; builds com AVX2 (`-CpuTarget x86-64-v3`) foram medidos e não aceleram o
código da VU1. Relatos de outras máquinas são bem-vindos: ligue antes o **Diagnóstico de áudio e compilação**.

## Upscaling e ferramentas externas

- **Nativo:** resolução interna (o jogo desenha de verdade 2×, 3×… mais pixels), filtro nítido (bicúbico + nitidez
  adaptativa), FXAA e filtro anisotrópico — tudo em Launcher → Gráficos, a maior parte também ao vivo no menu F1.
- **DLSS (inclusive DLSS 5), FSR 2–3 e XeSS:** não integrados neste port. A opção sem bordas já existente
  permite ferramentas externas de captura/escala; ela não instala DLSS nem comprova compatibilidade com uma versão dessas ferramentas.
- **Ferramentas externas** como Lossless Scaling (escala / geração de quadros), ReShade (OpenGL) e OBS enxergam o jogo no
  modo **sem bordas** (Launcher → Gráficos → *Permitir ferramentas externas*). Não são testadas oficialmente e podem
  adicionar atraso; geração de quadros funciona melhor quando o jogo já roda num ritmo estável.

## Traduções e idiomas

A compatibilidade é verificada pelo **SHA-1 da seção `.text`** do executável em [`games/gow1/game.toml`](games/gow1/game.toml).
Traduções que preservam o código original podem ser aceitas mesmo sem uma edição cadastrada; o idioma é detectado pelos
textos do menu. Traduções que alteram código não podem usar esse pipeline. Regiões com código diferente precisam
de build própria validada e registrada; consulte a tabela de compatibilidade regional.

| ISOs escolhidas | Resultado |
|---|---|
| Original USA | Jogo em inglês |
| Tradução compatível | Jogo traduzido com os vídeos presentes nesse disco |
| Original USA + tradução compatível | Vídeos originais, inclusive widescreen, com textos traduzidos |

Com mais de um idioma, o launcher pergunta qual usar. Detalhes de compatibilidade e preparação do disco:
[`docs/translations.md`](docs/translations.md).

O próprio launcher está em inglês, português, espanhol, turco, francês, alemão, italiano, russo e chinês simplificado
(escolha na página Outros; na primeira abertura vale o idioma do sistema); o menu F1 do jogo tem textos em inglês,
português, espanhol e turco.

## Relatando problemas

O launcher guarda um relatório limitado de cada sessão. Use **Outros → Marcar um problema durante o jogo** quando algo
acontecer e depois **Outros → Relatório de testes e erros** ao fechar o jogo para exportar o ZIP. Revise e anexe o ZIP ao seu relato, com a área e os
passos para reproduzir. Nada é enviado automaticamente; arquivos do jogo e saves ficam de fora. Diagnósticos detalhados
são opcionais e podem reduzir o FPS. Veja [`docs/reporting-bugs.md`](docs/reporting-bugs.md).

## Limitações conhecidas

- 60 fps travados ainda não são alcançados no combate pesado (veja [Desempenho](#desempenho)).
- Só as áreas iniciais (o navio) foram medidas a fundo; áreas posteriores podem se comportar diferente.
- Pequenos engasgos com falhas de áudio ainda podem ocorrer em transições. O defeito reproduzido de alinhamento
  dos canais PT-BR foi corrigido pelo patch 54; outras cenas precisam de testes. Vídeos ausentes ou cortados em discos
  modificados podem exigir o disco original; veja [traduções](docs/translations.md).
- Alguns packs podem deixar inimigos transparentes. A interação observada entre pack e motor continua sem causa
  isolada; compare a mesma cena sem substituições ao relatar o problema.
- CPUs de notebook com 2 núcleos/4 threads rodam o jogo a cerca de 20 fps em combate (veja [Desempenho](#desempenho)).
- Se notar falhas de imagem, desligue **Antecipar o fim do quadro** (e a **VU rápida**, se a tiver ligado) em
  Launcher → Desempenho e relate.
- Linux experimental; Steam Deck, builds Linux regionais e compatibilidade ampla de GPU ainda não validados.

## Roadmap

O plano completo, com os critérios de medição de cada item: [`docs/research/roadmap-2026-10-27.md`](docs/research/roadmap-2026-10-27.md).

| Prioridade | Foco | Situação |
|---|---|---|
| 1 | Qualidade da compilação e da recompilação | Em grande parte feito na 0.3.0 (toolchain fixada, cache, verify, instalação mais rápida com PGO); próximo: instalação abaixo de 20 minutos |
| 2 | 60 fps estáveis | Early FINISH e PGO feitos; próximo: timing estático da VU1 (os ~14% que faltam no combate pesado) e instruções da VU1 ainda interpretadas |
| 3 | Áudio | Alinhamento PT-BR corrigido (patch 54); investigar outras cenas e transições |
| 4 | Mods e texture packs | Substituições no formato PCSX2 e patches xdelta de ISO implementados; ampliar compatibilidade e gestão de mods |
| 5 | Port para Linux | Pipeline nativa e instalador experimental implementados; validar Deck real e dependências portáteis |
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
