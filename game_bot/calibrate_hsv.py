"""
calibrate_hsv.py
================
Ferramenta separada para calibrar os valores HSV do jogador ou dos
obstaculos, olhando a imagem REAL do jogo em tempo real.

Uso:
    python calibrate_hsv.py --target player
    python calibrate_hsv.py --target obstacle

No jogo das palmeiras (tronco + folhas + carinhas, cada parte com uma
cor diferente), uma unica faixa HSV pode nao cobrir o obstaculo
inteiro. Nesse caso, calibre cada parte separadamente usando qualquer
rotulo que comece com "obstacle", por exemplo:
    python calibrate_hsv.py --target obstacle_tronco
    python calibrate_hsv.py --target obstacle_folhas
    python calibrate_hsv.py --target obstacle_carinha
Cada execucao imprime uma faixa pronta para colar dentro da lista
OBSTACLE_HSV_RANGES em config.py.

Controles:
    F         -> congela/descongela o frame atual (util para obstaculos
                 que so ficam visiveis por pouco tempo na tela: aperte F
                 assim que o obstaculo aparecer para "pausar" aquele
                 instante e calibrar com calma)
    Clique esquerdo na janela "original" -> amostra automaticamente a
                 cor do pixel clicado e ja ajusta os sliders sozinho
                 (mais rapido que arrastar manualmente)
    Q ou ESC  -> encerra e imprime os valores finais no terminal
                 (prontos para copiar em config.py)

O que a janela mostra:
    - "original": a regiao capturada (GAME_REGION) sem alteracao
    - "mask": a mascara binaria resultante do filtro HSV atual
    - "resultado": a imagem original com a mascara aplicada (so aparece
      o que esta dentro da faixa HSV escolhida)

Fluxo recomendado para objetos que aparecem rapido (ex: obstaculos):
    1. Rode o script e deixe o jogo em execucao.
    2. Assim que o obstaculo aparecer na tela, aperte F para congelar.
    3. Clique em cima do obstaculo na janela "original".
    4. Confira a "mask"/"resultado"; se precisar, ajuste os sliders
       manualmente ainda com o frame congelado. Aperte F de novo para
       descongelar e tentar outro instante, se necessario.
    5. Aperte Q/ESC para finalizar e copiar os valores.
"""

import argparse
import sys

import cv2
import numpy as np
import mss

import config as cfg

# Margem aplicada ao redor da cor do pixel clicado ao amostrar
# automaticamente (clique do mouse). Valores maiores = faixa mais larga.
CLICK_H_TOLERANCE = 10
CLICK_S_TOLERANCE = 60
CLICK_V_TOLERANCE = 60


def nothing(_value):
    """Callback vazio exigido pela API de trackbars do OpenCV."""
    pass


def _get_screen_size():
    """Resolucao da tela (Windows). Usa um fallback se nao conseguir."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:
        return 1920, 1080


def layout_debug_windows(window_names, trackbar_window):
    """
    Posiciona as janelas de visualizacao (original/mask/resultado) e a
    janela de sliders FORA da area coberta por GAME_REGION.

    Isso evita o efeito de "espelho infinito": se uma janela de debug
    fica desenhada por cima da propria area capturada, o proximo frame
    acaba fotografando a janela anterior, criando reflexos repetidos.

    A funcao calcula qual lado da tela (esquerda/direita/cima/baixo)
    tem mais espaco livre ao redor de GAME_REGION e organiza as
    janelas (redimensionadas se necessario) nesse espaco.
    """
    screen_w, screen_h = _get_screen_size()
    region = cfg.GAME_REGION
    g_left, g_top = region["left"], region["top"]
    g_right = g_left + region["width"]
    g_bottom = g_top + region["height"]

    margins = {
        "left": g_left,
        "right": screen_w - g_right,
        "top": g_top,
        "bottom": screen_h - g_bottom,
    }
    side = max(margins, key=margins.get)
    space = margins[side]

    if side in ("left", "right"):
        slider_x = 0 if side == "left" else g_right + 5
        cv2.moveWindow(trackbar_window, slider_x, 0)
    else:
        slider_y = 0 if side == "top" else g_bottom + 5
        cv2.moveWindow(trackbar_window, 0, slider_y)

    if space < 150:
        print(
            "[CALIBRACAO][AVISO] Ha pouco espaco livre na tela fora da "
            "area do jogo (GAME_REGION quase preenche a tela toda). Se "
            "aparecer um efeito de reflexos/espelho repetido nas janelas "
            "'original'/'mask'/'resultado', arraste-as manualmente (pelo "
            "titulo) para fora da area ciano do jogo, ou deixe a janela "
            "do Roblox menor/nao maximizada para sobrar mais espaco."
        )

    win_w = max(120, min(260, space - 20))
    win_h = int(win_w * 0.75)

    for i, name in enumerate(window_names):
        cv2.resizeWindow(name, win_w, win_h)
        if side == "left":
            cv2.moveWindow(name, 5, i * (win_h + 40))
        elif side == "right":
            cv2.moveWindow(name, g_right + 10, i * (win_h + 40))
        elif side == "top":
            cv2.moveWindow(name, i * (win_w + 10), 5)
        else:
            cv2.moveWindow(name, i * (win_w + 10), g_bottom + 10)


def create_trackbars(window_name, initial_min, initial_max):
    """Cria a janela de sliders H/S/V min e max com valores iniciais."""
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.createTrackbar("H MIN", window_name, initial_min[0], 179, nothing)
    cv2.createTrackbar("H MAX", window_name, initial_max[0], 179, nothing)
    cv2.createTrackbar("S MIN", window_name, initial_min[1], 255, nothing)
    cv2.createTrackbar("S MAX", window_name, initial_max[1], 255, nothing)
    cv2.createTrackbar("V MIN", window_name, initial_min[2], 255, nothing)
    cv2.createTrackbar("V MAX", window_name, initial_max[2], 255, nothing)


def read_trackbars(window_name):
    """Le os valores atuais dos sliders e devolve (hsv_min, hsv_max)."""
    h_min = cv2.getTrackbarPos("H MIN", window_name)
    h_max = cv2.getTrackbarPos("H MAX", window_name)
    s_min = cv2.getTrackbarPos("S MIN", window_name)
    s_max = cv2.getTrackbarPos("S MAX", window_name)
    v_min = cv2.getTrackbarPos("V MIN", window_name)
    v_max = cv2.getTrackbarPos("V MAX", window_name)
    return (h_min, s_min, v_min), (h_max, s_max, v_max)


def main():
    parser = argparse.ArgumentParser(description="Calibrador de HSV do bot")
    parser.add_argument(
        "--target",
        default="player",
        help=(
            "Qual objeto calibrar. Use 'player' para o personagem, ou "
            "'obstacle' (ou qualquer rotulo iniciado por 'obstacle_', "
            "ex: 'obstacle_tronco') para uma parte de cor do obstaculo. "
            "Padrao: player"
        ),
    )
    args = parser.parse_args()
    target = args.target.strip().lower()
    is_obstacle = target.startswith("obstacle")

    if is_obstacle:
        hsv_min, hsv_max = cfg.OBSTACLE_HSV_MIN, cfg.OBSTACLE_HSV_MAX
    else:
        hsv_min, hsv_max = cfg.PLAYER_HSV_MIN, cfg.PLAYER_HSV_MAX

    window_name = f"Calibrar HSV - {target}"
    create_trackbars(window_name, hsv_min, hsv_max)

    # As 3 janelas de visualizacao (e a de sliders) sao posicionadas
    # automaticamente FORA da area coberta por GAME_REGION. Sem isso,
    # elas podem abrir por cima da propria area do jogo capturada,
    # criando um efeito de "espelho infinito" (cada frame fotografa a
    # janela de debug anterior).
    cv2.namedWindow("original", cv2.WINDOW_NORMAL)
    cv2.namedWindow("mask", cv2.WINDOW_NORMAL)
    cv2.namedWindow("resultado", cv2.WINDOW_NORMAL)
    layout_debug_windows(["original", "mask", "resultado"], window_name)

    try:
        sct = mss.mss()
    except Exception as exc:
        print(f"[ERRO] Nao foi possivel iniciar a captura de tela: {exc}")
        sys.exit(1)

    print(f"[CALIBRACAO] Alvo: {target}")
    print("[CALIBRACAO] Ajuste os sliders ate isolar o objeto desejado.")
    print("[CALIBRACAO] F = congela/descongela o frame atual.")
    print("[CALIBRACAO] Clique na janela 'original' para amostrar a cor "
          "de um pixel automaticamente.")
    print("[CALIBRACAO] Pressione Q ou ESC para sair e ver os valores finais.")

    last_min, last_max = hsv_min, hsv_max
    frozen_frame = None       # quando != None, o frame fica "pausado"
    picked_point = None       # (x, y) do ultimo clique, a processar

    def on_mouse(event, x, y, _flags, _param):
        nonlocal picked_point
        if event == cv2.EVENT_LBUTTONDOWN:
            picked_point = (x, y)

    cv2.setMouseCallback("original", on_mouse)

    try:
        while True:
            if frozen_frame is None:
                try:
                    raw = np.array(sct.grab(cfg.GAME_REGION))
                except Exception as exc:
                    print(f"[ERRO] Falha ao capturar a tela: {exc}")
                    break
                frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
            else:
                frame = frozen_frame.copy()

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            if picked_point is not None:
                px, py = picked_point
                picked_point = None
                if 0 <= py < hsv.shape[0] and 0 <= px < hsv.shape[1]:
                    h, s, v = [int(c) for c in hsv[py, px]]
                    h_min_c = max(0, h - CLICK_H_TOLERANCE)
                    h_max_c = min(179, h + CLICK_H_TOLERANCE)
                    s_min_c = max(0, s - CLICK_S_TOLERANCE)
                    s_max_c = min(255, s + CLICK_S_TOLERANCE)
                    v_min_c = max(0, v - CLICK_V_TOLERANCE)
                    v_max_c = min(255, v + CLICK_V_TOLERANCE)
                    cv2.setTrackbarPos("H MIN", window_name, h_min_c)
                    cv2.setTrackbarPos("H MAX", window_name, h_max_c)
                    cv2.setTrackbarPos("S MIN", window_name, s_min_c)
                    cv2.setTrackbarPos("S MAX", window_name, s_max_c)
                    cv2.setTrackbarPos("V MIN", window_name, v_min_c)
                    cv2.setTrackbarPos("V MAX", window_name, v_max_c)
                    print(
                        f"[CALIBRACAO] Cor amostrada em ({px},{py}): "
                        f"H={h} S={s} V={v} -> sliders ajustados"
                    )

            h_min, h_max = read_trackbars(window_name)
            last_min, last_max = h_min, h_max

            mask = cv2.inRange(hsv, np.array(h_min), np.array(h_max))
            resultado = cv2.bitwise_and(frame, frame, mask=mask)

            status = "CONGELADO (F solta)" if frozen_frame is not None \
                else "AO VIVO (F congela)"
            texto = f"{status}  MIN {h_min}  MAX {h_max}"
            cv2.putText(
                frame, texto, (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
            )

            cv2.imshow("original", frame)
            cv2.imshow("mask", mask)
            cv2.imshow("resultado", resultado)

            key = cv2.waitKey(30) & 0xFF
            if key == ord("q") or key == 27:  # 27 = ESC
                break
            elif key == ord("f"):
                if frozen_frame is None:
                    frozen_frame = frame.copy()
                    print("[CALIBRACAO] Frame congelado.")
                else:
                    frozen_frame = None
                    print("[CALIBRACAO] Frame liberado (ao vivo).")
    finally:
        cv2.destroyAllWindows()

    print("\n[CALIBRACAO] Valores finais:")
    if target == "player":
        print(f"PLAYER_HSV_MIN = {list(last_min)}")
        print(f"PLAYER_HSV_MAX = {list(last_max)}")
        print("Copie essas duas linhas para dentro de config.py")
    elif target == "obstacle":
        print(f"OBSTACLE_HSV_MIN = {list(last_min)}")
        print(f"OBSTACLE_HSV_MAX = {list(last_max)}")
        print("Copie essas duas linhas para dentro de config.py")
    else:
        # Rotulo customizado (ex: obstacle_tronco, obstacle_folhas):
        # imprime como uma entrada pronta para a lista OBSTACLE_HSV_RANGES.
        print(f"# {target}")
        print(f"({list(last_min)}, {list(last_max)}),")
        print(
            "Cole essa linha dentro da lista OBSTACLE_HSV_RANGES em "
            "config.py (uma linha por parte do obstaculo calibrada)."
        )


if __name__ == "__main__":
    main()
