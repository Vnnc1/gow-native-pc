# Kit privado de diagnóstico

Este instalador inclui uma versão já compilada do jogo e um coletor de diagnóstico.
Não inclui os arquivos do disco. É uma base para medir os problemas, sem promessa
de ganho de FPS. Requer Windows 10/11 de 64 bits e CPU com SSE4.2 e POPCNT.

1. Instale em sua pasta própria, sem substituir a instalação normal.
2. Abra **God of War Native PC - Diagnostico** e selecione o executável original
   indicado na tela, dentro da pasta do jogo já extraído pela instalação normal.
   A versão USA e traduções com código compatível são aceitas; Europa/Japão não.
3. No notebook, conecte à tomada. Mantenha escala 1× e VU rápida desmarcada.
4. Execute **Teste leve**. Carregue seu save e jogue por pelo menos dois minutos na
   cena problemática. Use Alt+Tab para anotar o local e clicar em **Marcar queda**.
5. Feche o jogo ou use **Encerrar teste**, espere o resumo e **Exporte o ZIP**.
6. Repita a mesma cena em **Diagnóstico detalhado**, mantendo a configuração.
   Exporte outro ZIP. Esse modo acrescenta temporização e pode reduzir o FPS;
   não compare seu FPS diretamente com o modo leve.
7. Envie os dois ZIPs e diga em qual trecho apareceu o problema, se estava na
   tomada e se havia outros programas abertos. Nada é enviado automaticamente.

O cartão `Mcd001.ps2` que estiver ao lado do executável escolhido é copiado para
o kit antes de cada teste. O original permanece intacto. Sem esse cartão, a sessão
começa com um cartão novo. Os saves feitos no teste ficam na cópia privada e não
passam automaticamente à instalação normal. O kit não possui save states.

O coletor continua funcionando se a janela do kit for fechada. Abra o kit novamente
para encerrar ou exportar a sessão. Relatórios e cartões particulares ficam em
`%LOCALAPPDATA%/gow-native-pc-diagnostics/DiagnosticKit/`. O botão de relatórios
abre a pasta correspondente. Os arquivos têm limites de tamanho; sessões muito
longas podem truncar a coleta. Exporte cada teste antes de começar outro.

`RESUMO.txt` apresenta FPS, intervalos do jogo, memória e indícios encontrados.
`summary.json` permite comparar os testes; `metrics.jsonl` preserva as medições,
`events.jsonl` guarda os marcadores e os logs mostram a execução. O ZIP não contém
ISO, arquivos extraídos, saves ou capturas. Revise as anotações antes de compartilhar.

Os primeiros 30 segundos ficam fora da média resumida. Menus/carregamentos após
esse período ainda entram na média: anote quando chegou à cena. Tempos de VU1,
GS e filas podem se sobrepor e não devem ser somados como tempo de quadro. CPU
usa um processador lógico como 100%. Ausência de métrica significa indisponível.
Os alertas são pistas, não confirmação automática da causa. A GPU registrada é
a escolhida pelo contexto gráfico do jogo, não uma medição de sua ocupação.

O executável de cada kit é identificado pelo SHA-256 em `diagnostic-kit.json`
e em cada relatório. A revisão com o patch 60 controla o cache de texturas e
reutiliza seu armazenamento; ambas as mudanças funcionam automaticamente nos
dois modos de teste. O modo detalhado também registra `[gs-cache]`: bytes de
texturas residentes, orçamento, descartes e atualizações que reutilizaram espaço.
Esse contador não representa toda a memória do processo ou do driver.
Os 60 FPS em notebooks e máquinas mais fracas ainda precisam ser validados nesses PCs.

A revisão com o patch 61 evita uma espera da janela pelo publicador de imagens
quando essa trava está ocupada. A imagem anterior permanece válida até haver uma
nova pronta. Isso corrige uma fonte de atraso; não comprova a solução de todas as
quedas ou do input lag. O kit não inclui FSR da AMD. Para comparar placas, mantenha
a mesma escala e cena nos dois testes e marque o trecho da queda.
