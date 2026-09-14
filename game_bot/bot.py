"""
bot.py
======
Bot externo para um jogo simples controlado apenas pelo clique esquerdo
do mouse (pular). O bot usa apenas visao computacional (captura de tela
+ OpenCV) e automacao externa de mouse (pydirectinput). Nao ha leitura
de memoria do processo do jogo, nem injecao de DLL, nem qualquer acesso
interno ao jogo.

Fluxo principal (ver main()):

    capturar tela
        -> detectar jogador
        -> detectar obstaculos
        -> encontrar proxima passagem segura
        -> calcular velocidade do jogador
        -> decidir se deve pular
        -> clicar ou esperar
        -> desenhar debug
        -> repetir

Controles (funcionam globalmente, mesmo com a janela do OpenCV sem foco):
    1 = ativa o bot
    2 = pausa o bot
    3 = encerra o programa
"""

import sys
import time
from collections import deque

import cv2
import numpy as np
import mss

try:
    import pydirectinput
except ImportError:
    print("[ERRO] Biblioteca 'pydirectinput' nao encontrada. "
          "Instale com: pip install pydirectinput")
    sys.exit(1)

try:
    import keyboard
except ImportError:
    print("[ERRO] Biblioteca 'keyboard' nao encontrada. "
          "Instale com: pip install keyboard")
    sys.exit(1)

import config as cfg


# ==================================================
# ESTADO GLOBAL DO BOT
# ==================================================
bot_active = False      # True = bot pode clicar; False = so observa
should_exit = False      # sinalizado pela tecla 3
last_click_time = 0.0

last_player_position = None      # (cx, cy) do ultimo frame valido
player_trajectory = deque(maxlen=cfg.TRAJECTORY_LEN)
velocity_history = deque(maxlen=cfg.VELOCITY_HISTORY_LEN)

# Controle de debounce das hotkeys (edge detection: so dispara na
# transicao "solto -> pressionado", ignorando o auto-repeat do SO).
_pressed_keys = set()


# ==================================================
# 1. CAPTURA DE TELA
# ==================================================
def capture_screen(sct):
    """Captura a regiao configurada da tela e devolve um frame BGR."""
    raw = np.array(sct.grab(cfg.GAME_REGION))
    frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    return frame


# ==================================================
# 2. DETECCAO DO PERSONAGEM
# ==================================================
def detect_player(frame, last_position):
    """
    Detecta o personagem no frame usando filtro de cor HSV.

    Retorna um dicionario com x, y, w, h, cx, cy do jogador, ou None
    se nenhum candidato confiavel foi encontrado.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv, np.array(cfg.PLAYER_HSV_MIN), np.array(cfg.PLAYER_HSV_MAX)
    )

    kernel_open = np.ones(cfg.MORPH_OPEN_KERNEL, np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
    mask = cv2.dilate(mask, kernel_open, iterations=1)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []
    frame_h, frame_w = frame.shape[:2]
    min_ratio, max_ratio = cfg.PLAYER_ASPECT_RATIO_RANGE

    for c in contours:
        area = cv2.contourArea(c)
        if area < cfg.PLAYER_MIN_AREA:
            continue

        x, y, w, h = cv2.boundingRect(c)
        if h == 0:
            continue

        ratio = w / float(h)
        if not (min_ratio <= ratio <= max_ratio):
            continue

        cx, cy = x + w // 2, y + h // 2

        if cfg.PLAYER_SEARCH_X_RANGE is not None:
            x_min, x_max = cfg.PLAYER_SEARCH_X_RANGE
            if not (x_min <= cx <= x_max):
                continue

        candidates.append({
            "x": x, "y": y, "w": w, "h": h,
            "cx": cx, "cy": cy, "area": area,
        })

    if not candidates:
        return None

    if last_position is None:
        # Primeira deteccao: assume que o maior contorno valido e o jogador.
        best = max(candidates, key=lambda c: c["area"])
        return best

    # Ha posicao anterior: prioriza o candidato mais proximo dela.
    last_cx, last_cy = last_position
    best = min(
        candidates,
        key=lambda c: (c["cx"] - last_cx) ** 2 + (c["cy"] - last_cy) ** 2,
    )
    dist = ((best["cx"] - last_cx) ** 2 + (best["cy"] - last_cy) ** 2) ** 0.5

    if dist > cfg.MAX_PLAYER_JUMP_DISTANCE:
        # Nenhum candidato plausivel perto da ultima posicao conhecida.
        # Comportamento conservador: consideramos que perdemos o jogador
        # em vez de arriscar seguir o objeto errado.
        return None

    return best


# ==================================================
# 3. DETECCAO DOS OBSTACULOS
# ==================================================
def detect_obstacles(frame):
    """
    Detecta obstaculos no frame usando filtro de cor HSV.

    Retorna uma lista de dicionarios com x, y, w, h, cx, cy, ordenada
    por posicao horizontal (x) crescente.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv, np.array(cfg.OBSTACLE_HSV_MIN), np.array(cfg.OBSTACLE_HSV_MAX)
    )

    kernel_close = np.ones(cfg.MORPH_CLOSE_KERNEL, np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_close)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    obstacles = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < cfg.OBSTACLE_MIN_AREA:
            continue

        x, y, w, h = cv2.boundingRect(c)
        if w < cfg.OBSTACLE_MIN_WIDTH or h < cfg.OBSTACLE_MIN_HEIGHT:
            continue

        obstacles.append({
            "x": x, "y": y, "w": w, "h": h,
            "cx": x + w // 2, "cy": y + h // 2, "area": area,
        })

    obstacles.sort(key=lambda o: o["x"])
    return obstacles


# ==================================================
# 4. IDENTIFICACAO DA PASSAGEM / ZONA SEGURA
# ==================================================
def find_target(player, obstacles, frame_width, frame_height):
    """
    Identifica a proxima abertura segura pela qual o personagem deve
    passar, a partir dos obstaculos detectados a frente do jogador.

    Retorna um dicionario com target_x, target_y, opening_start_y,
    opening_end_y, gap_height -- ou None se nao houver alvo confiavel.
    """
    if player is None:
        return None

    player_x = player["cx"]

    ahead = [
        o for o in obstacles
        if (o["x"] + o["w"]) >= (player_x - cfg.OBSTACLE_BEHIND_MARGIN)
    ]
    if not ahead:
        return None

    ahead.sort(key=lambda o: o["x"])

    # Agrupa obstaculos proximos em "colunas" (mesma coluna vertical).
    columns = []
    current_column = [ahead[0]]
    for obs in ahead[1:]:
        prev_max_x = max(o["x"] + o["w"] for o in current_column)
        if obs["x"] - prev_max_x <= cfg.COLUMN_CLUSTER_GAP:
            current_column.append(obs)
        else:
            columns.append(current_column)
            current_column = [obs]
    columns.append(current_column)

    # A coluna mais proxima do jogador (menor x) e a relevante agora.
    nearest_column = min(columns, key=lambda col: min(o["x"] for o in col))

    # Calcula os intervalos verticais ocupados por obstaculos na coluna,
    # mesclando intervalos sobrepostos.
    intervals = sorted(
        [(o["y"], o["y"] + o["h"]) for o in nearest_column]
    )
    merged = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Candidatos de abertura: entre obstaculos consecutivos, e nas bordas
    # (topo/fundo do frame) caso a coluna nao cubra a tela inteira.
    gap_candidates = []

    if merged[0][0] > 0:
        gap_candidates.append((0, merged[0][0]))

    for i in range(len(merged) - 1):
        gap_start = merged[i][1]
        gap_end = merged[i + 1][0]
        if gap_end > gap_start:
            gap_candidates.append((gap_start, gap_end))

    if merged[-1][1] < frame_height:
        gap_candidates.append((merged[-1][1], frame_height))

    if not gap_candidates:
        return None

    # A abertura real e assumida como a maior (heuristica simples e
    # robusta o suficiente para o MVP).
    best_gap = max(gap_candidates, key=lambda g: g[1] - g[0])
    gap_height = best_gap[1] - best_gap[0]

    if gap_height < cfg.MIN_GAP_HEIGHT:
        return None

    target_x = min(o["x"] for o in nearest_column)
    target_y = (best_gap[0] + best_gap[1]) // 2

    return {
        "target_x": target_x,
        "target_y": target_y,
        "opening_start_y": best_gap[0],
        "opening_end_y": best_gap[1],
        "gap_height": gap_height,
    }


# ==================================================
# 5. VELOCIDADE / MOVIMENTO DO JOGADOR
# ==================================================
def calculate_velocity(trajectory, velocity_hist):
    """
    Calcula a velocidade vertical suavizada do jogador a partir do
    historico de posicoes (trajectory) e atualiza o historico de
    velocidades (velocity_hist), usado como media movel.

    velocity_y > 0  -> caindo
    velocity_y < 0  -> subindo
    velocity_y ~= 0 -> topo do salto / parado
    """
    if len(trajectory) < 2:
        return 0.0

    prev_cy = trajectory[-2][1]
    curr_cy = trajectory[-1][1]
    instant_velocity = curr_cy - prev_cy

    velocity_hist.append(instant_velocity)
    return sum(velocity_hist) / len(velocity_hist)


def predict_player_y(player, velocity_y, frames_ahead=None):
    """
    Funcao OPCIONAL (desativada por padrao via cfg.ENABLE_PREDICTION).

    Estima a posicao Y futura do jogador considerando velocidade atual
    e uma estimativa grosseira de gravidade. Util para antecipar ainda
    mais o clique, mas pode deixar o bot instavel se a fisica do jogo
    for muito diferente da estimativa -- por isso comeca desativada.
    """
    if frames_ahead is None:
        frames_ahead = cfg.PREDICTION_FRAMES_AHEAD

    y = player["cy"]
    vy = velocity_y
    for _ in range(frames_ahead):
        y += vy
        vy += cfg.GRAVITY_ESTIMATE
    return y


# ==================================================
# 6. CONTROLE DO JOGO (CLIQUE)
# ==================================================
def click_jump():
    """Executa um unico clique esquerdo (nao mantem o botao pressionado)."""
    pydirectinput.click(button="left")
    print("[ACTION] JUMP")


# ==================================================
# 7. DECISAO DO BOT
# ==================================================
def should_jump(player, target, velocity_y):
    """
    Decide se o bot deve pular agora, com base na posicao do jogador,
    no alvo (abertura segura) e na velocidade vertical atual.

    Logica:
      - Sem jogador ou sem alvo confiavel -> nunca pula (conservador).
      - Subindo (velocity_y bem negativa) -> espera, ja esta subindo.
      - Caindo (velocity_y positiva):
          * se ja esta no nivel do centro do alvo (ou abaixo) -> pula
            para nao cair na zona perigosa;
          * se o obstaculo esta proximo (urgente) e o jogador ja esta
            razoavelmente abaixo do centro do alvo -> antecipa o pulo.
      - Topo do salto / quase parado -> so pula se estiver
        visivelmente abaixo do centro do alvo.
    """
    if player is None or target is None:
        return False

    player_y = player["cy"]
    target_y = target["target_y"]
    target_x = target["target_x"]
    margin = cfg.TARGET_MARGIN

    dist_to_obstacle = target_x - player["cx"]
    urgent = dist_to_obstacle <= cfg.URGENT_DISTANCE_PX

    if velocity_y < -cfg.VELOCITY_DEADZONE:
        # Subindo: aguarda, o proprio impulso do salto ja esta em curso.
        return False

    if velocity_y > cfg.VELOCITY_DEADZONE:
        # Caindo.
        if player_y >= target_y - margin:
            return True
        if urgent and player_y > target_y - (margin * 2):
            return True
        return False

    # Topo do salto / quase parado.
    if player_y > target_y:
        return True
    return False


def get_motion_state(velocity_y):
    """Classifica o estado de movimento vertical do jogador em texto."""
    if velocity_y < -cfg.VELOCITY_DEADZONE:
        return "SUBINDO"
    if velocity_y > cfg.VELOCITY_DEADZONE:
        return "CAINDO"
    return "TOPO DO SALTO"


# ==================================================
# 11/12. DEBUG VISUAL
# ==================================================
def draw_debug(frame, player, obstacles, target, velocity_y,
               state_str, action_str, fps):
    """Desenha todas as informacoes de debug sobre uma copia do frame."""
    debug = frame.copy()

    for o in obstacles:
        cv2.rectangle(
            debug, (o["x"], o["y"]), (o["x"] + o["w"], o["y"] + o["h"]),
            cfg.COLOR_OBSTACLE, 2,
        )

    if target is not None:
        cv2.line(
            debug,
            (0, target["opening_start_y"]),
            (frame.shape[1], target["opening_start_y"]),
            cfg.COLOR_SAFE_ZONE, 1,
        )
        cv2.line(
            debug,
            (0, target["opening_end_y"]),
            (frame.shape[1], target["opening_end_y"]),
            cfg.COLOR_SAFE_ZONE, 1,
        )
        cv2.circle(
            debug, (target["target_x"], target["target_y"]), 6,
            cfg.COLOR_TARGET, -1,
        )
        cv2.putText(
            debug, "TARGET",
            (target["target_x"] + 8, target["target_y"] - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, cfg.COLOR_TARGET, 1, cv2.LINE_AA,
        )

    for point in player_trajectory:
        cv2.circle(debug, point, 2, cfg.COLOR_TRAJECTORY, -1)

    if player is not None:
        cv2.rectangle(
            debug, (player["x"], player["y"]),
            (player["x"] + player["w"], player["y"] + player["h"]),
            cfg.COLOR_PLAYER, 2,
        )
        cv2.circle(debug, (player["cx"], player["cy"]), 3, cfg.COLOR_PLAYER, -1)

    lines = [
        f"BOT: {'ATIVO' if bot_active else 'PAUSADO'}",
        f"PLAYER X: {player['cx'] if player else 'NOT FOUND'}",
        f"PLAYER Y: {player['cy'] if player else 'NOT FOUND'}",
        f"TARGET X: {target['target_x'] if target else 'NOT FOUND'}",
        f"TARGET Y: {target['target_y'] if target else 'NOT FOUND'}",
        f"VELOCIDADE Y: {velocity_y:.2f}",
        f"ESTADO: {state_str}",
        f"ACAO: {action_str}",
        f"FPS: {fps:.1f}",
    ]

    y0 = 20
    for i, line in enumerate(lines):
        cv2.putText(
            debug, line, (10, y0 + i * 20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, cfg.COLOR_TEXT, 1, cv2.LINE_AA,
        )

    return debug


# ==================================================
# 9/10. HOTKEYS (1 = ativar, 2 = pausar, 3 = encerrar)
# ==================================================
def _handle_key_down(name):
    """Executa a acao correspondente a UMA unica tecla pressionada."""
    global bot_active, should_exit

    if name == "1":
        if not bot_active:
            bot_active = True
            print("[BOT] Ativado")
    elif name == "2":
        if bot_active:
            bot_active = False
            print("[BOT] Pausado")
    elif name == "3":
        if not should_exit:
            should_exit = True
            print("[BOT] Encerrando...")


def _on_key_event(event):
    """
    Callback global da biblioteca 'keyboard'.

    Faz deteccao de borda (key down/up) manualmente: so dispara a acao
    na transicao de "solta" para "pressionada". Isso evita que segurar
    a tecla (auto-repeat do sistema operacional) dispare a acao varias
    vezes seguidas.
    """
    if event.event_type == keyboard.KEY_DOWN:
        if event.name not in _pressed_keys:
            _pressed_keys.add(event.name)
            _handle_key_down(event.name)
    elif event.event_type == keyboard.KEY_UP:
        _pressed_keys.discard(event.name)


def handle_hotkeys():
    """Registra o hook global de teclado (chamado uma unica vez)."""
    keyboard.hook(_on_key_event)


# ==================================================
# LOOP PRINCIPAL
# ==================================================
def main():
    global last_player_position, last_click_time

    print("[BOT] Programa iniciado")
    print("[BOT] Pressione 1 para ativar, 2 para pausar, 3 para encerrar.")

    try:
        sct = mss.mss()
    except Exception as exc:
        print(f"[ERRO] Nao foi possivel iniciar a captura de tela: {exc}")
        return

    if cfg.GAME_REGION["width"] <= 0 or cfg.GAME_REGION["height"] <= 0:
        print("[ERRO] GAME_REGION invalida em config.py. "
              "Verifique width/height.")
        return

    handle_hotkeys()

    player_found_logged = False
    target_found_logged = False

    try:
        while not should_exit:
            loop_start = time.time()

            try:
                frame = capture_screen(sct)
            except Exception as exc:
                print(f"[ERRO] Falha ao capturar a tela: {exc}")
                time.sleep(0.5)
                continue

            frame_h, frame_w = frame.shape[:2]

            player = detect_player(frame, last_player_position)

            if player is not None:
                last_player_position = (player["cx"], player["cy"])
                player_trajectory.append((player["cx"], player["cy"]))
                if not player_found_logged:
                    print("[PLAYER] Detectado")
                    player_found_logged = True
            else:
                player_found_logged = False

            obstacles = detect_obstacles(frame)
            target = find_target(player, obstacles, frame_w, frame_h)

            if target is not None and not target_found_logged:
                print("[TARGET] Novo alvo encontrado")
                target_found_logged = True
            elif target is None:
                target_found_logged = False

            velocity_y = calculate_velocity(player_trajectory, velocity_history)
            state_str = get_motion_state(velocity_y)

            action_str = "ESPERAR"
            if bot_active and player is not None and target is not None:
                now = time.time()
                if should_jump(player, target, velocity_y):
                    if now - last_click_time >= cfg.CLICK_COOLDOWN:
                        click_jump()
                        last_click_time = now
                        action_str = "PULAR"

            if cfg.DEBUG:
                fps = 1.0 / max(time.time() - loop_start, 1e-6)
                debug_frame = draw_debug(
                    frame, player, obstacles, target, velocity_y,
                    state_str, action_str, fps,
                )
                cv2.imshow("Bot - Visao", debug_frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                print("[BOT] Encerrando (tecla local Q/ESC)...")
                break

            if cfg.FPS_LIMIT:
                target_dt = 1.0 / cfg.FPS_LIMIT
                elapsed = time.time() - loop_start
                if elapsed < target_dt:
                    time.sleep(target_dt - elapsed)

    except KeyboardInterrupt:
        print("[BOT] Interrompido pelo usuario (Ctrl+C).")
    except Exception as exc:
        print(f"[ERRO] Excecao inesperada no loop principal: {exc}")
    finally:
        try:
            pydirectinput.mouseUp(button="left")
        except Exception:
            pass
        cv2.destroyAllWindows()
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        print("[BOT] Programa encerrado corretamente.")


if __name__ == "__main__":
    main()
