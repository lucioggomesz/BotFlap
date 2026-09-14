"""
config.py
=========
Configuracao central do bot.

Todos os valores que precisam ser calibrados/ajustados ficam aqui,
para nao ser necessario procurar constantes espalhadas pelo codigo.

IMPORTANTE:
Os valores de HSV (PLAYER_HSV_MIN/MAX e OBSTACLE_HSV_MIN/MAX) abaixo
sao apenas EXEMPLOS aproximados. Eles quase certamente NAO vao
funcionar direto no seu jogo. Use o script `calibrate_hsv.py` para
descobrir os valores corretos observando a imagem real do jogo.
"""

# ==================================================
# REGIAO DE CAPTURA DE TELA
# ==================================================
# Ajuste estes valores para a posicao/tamanho exatos da janela do jogo
# na sua tela. Pode usar uma ferramenta de captura (ex: Snipping Tool)
# para descobrir as coordenadas.
GAME_REGION = {
    "top": 64,
    "left": 231,
    "width": 817,
    "height": 606,
}

# ==================================================
# HSV DO PERSONAGEM (JOGADOR)
# ==================================================
# Valores de EXEMPLO. Calibrar com calibrate_hsv.py --target player
PLAYER_HSV_MIN = [20, 80, 80]
PLAYER_HSV_MAX = [35, 255, 255]

# ==================================================
# HSV DOS OBSTACULOS
# ==================================================
# Valores de EXEMPLO. Calibrar com calibrate_hsv.py --target obstacle
# Usados como fallback caso OBSTACLE_HSV_RANGES esteja vazio.
OBSTACLE_HSV_MIN = [5, 60, 40]
OBSTACLE_HSV_MAX = [20, 255, 200]

# No jogo das palmeiras (tronco marrom + folhas verdes + carinhas
# amarelas), uma unica faixa HSV normalmente NAO cobre o obstaculo
# inteiro. Preencha OBSTACLE_HSV_RANGES com uma faixa por "parte" do
# obstaculo (tronco, folhas, carinhas...) calibrando cada uma com:
#     python calibrate_hsv.py --target obstacle_tronco
#     python calibrate_hsv.py --target obstacle_folhas
#     python calibrate_hsv.py --target obstacle_carinha
# As mascaras de todas as faixas listadas aqui sao unidas (OR) antes
# de procurar os contornos. Se a lista ficar vazia, o codigo usa
# OBSTACLE_HSV_MIN/MAX acima como faixa unica.
OBSTACLE_HSV_RANGES = [
    # ([h_min, s_min, v_min], [h_max, s_max, v_max]),
    # ([10, 60, 40], [25, 255, 200]),   # exemplo: tronco marrom
    # ([35, 60, 80], [85, 255, 255]),   # exemplo: folhas verdes
    # ([20, 80, 150], [35, 255, 255]),  # exemplo: carinhas amarelas
]

# Kernel de fechamento usado para "colar" as partes do obstaculo
# (tronco + folhas + carinhas) em um unico contorno, mesmo que fiquem
# levemente separadas apos a uniao das mascaras. Costuma precisar ser
# mais alto que largo, pois as partes ficam empilhadas verticalmente.
OBSTACLE_MERGE_KERNEL = (9, 25)

# ==================================================
# FILTROS DE DETECCAO DO JOGADOR
# ==================================================
# Area minima (em pixels) para um contorno ser considerado o jogador.
PLAYER_MIN_AREA = 150

# Faixa aceitavel de proporcao largura/altura do bounding box do jogador.
# Usado para descartar contornos com formato muito diferente do esperado.
PLAYER_ASPECT_RATIO_RANGE = (0.3, 3.0)

# Distancia maxima (em pixels) que o jogador pode "teleportar" entre um
# frame e outro. Se a deteccao mais proxima estiver mais longe que isso
# da ultima posicao conhecida, ela e descartada (evita trocar de alvo
# por engano com outro objeto da mesma cor).
MAX_PLAYER_JUMP_DISTANCE = 120

# Faixa horizontal (em pixels, relativa a regiao capturada) onde o
# personagem costuma ficar. Use None para desativar esse filtro.
# Ex: (50, 250) restringe a busca do jogador a essa faixa de X.
PLAYER_SEARCH_X_RANGE = None

# ==================================================
# FILTROS DE DETECCAO DE OBSTACULOS
# ==================================================
OBSTACLE_MIN_AREA = 300
OBSTACLE_MIN_WIDTH = 10
OBSTACLE_MIN_HEIGHT = 10

# ==================================================
# LOGICA DE PASSAGEM / ZONA SEGURA
# ==================================================
# Obstaculos com borda direita (x + w) menor que player_x - esta margem
# sao considerados "para tras" e ignorados ao procurar o proximo alvo.
OBSTACLE_BEHIND_MARGIN = 20

# Obstaculos cuja distancia horizontal entre si seja menor ou igual a
# este valor sao agrupados na mesma "coluna" de obstaculo.
COLUMN_CLUSTER_GAP = 40

# Altura minima de abertura (gap) para ser considerada uma passagem
# segura confiavel. Gaps menores que isso sao ignorados.
MIN_GAP_HEIGHT = 40

# Margem de tolerancia (pixels) usada na decisao de pulo em torno do
# centro do alvo.
TARGET_MARGIN = 15

# ==================================================
# MOVIMENTO / VELOCIDADE
# ==================================================
# Quantidade de amostras de velocidade usadas na media movel para
# suavizar ruido de deteccao.
VELOCITY_HISTORY_LEN = 5

# Velocidade (px/frame) abaixo da qual consideramos o jogador
# praticamente parado (topo do salto).
VELOCITY_DEADZONE = 1.5

# Distancia horizontal (px) ate o proximo obstaculo a partir da qual
# consideramos a situacao "urgente" (o bot antecipa o pulo).
URGENT_DISTANCE_PX = 160

# ==================================================
# PREVISAO DE MOVIMENTO (OPCIONAL - desativado por padrao)
# ==================================================
ENABLE_PREDICTION = False
GRAVITY_ESTIMATE = 0.6          # px/frame^2, estimativa grosseira
PREDICTION_FRAMES_AHEAD = 5

# ==================================================
# CLIQUE / COOLDOWN
# ==================================================
CLICK_COOLDOWN = 0.10  # segundos minimos entre cliques

# ==================================================
# DESEMPENHO
# ==================================================
FPS_LIMIT = 60   # None para nao limitar

# ==================================================
# DEBUG / VISUAL
# ==================================================
DEBUG = True

COLOR_PLAYER = (0, 255, 0)          # verde
COLOR_OBSTACLE = (0, 0, 255)        # vermelho
COLOR_TARGET = (255, 0, 0)          # azul
COLOR_SAFE_ZONE = (0, 255, 255)     # amarelo
COLOR_TEXT = (255, 255, 255)        # branco
COLOR_TRAJECTORY = (255, 0, 255)    # magenta

# Quantidade de posicoes anteriores do jogador desenhadas na tela.
TRAJECTORY_LEN = 20

# Kernels de morfologia usados na limpeza das mascaras HSV.
MORPH_OPEN_KERNEL = (3, 3)
MORPH_CLOSE_KERNEL = (5, 5)
