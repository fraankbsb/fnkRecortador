#!/usr/bin/env python3
"""
watch_and_publish.py - Vigia os arquivos do payload e publica sozinho
quando ficam parados por alguns segundos (evita publicar no meio de uma
edicao em andamento).
"""

import subprocess
import sys
import time
from pathlib import Path

from publish import PAYLOAD_FILES

BASE_DIR = Path(__file__).resolve().parent
SILENCIO_S = 8
INTERVALO_S = 1


def mtimes():
    resultado = {}
    for rel in PAYLOAD_FILES:
        caminho = BASE_DIR / rel
        if caminho.exists():
            resultado[rel] = caminho.stat().st_mtime
    return resultado


def main():
    print(f"Vigiando {len(PAYLOAD_FILES)} arquivo(s) do payload em {BASE_DIR}")
    print(f"Publica automaticamente {SILENCIO_S}s apos a ultima mudanca.\n")

    anterior = mtimes()
    ultima_mudanca = None

    while True:
        time.sleep(INTERVALO_S)
        atual = mtimes()
        if atual != anterior:
            anterior = atual
            ultima_mudanca = time.time()
            print("Mudanca detectada, aguardando estabilizar...")

        if ultima_mudanca is not None and (time.time() - ultima_mudanca) >= SILENCIO_S:
            print("Publicando...")
            subprocess.run([sys.executable, str(BASE_DIR / "publish.py"), "auto"], cwd=BASE_DIR)
            ultima_mudanca = None
            anterior = mtimes()
            print("\nVigiando novamente...\n")


if __name__ == "__main__":
    main()
