# Histórico de versões

[English](CHANGELOG.md) · **Português (Brasil)**

O que mudou de uma versão para a outra. As notas das releases no GitHub têm o mesmo texto, mais as instruções de
download e instalação; os patches do runtime estão listados um a um em [`engine/README.md`](engine/README.md).

## Numeração

As versões são `0.MENOR.CORREÇÃO` ([Versionamento Semântico](https://semver.org/lang/pt-BR/) para um projeto que ainda
não está pronto):

- **MENOR** (0.**4**.0) sobe numa versão com recursos novos ou ganho de desempenho. Pode pedir para recompilar o jogo.
- **CORREÇÃO** (0.3.**1**) sobe numa versão só com correções de bugs.
- **1.0.0** fica reservada para o port completo: o jogo inteiro jogável a 60 fps travados, sem bugs graves conhecidos.

A tag de uma versão é `v` + o número, e o launcher dentro dela informa o mesmo número: a verificação de atualizações do
launcher compara os dois.

**Renumeração (31/10/2026).** As primeiras versões tinham as tags v1.0.0, v2.0.0, v3.0.0 e v3.0.1, enquanto os títulos
diziam v0.0.x. Agora são v0.1.0, v0.2.0, v0.3.0 e v0.3.1, com os mesmos arquivos e conteúdo. Um launcher dessas versões
(ele informa de 1.0.0 a 3.0.1) não enxerga as versões 0.x como mais novas: **instale a v0.4.0 uma vez pelo setup, por
cima da instalação atual**; daí em diante as atualizações automáticas voltam a funcionar. A compilação do jogo, os
discos e os saves são mantidos.

## [v0.5.0] — 2026-11-02

### Novidades
- **Distribuição Linux experimental:** launcher e coletor nativos, pipeline Linux, pacote verificado de fontes/binários
  e instalador autoextraível `.run`. Destinada a testes em dispositivos Linux e Steam Deck; compilada e testada
  inicialmente no Ubuntu 26.04 via WSL. Usa bibliotecas do sistema; SteamOS, Deck real e desempenho ainda não validados.
- **Importação de CHD para recompilação:** imagens CHDv5 suportadas são verificadas e convertidas para um cache de ISO,
  passando pelas mesmas verificações de compatibilidade do executável. Exige espaço extra e preserva a imagem original.
- **Regiões:** EUA e a imagem Asia testada, com código idêntico ao USA; builds Windows isoladas de Japão `SLPM_670.10`
  e Europa `SCES_531.33`, validadas no navio inicial. O launcher seleciona builds correspondentes registradas e separa
  seus saves. Uma instalação nova não recompila automaticamente discos de código diferente pela pipeline USA.
  Outros seriais e a campanha completa ainda não foram validados; demos são excluídas.
- **Nova tela de Acessibilidade:** texture packs e assistência aos controles em uma página própria. As substituições
  PNG no formato PCSX2 já existentes permitem personalizar o visual; nenhum pack acompanha o projeto.
- **Assistência de analógico no teclado:** tecla segurada opcional para alternar direções ou girar (G por padrão),
  interrompida ao soltar/perder foco, sem alterar gamepads conectados. Repetição de L1/L2/R1/R2 ativada individualmente.
- **Mods de ISO:** aplicação verificada de patches xdelta/VCDIFF em uma nova imagem, preservando o disco de origem.

### Correções
- **Áudio das cutscenes:** pacotes restantes de um vídeo não corrompem mais o alinhamento dos canais e as vozes PT-BR
  do vídeo seguinte (patch 54). A cena PT-BR medida passou a corresponder à faixa original dentro do erro de arredondamento;
  USA permaneceu inalterada. Mantidas as correções anteriores de efeitos sonoros sumindo. Outras cenas ainda precisam de testes.
- **Combinações de teclado seguradas:** Ctrl + Espaço e Ctrl + WASD preservam os botões do jogo; esquiva padrão em
  Alt + WASD. A repetição de QTE pausa durante combinações para não interromper ações seguradas (patches 57–58).
- **Inicialização Linux:** discos preparados recebem aliases IOP em minúsculas para caminhos sensíveis a maiúsculas.
  O coletor registra CPU/memória RSS no Linux, com testes de falha apropriados à plataforma.

### Compilação e desempenho
- Módulos IOP nativos compilados em partes paralelas (patch 55). No teste Xeon/Clang registrado, a unidade mais demorada
  caiu de **126,5 s para 24,5 s**; não é o tempo da instalação completa nem uma comparação entre máquinas diferentes.
- Reduzir mais o tempo de recompilação e melhorar PCs mais fracos seguem como metas rumo à v1.0.0, sem prazo ou duração
  prometidos. Mantidas as melhorias de VU1/PGO; as medições não comprovam 60 FPS cravados em toda a categoria intermediária
  nem na campanha completa. Veja [evidências por hardware](docs/tested-hardware.md).
- O pacote Windows v0.5.0 **não inclui perfil PGO pré-treinado**; o treinamento local continua disponível.

### Gráficos e limitações restantes
- Mantidos resolução interna, filtro nítido, FXAA, anisotropia e modo sem bordas para ferramentas externas.
  **DLSS, inclusive DLSS 5, não está integrado**; escala/geração de quadros externa não equivale a suporte nativo a DLSS.
- Inimigos transparentes foram reproduzidos com um pack; ainda não foi isolado se a causa está nos arquivos ou no
  tratamento pelo renderizador. Não foi aplicada uma correção geral de transparência.
- Os testes Linux chegaram ao gameplay inicial com renderização por software no WSL. Steam Input, suspensão,
  desempenho de GPU real e builds Linux Japão/Europa ainda precisam de validação. Veja [Linux](docs/linux.md) e
  [compatibilidade dos discos](docs/disc-import.md).

## [v0.4.0] — 2026-10-31

Mudanças desde a v0.3.1 na branch de desenvolvimento.

### Novidades
- **Modo VU rápida** (desligado por padrão; Launcher → Desempenho): código da VU1 sem as limpezas exatas de ponto
  flutuante, como as configurações padrão do PCSX2. Cerca de 12% menos trabalho da VU1 no combate; diferenças pequenas e
  raras em relação ao modo exato (patch 51).
- **Segurar em vez de apertar sem parar** (acessibilidade, desligado por padrão; Launcher → Controles): nos minijogos
  que pedem apertos repetidos, segurar o botão aperta por você; um toque curto continua sendo um só. Por
  [ThisIsAkill](https://github.com/ThisIsAkill) (PR #10, patch 53).
- **Launcher em francês, alemão, italiano, russo e chinês simplificado**, além de inglês, português, espanhol e
  turco; o idioma do sistema é escolhido na primeira abertura. O menu F1 do jogo fica em inglês nesses idiomas.
- As versões podem trazer um perfil da otimização guiada por perfil (PGO) treinado exatamente no runtime e nos patches
  delas.
- `tools/pipeline/patches.ps1`: a pilha de patches do runtime como commits do git, para movê-la para um commit mais novo
  do runtime.

### Desempenho
- Os caminhos de depuração e gravação do interpretador da VU1 não reservam mais quadros de pilha grandes a cada programa
  da VU1 (patch 50).

### Correções
- **Tela rosa congelada quando o renderizador da GPU não inicia** (sem OpenGL 4.3: GPU antiga, o Adaptador de Vídeo
  Básico da Microsoft, Área de Trabalho Remota; ou um driver que recusa os shaders): a janela agora diz o motivo e o
  que fazer (patch 52).
- **"O termo ...\build.ps1 não é reconhecido" na instalação**: um antivírus tinha removido o script da pipeline
  enquanto ele iniciava. O launcher agora avisa que um arquivo foi removido e como restaurá-lo, em vez de "Falhou
  (código 1)".
- **Efeitos sonoros sumindo em lutas longas**: as vozes liberadas agora caem até zero e liberam o espaço; antes, as
  vozes de efeitos lotavam depois de uns 35 s de combate e os golpes ficavam mudos até trocar de área (patch 48).
- **A instalação falhava numa pasta com espaço no nome** (por exemplo `E:\God of War`): o caminho do perfil PGO era
  cortado no primeiro espaço e toda compilação falhava ("sccache: Failed to open file for hashing").
- Instalar pelo setup por cima de uma versão anterior agora pede para recompilar o jogo quando os patches do runtime
  mudam, como já acontecia nas atualizações pelo launcher.

## [v0.3.1] — 31/10/2026

Antes v3.0.1. 7 commits desde a v0.3.0.

### Desempenho
Medido no PC de teste (Xeon E5-2666 v3 + RX 580, tela cheia, rota do save, pares alternados).
- Código da VU1 gerado mais enxuto, com resultado idêntico bit a bit: média de ~51 para **~57 fps**, combate pesado de
  ~51 para **~55 fps** (patch 43).
- Envio sem lock para a thread do estágio do GS: ~150 mil despertares de thread a menos por segundo, combate +3,5%
  (patch 44).
- Decodificação da VU1 sob demanda e uma cópia a menos por pacote GIF, do fork
  [gow-native-pc-optimization](https://github.com/huanghuangdaquan-beep/gow-native-pc-optimization) (patches 45–46).

### Novidades
- O instalador confere o SSE4.2 e avisa CPUs sem suporte antes de instalar.
- CPUs de até 4 threads instalam sem a etapa da otimização guiada por perfil (dá para rodar depois) e com um compilador
  a mais em paralelo.

### Correções
- GPUs com driver até OpenGL 4.3–4.5 (Intel HD 4000–4600 e outras) usam o renderizador por GPU em vez do renderizador
  por software, muito mais lento (patch 47).
- As dependências são baixadas uma vez só e sem histórico: a etapa do PGO não baixa mais ~1 GB de novo.
- O aviso de "recompilar" só some depois de recompilar com o runtime novo; depois de uma atualização, o launcher
  recomenda treinar o perfil de novo.

## [v0.3.0] — 31/10/2026

Antes v3.0.0. 28 commits desde a v0.2.0.

### Desempenho
Medido no PC de teste (tela cheia 1080p, resolução interna 2×).
- Combate mais pesado do navio de ~40 para **50–53 fps**; média do navio ~55 fps.
- **Early FINISH**: o jogo prepara o próximo quadro enquanto a VU1 desenha o atual, cerca de +20% no combate pesado.
- **A otimização guiada por perfil faz parte da instalação** (etapa `tune`): cerca de +5% na média e +13% no combate.
- **JIT x86-64 da VU1**: áreas sem código da VU1 gravado são compiladas durante o jogo (patches 18 e 27).
- Chamadas JAL/JALR mais enxutas e caminhos rápidos de memória (patches 28–35).

### Novidades
- **Menu F1 no jogo**: aba Gráficos ao vivo, aba Truques (F2) e aba Save; o depurador do runtime foi para Ctrl+F1.
- Launcher: perfis gráficos (Desempenho / Equilibrado / Qualidade), tela cheia sem bordas, seção "Upscaling e
  ferramentas", página Saves, estado do PGO e relatórios de sessão para relatar bugs.
- Preparação da primeira jogatina + PGO em ~24 minutos, contra ~63 antes; testes de regressão `build.cmd -Stages verify`.

### Correções
- Correção de memória/DMA, overflow na mixagem de áudio (SPU2), execução direta do jogo, placeholders dos vídeos em
  widescreen.
- O FXAA não desliga mais o filtro nítido; opções que não faziam nada foram removidas.

## [v0.2.0] — 25/10/2026

Antes v2.0.0 (o launcher dela informa 2.1.0). 15 commits desde a v0.1.0.

### Novidades
- **O clang (llvm-mingw) passa a ser o compilador**: o jogo compila em ~15 minutos, contra 45–60 com o MSVC; não precisa
  mais de Visual Studio, Git nem Python.
- **Instalação em três passos**: ferramentas portáteis → ISO → instalar. Nova tela de carregamento com uma barra só e o
  tempo restante.
- Controle remapeável botão por botão (patch 14) e proporção 32:9.
- **Atualizações do launcher pelas Releases do GitHub.**
- Otimização guiada por perfil opcional (Instalar → Mais opções).

### Desempenho
- Combate do navio com roteiro: mínimo de 51,4 para 54,6 fps, média de 56,5 para 58,4 fps (clang + PGO).
- VU1 sem limpezas de ponto flutuante desnecessárias e com blocos encadeados (patches 10 e 13); som mixado em lotes; o
  heap do IOP reaproveita memória liberada (patch 11).

### Correções
- Compilação a partir de pendrive / exFAT; verificação do Python; o launcher relê o caminho do jogo depois de compilar.

## [v0.1.0] — 25/10/2026

Antes v1.0.0. 12 commits: a primeira versão.

### Novidades
- Pipeline de compilação com perfis por jogo, setup de arquivo único (sem administrador) com desinstalador, launcher.
- Traduções de fãs aceitas pelo idioma, com escolha do idioma quando há várias ISOs.
- Opção de filtragem anisotrópica.

### Desempenho
- Combate do navio com roteiro e as opções padrão: média de ~48 para ~58 fps (todo bloco da VU1 como código nativo,
  gravação da VU1 barata, mixagem de som mais rápida, geração de código "register locals", patches 08–09).

### Correções
- Correções de imagem em resolução interna alta, vindas do port nativo do God of War II; tradução de MOVZ/MOVN; memória
  do runtime fora do heap do jogo; áudio dos vídeos; saves no memory card mais rápidos; os patches do runtime mantêm as
  quebras de linha.

[v0.5.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.5.0
[v0.4.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.4.0
[v0.3.1]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.3.1
[v0.3.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.3.0
[v0.2.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.2.0
[v0.1.0]: https://github.com/Vnnc1/gow-native-pc/releases/tag/v0.1.0
