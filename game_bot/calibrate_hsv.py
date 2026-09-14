"""
calibrate_hsv.py
================
Ferramenta separada para calibrar os valores HSV do jogador ou dos
obstaculos, olhando a imagem REAL do jogo em tempo real.

Uso:
    python calibrate_hsv.py --target player
    python calibrate_hsv.py --target obstacle

Controles:
    Q ou ESC  -> encerra e imprime os valores finais no terminal
                 (prontos para copiar em config.py)

O que a janela mostra:
    - "original": a regiao capturada (GAME_REGION) sem alteracao
    - "mask": a mascara binaria resultante do filtro HSV atual
    - "resultado": a imagem original com a mascara aplicada (so aparece
      o que esta dentro da faixa HSV escolhida)

Ajuste os sliders ate que APENAS o objeto desejado (jogador ou
obstaculo) fique branco na mascara, com o minimo de ruido possivel.
"""

import argparse
import sys

import cv2
import numpy as np
import mss

import config as cfg


def nothing(_value):
    """Callback vazio exigido pela API de trackbars do OpenCV."""
    pass


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
        choices=["player", "obstacle"],
        default="player",
        help="Qual objeto calibrar: 'player' ou 'obstacle' (padrao: player)",
    )
    args = parser.parse_args()

    if args.target == "player":
        hsv_min, hsv_max = cfg.PLAYER_HSV_MIN, cfg.PLAYER_HSV_MAX
    else:
        hsv_min, hsv_max = cfg.OBSTACLE_HSV_MIN, cfg.OBSTACLE_HSV_MAX

    window_name = f"Calibrar HSV - {args.target}"
    create_trackbars(window_name, hsv_min, hsv_max)

    try:
        sct = mss.mss()
    except Exception as exc:
        print(f"[ERRO] Nao foi possivel iniciar a captura de tela: {exc}")
        sys.exit(1)

    print(f"[CALIBRACAO] Alvo: {args.target}")
    print("[CALIBRACAO] Ajuste os sliders ate isolar o objeto desejado.")
    print("[CALIBRACAO] Pressione Q ou ESC para sair e ver os valores finais.")

    last_min, last_max = hsv_min, hsv_max

    try:
        while True:
            try:
                raw = np.array(sct.grab(cfg.GAME_REGION))
            except Exception as exc:
                print(f"[ERRO] Falha ao capturar a tela: {exc}")
                break

            frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

            h_min, h_max = read_trackbars(window_name)
            last_min, last_max = h_min, h_max

            mask = cv2.inRange(hsv, np.array(h_min), np.array(h_max))
            resultado = cv2.bitwise_and(frame, frame, mask=mask)

            texto = f"MIN {h_min}  MAX {h_max}"
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
    finally:
        cv2.destroyAllWindows()

    print("\n[CALIBRACAO] Valores finais:")
    if args.target == "player":
        print(f"PLAYER_HSV_MIN = {list(last_min)}")
        print(f"PLAYER_HSV_MAX = {list(last_max)}")
    else:
        print(f"OBSTACLE_HSV_MIN = {list(last_min)}")
        print(f"OBSTACLE_HSV_MAX = {list(last_max)}")
    print("Copie essas linhas para dentro de config.py")


if __name__ == "__main__":
    main()
