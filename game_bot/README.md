# Game Bot (visão computacional + automação externa de mouse)

Bot externo em Python para um jogo simples controlado apenas pelo botão
esquerdo do mouse (clique = pulo). O bot **apenas olha a tela** (captura
via MSS + OpenCV) e **simula cliques externamente** (via pydirectinput).

Não há leitura/escrita de memória do processo do jogo, injeção de DLL,
nem qualquer acesso a arquivos ou processos internos do jogo — somente
visão computacional e automação externa de input, adequado para uso
acadêmico.

## Estrutura do projeto

```
game_bot/
├── bot.py             # programa principal
├── calibrate_hsv.py   # ferramenta de calibração de cores HSV
├── config.py          # todas as configurações/constantes
├── requirements.txt   # dependências
└── README.md
```

## Dependências

```
pip install -r requirements.txt
```

ou manualmente:

```
pip install opencv-python numpy mss pydirectinput keyboard
```

Notas para Windows:
- `pydirectinput` usa `SendInput` do Windows e funciona bem com a
  maioria dos jogos (melhor que `pyautogui` para jogos, que muitas
  vezes ignoram eventos sintéticos do `pyautogui`).
- A biblioteca `keyboard` no Windows normalmente precisa ser executada
  com privilégios suficientes para capturar teclas globalmente. Se as
  teclas 1/2/3 não funcionarem fora da janela do OpenCV, tente rodar o
  terminal/VS Code como Administrador.

## Como executar

1. Crie uma pasta para o projeto e copie os arquivos deste diretório
   para dentro dela (ou use `game_bot/` como está).
2. (Recomendado) Crie um ambiente virtual:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
3. Instale as dependências:
   ```
   pip install -r requirements.txt
   ```
4. Abra o jogo na tela, na posição onde ele vai ficar durante o uso.
5. Rode o calibrador de cor do jogador:
   ```
   python calibrate_hsv.py --target player
   ```
   Ajuste os sliders H/S/V até que **apenas** o personagem apareça
   branco na janela `mask`, com o mínimo de ruído possível. Pressione
   `Q` ou `ESC` para ver os valores finais impressos no terminal.
6. Copie os valores impressos (`PLAYER_HSV_MIN` / `PLAYER_HSV_MAX`)
   para dentro de `config.py`.
7. Repita o processo para os obstáculos. No jogo das palmeiras (tronco
   marrom + folhas verdes + carinhas amarelas), uma única faixa de cor
   normalmente não cobre o obstáculo inteiro, então calibre **cada
   parte separadamente**:
   ```
   python calibrate_hsv.py --target obstacle_tronco
   python calibrate_hsv.py --target obstacle_folhas
   python calibrate_hsv.py --target obstacle_carinha
   ```
   Cada execução imprime uma linha pronta (ex: `([10, 60, 40], [25,
   255, 200]),`) para colar dentro da lista `OBSTACLE_HSV_RANGES` em
   `config.py`. O bot une (OR) as máscaras de todas as faixas
   cadastradas e depois "cola" as partes próximas com fechamento
   morfológico (`OBSTACLE_MERGE_KERNEL`), tratando tronco + folhas +
   carinha como um único obstáculo.

   Se o seu obstáculo tiver só uma cor dominante e simples, pode usar
   o modo antigo de faixa única:
   ```
   python calibrate_hsv.py --target obstacle
   ```
   e copiar `OBSTACLE_HSV_MIN` / `OBSTACLE_HSV_MAX` para `config.py`,
   deixando `OBSTACLE_HSV_RANGES = []` (vazio).
8. Ajuste `GAME_REGION` em `config.py` para a posição exata (top,
   left, width, height) da janela/área do jogo na sua tela.
9. Rode o bot:
   ```
   python bot.py
   ```
10. Pressione **1** para ativar o bot, **2** para pausar, **3** para
    encerrar. Esses controles funcionam mesmo sem a janela do OpenCV
    estar em foco.

## Lógica resumida

1. **Captura**: MSS captura só a região `GAME_REGION` a cada frame.
2. **Detecção do jogador**: filtro HSV + contornos, com preferência
   pelo candidato mais próximo da última posição conhecida (evita
   trocar de alvo com outro objeto da mesma cor). Se nada plausível for
   encontrado perto da posição anterior, o bot assume que perdeu o
   jogador (comportamento conservador: não clica).
3. **Detecção de obstáculos**: mesmo princípio, com filtro de área e
   morfologia para reduzir ruído.
4. **Passagem segura (`find_target`)**: os obstáculos à frente do
   jogador são agrupados em "colunas"; dentro da coluna mais próxima,
   o bot calcula os espaços livres entre obstáculos (e entre eles e as
   bordas da tela) e escolhe o maior gap como a abertura por onde o
   personagem deve passar. O centro dessa abertura é o alvo
   (`target_x`, `target_y`).
5. **Velocidade**: a diferença de posição vertical entre frames é
   suavizada com uma média móvel (`VELOCITY_HISTORY_LEN` amostras),
   classificando o estado em `SUBINDO`, `CAINDO` ou `TOPO DO SALTO`.
6. **Decisão (`should_jump`)**: se o jogador está caindo e já alcançou
   (ou passou) o centro vertical da abertura, o bot pula. Se o
   obstáculo está muito próximo horizontalmente (situação "urgente"),
   o bot antecipa o pulo um pouco antes de chegar exatamente no centro.
   Enquanto o jogador está subindo, o bot espera.
7. **Clique**: `pydirectinput.click(button="left")` executa um clique
   único (não segura o botão), respeitando um cooldown mínimo
   (`CLICK_COOLDOWN`) entre cliques.
8. **Debug visual**: a janela do OpenCV desenha bounding boxes do
   jogador (verde) e obstáculos (vermelho), a abertura escolhida
   (linhas amarelas), o alvo (ponto azul), a trajetória recente do
   jogador (magenta) e um painel de texto com estado, velocidade, FPS
   e a ação decidida em cada frame.

## Controles (teclado global)

| Tecla | Ação |
|-------|------|
| 1     | Ativa o bot (`bot_active = True`) |
| 2     | Pausa o bot (`bot_active = True` → `False`), continua mostrando a visão |
| 3     | Encerra: solta o mouse, fecha as janelas OpenCV e finaliza o programa |

Cada pressionamento dispara a ação **uma única vez**: o hook de
teclado detecta a transição "solta → pressionada" (`KEY_DOWN`) por
tecla e ignora eventos repetidos enquanto ela continua pressionada,
até o próximo `KEY_UP`.

## O que você provavelmente vai precisar calibrar

- **`GAME_REGION`**: posição/tamanho exatos da janela do jogo na tela.
- **`PLAYER_HSV_MIN` / `PLAYER_HSV_MAX`**: cor do personagem (use
  `calibrate_hsv.py --target player`).
- **`OBSTACLE_HSV_MIN` / `OBSTACLE_HSV_MAX`**: cor dos obstáculos (use
  `calibrate_hsv.py --target obstacle`).
- **`PLAYER_MIN_AREA` / `OBSTACLE_MIN_AREA`**: dependem da resolução e
  do zoom da captura.
- **`MAX_PLAYER_JUMP_DISTANCE`**: depende da velocidade do jogo e do
  FPS real de captura.
- **`TARGET_MARGIN`, `URGENT_DISTANCE_PX`, `VELOCITY_DEADZONE`**: afinam
  o "timing" da decisão de pulo — ajuste observando a janela de debug.
- **`MIN_GAP_HEIGHT`**: altura mínima de abertura considerada válida.

Os valores em `config.py` são apenas exemplos aproximados — **não**
foram calibrados para nenhum jogo específico.

## Melhorias futuras (arquitetura já preparada)

A detecção (`detect_player` / `detect_obstacles`) está separada da
lógica de decisão (`find_target` / `should_jump`). Isso permite trocar
o método de detecção sem reescrever a lógica do bot:

- **Template Matching**: capture uma imagem pequena do personagem
  (`player_template.png`) e substitua `detect_player` por uma busca com
  `cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)`, pegando a
  posição de maior correlação acima de um limiar. Útil quando a cor do
  personagem varia (animações, iluminação).
- **ORB / features**: para detectar o personagem mesmo com rotação ou
  variações maiores de aparência, usando `cv2.ORB_create()` e
  correspondência de descritores contra uma imagem de referência.
- **YOLO**: no futuro, `detect_player` e `detect_obstacles` poderiam
  chamar um modelo YOLO treinado (`model(frame)`) e converter as caixas
  detectadas para o mesmo formato de dicionário (`x, y, w, h, cx, cy`)
  já usado hoje — o restante do pipeline (`find_target`,
  `calculate_velocity`, `should_jump`, `draw_debug`) não precisaria
  mudar.

Outras ideias de evolução, para depois do MVP estar estável:
- Estimar a força/altura média de cada salto observando os primeiros
  frames após um clique.
- Ativar `ENABLE_PREDICTION` em `config.py` e usar `predict_player_y()`
  para antecipar ainda mais o clique com base em posição + velocidade
  + gravidade estimada (já implementado, desativado por padrão porque
  pode deixar o bot instável até a física estimada ser bem calibrada).
- Formalizar uma máquina de estados explícita (`SEARCHING_PLAYER`,
  `ASCENDING`, `FALLING`, `JUMP_REQUIRED`, `WAITING`) em vez de strings
  soltas, se a lógica crescer.
- Um controlador tipo PID sobre o erro vertical (`target_y - player_y`)
  em vez de uma regra por limiares.
- Reinforcement learning, usando a mesma captura de tela como
  observação e o clique como ação — só faz sentido depois que a
  detecção estiver robusta o bastante para gerar recompensas
  confiáveis.

## Sobre performance / FPS

`FPS_LIMIT` em `config.py` limita o loop principal (por padrão 60) para
não consumir CPU desnecessariamente. Se a captura com MSS conseguir
manter uma taxa maior de forma estável e você quiser reação mais
rápida, pode definir `FPS_LIMIT = None` para não limitar — nesse caso
o gargalo passa a ser a velocidade real de captura + processamento
OpenCV na sua máquina.
