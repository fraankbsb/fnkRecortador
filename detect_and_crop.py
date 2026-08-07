#!/usr/bin/env python3
"""
detect_and_crop.py - Crop automatico + blur de @username via ffmpeg
Saida padronizada em 1080px de largura (1080x1080 / 1080x1350 / 1080x1920,
conforme o ratio classificado).
"""

import subprocess
import sys
import shutil
from pathlib import Path


def _bootstrap_dependencia(modulo, pacote_pip):
    """Instala silenciosamente uma dependencia Python ausente via pip.
    Necessario porque o launcher pode chamar `python detect_and_crop.py`
    diretamente (sem passar pelo bootstrap do .bat)."""
    try:
        __import__(modulo)
    except ImportError:
        print(f"Instalando dependencia ausente: {pacote_pip} ...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", pacote_pip])


for _modulo, _pacote in [("cv2", "opencv-python-headless"), ("numpy", "numpy"),
                          ("PIL", "Pillow"), ("pytesseract", "pytesseract")]:
    _bootstrap_dependencia(_modulo, _pacote)

import cv2
import numpy as np
import platform as _platform
import os as _os


def _resolver_tesseract():
    """Procura o executavel do Tesseract em locais conhecidos do Windows.
    Retorna o caminho encontrado ou None."""
    if _platform.system() != "Windows":
        return shutil.which("tesseract")
    candidatos = [
        _os.environ.get("TESSERACT_CMD", ""),          # 1. definido pelo .bat
        shutil.which("tesseract") or "",                # 2. PATH do sistema
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"C:\Users\Public\Tesseract-OCR\tesseract.exe",
        r"C:\ProgramData\chocolatey\bin\tesseract.exe",
    ]
    for c in candidatos:
        if c and _os.path.exists(c):
            return c
    return None


def _tentar_instalar_tesseract():
    """Auto-instala o Tesseract via winget quando ausente. So deve ser
    chamado quando o usuario realmente pediu blur de @username - nao faz
    sentido atrasar toda inicializacao do app por uma feature opcional."""
    print("  Tesseract OCR nao encontrado - tentando instalar via winget...")
    try:
        proc = subprocess.run(
            ["winget", "install", "--id", "UB-Mannheim.TesseractOCR", "-e",
             "--source", "winget", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            print(f"  winget retornou codigo {proc.returncode}")
            print(f"  saida: {(proc.stdout or '')[-800:]}")
            print(f"  erro : {(proc.stderr or '')[-800:]}")
    except Exception as e:
        print(f"  Falha ao executar winget: {e}")
        return None
    return _resolver_tesseract()


try:
    from PIL import Image, ImageEnhance
    import pytesseract

    _tess_encontrado = _resolver_tesseract()
    if _tess_encontrado:
        pytesseract.pytesseract.tesseract_cmd = _tess_encontrado
        OCR_DISPONIVEL = True
    else:
        OCR_DISPONIVEL = False
        print("AVISO: Tesseract OCR nao encontrado — blur de @username sera desativado.", file=sys.stderr)
        print("       Baixe em: https://github.com/UB-Mannheim/tesseract/wiki", file=sys.stderr)
except ImportError:
    OCR_DISPONIVEL = False
    print("AVISO: Tesseract OCR nao encontrado — blur de @username sera desativado.", file=sys.stderr)
    print("       Baixe em: https://github.com/UB-Mannheim/tesseract/wiki", file=sys.stderr)

import argparse
import json, math

# Localizacao portavel: fnkPerfis fica ao lado deste projeto (mesmo pai
# fnkSocialMidia), entao computamos a partir do proprio script - funciona
# em qualquer PC/disco, nunca fixa uma letra de drive.
FNKPERFIS_DIR = Path(_os.environ.get("FNKPERFIS_DIR") or (Path(__file__).resolve().parent.parent / "fnkPerfis"))
PASTA_ENTRADA = "DONWLOADS"
PASTA_SAIDA   = "VIDEOS RECORTADOS"
PASTA_USADOS  = "VIDEOS USADOS"
PADDING_PADRAO = 2

FFMPEG_BIN = "ffmpeg"  # atualizado por garantir_ffmpeg() se so for achado fora do PATH


def _localizar_ffmpeg_pos_instalacao():
    """Apos `winget install`, o PATH do processo atual nao e atualizado
    (so processos novos veem o PATH novo). Procura o binario recem
    instalado diretamente na pasta de pacotes do winget como fallback."""
    base = Path(_os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if not base.exists():
        return None
    candidatos = sorted(base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    return str(candidatos[-1]) if candidatos else None


def garantir_ffmpeg():
    """Confirma que o ffmpeg esta disponivel, tentando auto-instalar via
    winget se necessario. Atualiza FFMPEG_BIN para o caminho resolvido.
    Retorna True se o ffmpeg ficou disponivel de alguma forma."""
    global FFMPEG_BIN
    if shutil.which("ffmpeg"):
        FFMPEG_BIN = "ffmpeg"
        return True
    caminho = _localizar_ffmpeg_pos_instalacao()
    if caminho:
        FFMPEG_BIN = caminho
        return True

    print("  ffmpeg nao encontrado - tentando instalar via winget...")
    try:
        proc = subprocess.run(
            ["winget", "install", "--id", "Gyan.FFmpeg", "-e",
             "--source", "winget", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            print(f"  winget retornou codigo {proc.returncode}")
            print(f"  saida: {(proc.stdout or '')[-800:]}")
            print(f"  erro : {(proc.stderr or '')[-800:]}")
    except Exception as e:
        print(f"  Falha ao executar winget: {e}")
        return False

    if shutil.which("ffmpeg"):
        FFMPEG_BIN = "ffmpeg"
        return True
    caminho = _localizar_ffmpeg_pos_instalacao()
    if caminho:
        FFMPEG_BIN = caminho
        print("  ffmpeg instalado com sucesso.")
        return True

    print("  ffmpeg continua indisponivel apos a tentativa de instalacao.")
    print("  Pode ser necessario reiniciar o programa (PATH so atualiza em processos novos).")
    print("  Instalacao manual: https://www.gyan.dev/ffmpeg/builds/")
    return False

# ─────────────────────────────────────────────
# CLASSIFICACAO POR DIMENSAO (integrada ao recorte)
# ─────────────────────────────────────────────
VIDEO_EXT  = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mts", ".m2ts", ".flv", ".wmv"}
RATIOS     = {"1por1": (1, 1), "4por5": (4, 5), "9por16": (9, 16)}
W_CLASS    = {"fill": 0.40, "crop": 0.30, "scale": 0.20, "res": 0.10}
REF_PX     = 1920 * 1080

# Tamanho de saida por ratio: largura fixa em 1080 (padrao de redes
# sociais), altura de referencia so para exibicao/log - o encode real
# escala mantendo a proporcao do crop detectado (scale=1080:-2), entao o
# resultado final fica no tamanho alvo ou bem proximo dele sem distorcer
# nem recortar novamente o que ja foi cortado do template.
TARGET_DIMS = {"1por1": (1080, 1080), "4por5": (1080, 1350), "9por16": (1080, 1920)}
TARGET_LARGURA = 1080


def _calc_score(w, h, rw, rh):
    sr, tr = w / h, rw / rh
    diff  = abs(math.log(sr) - math.log(tr))
    fill  = math.exp(-diff * 1.5)
    crop  = min(tr, sr) / max(tr, sr)
    ref_h = math.sqrt(REF_PX / tr)
    ref_w = ref_h * tr
    sf    = (ref_w / w) if sr >= tr else (ref_h / h)
    scale = 1.0 if sf <= 1.0 else max(0.0, 1.0 - (sf - 1.0))
    res   = min(1.0, (w * h) / REF_PX)
    return fill * W_CLASS["fill"] + crop * W_CLASS["crop"] + scale * W_CLASS["scale"] + res * W_CLASS["res"]


def classificar_ratio(w, h):
    """Retorna '1por1', '4por5' ou '9por16' baseado nas dimensoes do video."""
    scores = {name: _calc_score(w, h, rw, rh) for name, (rw, rh) in RATIOS.items()}
    return max(scores, key=lambda k: scores[k])


def detectar_regiao(video_path, padding=PADDING_PADRAO, num_amostras=24):
    """
    Identificador inteligente de area de video.

    Logica:
    1. Amostra ~24 frames distribuidos ao longo do video
    2. Calcula variancia temporal pixel a pixel
    3. Agrega por linha e coluna
    4. Limiar ABSOLUTO calibrado pelo ruido de compressao medido nos 4
       cantos do frame (candidatos naturais a "template", pois um card ou
       moldura raramente cobre o frame ate os cantos). Um card estatico
       gerado digitalmente tem ruido de compressao proximo de zero entre
       frames; qualquer video real (mesmo parado) sempre carrega ruido de
       sensor mensuravel. NAO usamos fracao do pico maximo do sinal: um
       unico elemento de alto contraste dentro do video real (legenda,
       objeto colorido) infla esse pico e pode empurrar o limiar acima do
       nivel de ruido normal do resto do video, cortando pedacos legitimos
       dele por engano.
    5. Antes de cortar, compara o ruido dos cantos com a mediana de
       variancia de TODO o frame: se forem parecidos, os cantos
       provavelmente sao video real (sem template), e nao ha base
       confiavel para decidir onde cortar -> mantem o frame inteiro em vez
       de arriscar remover pedacos do video.
    6. Preenche lacunas internas de ate 20 linhas (cenas escuras, legendas)
       sem tocar nas bordas externas
    7. Resultado: range exato do video real

    Funciona para qualquer tipo:
    - Card de Twitter/Instagram (header branco + video embebido)
    - Borda preta solida (acima/abaixo/lateral)
    - Video sem bordas (ocupa frame inteiro)
    - Video com cenas escuras no meio
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Nao foi possivel abrir: {video_path}")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if total < 2:
        cap.release()
        return None

    frames = []
    for i in range(num_amostras):
        idx = int(total * i / max(num_amostras - 1, 1))
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(idx, total - 1))
        ret, frame = cap.read()
        if ret:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()

    if len(frames) < 2:
        return None

    var = np.var(np.stack(frames), axis=0)
    vl  = var.mean(axis=1)   # variancia por linha  (H valores)
    vc  = var.mean(axis=0)   # variancia por coluna (W valores)

    # Amostra dos 4 cantos (candidatos a template) e da mediana global
    # (nivel tipico do frame inteiro, robusto a hotspots de movimento
    # localizados em qualquer posicao) para calibrar o limiar por video.
    m = max(4, min(20, var.shape[0] // 20, var.shape[1] // 20))
    cantos = np.concatenate([
        var[0:m, 0:m].ravel(),  var[0:m, -m:].ravel(),
        var[-m:, 0:m].ravel(),  var[-m:, -m:].ravel(),
    ])
    ruido_cantos   = float(np.median(cantos))
    mediana_global = float(np.median(var))
    # Duas condicoes precisam valer para assumir que os cantos sao
    # template: (a) MAGNITUDE absoluta muito baixa - um card/moldura
    # gerado digitalmente tem ruido de compressao residual tipicamente
    # bem abaixo de 2.0 (escala de variancia de luminancia 0-255); video
    # real de camera, mesmo em fundo parado (parede, equipamento), carrega
    # ruido de sensor que fica ordens de grandeza acima disso. So a
    # condicao relativa (b) nao basta: e comum um video real ter o fundo
    # (que cai justamente nos cantos) bem mais parado que o sujeito em
    # movimento no centro, o que tambem produz razao baixa sem existir
    # template algum.
    tem_template_confiavel = ruido_cantos < 2.0 and ruido_cantos < mediana_global * 0.35
    limiar_global = max(ruido_cantos * 4.0, 1.0)

    def achar_range(sinal, max_lacuna=20):
        mx = sinal.max()
        if mx < 1.0:
            return 0, len(sinal) - 1

        if not tem_template_confiavel:
            # Sem evidencia confiavel de template: os cantos tem ruido
            # parecido com o resto do frame, entao nao ha uma referencia
            # segura de "area estatica" para cortar. Melhor manter o
            # frame inteiro do que arriscar remover video real.
            return 0, len(sinal) - 1

        ativo = sinal > limiar_global

        if not ativo.any():
            return 0, len(sinal) - 1

        n = len(ativo)

        # Preenche lacunas pequenas (cenas escuras, legendas fixas no meio
        # do video real) sem unir blocos separados por lacunas grandes —
        # isso e o que evita que uma legenda queimada no card (com leve
        # tremor de compressao, logo com variancia > 0) seja confundida
        # com o inicio do video real: ela fica isolada em seu proprio
        # bloco, menor que o bloco do video.
        i = 0
        while i < n:
            if not ativo[i]:
                j = i
                while j < n and not ativo[j]:
                    j += 1
                if j - i <= max_lacuna:
                    ativo[i:j] = True
                i = j
            else:
                i += 1

        # O video real e o MAIOR bloco continuo de atividade. Legendas/
        # marcas d'agua no card sao blocos isolados e bem menores.
        blocos = []
        i = 0
        while i < n:
            if ativo[i]:
                j = i
                while j < n and ativo[j]:
                    j += 1
                blocos.append((i, j - 1))
                i = j
            else:
                i += 1

        if not blocos:
            return 0, n - 1

        ini, fim = max(blocos, key=lambda b: b[1] - b[0])
        return ini, fim

    y1, y2 = achar_range(vl)
    x1, x2 = achar_range(vc)

    x1 = max(0,   x1 - padding)
    y1 = max(0,   y1 - padding)
    x2 = min(W-1, x2 + padding)
    y2 = min(H-1, y2 + padding)

    w = (x2 - x1) & ~1
    h = (y2 - y1) & ~1
    return (x1, y1, w, h, W, H)


def detectar_usernames(video_path, crop_y=0, crop_h=None, num_amostras=10):
    """
    Detecta @username via OCR apenas dentro da area do video real (ignora card/template).
    Aceita formatos: @usuario, ig/@usuario, tiktok/@usuario, etc.
    crop_y: Y de inicio do video real no frame original
    crop_h: altura do video real (None = ate o fim)
    """
    import re
    if not OCR_DISPONIVEL:
        return []

    cap   = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W     = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H     = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Limites da area do video real (ignora card/template acima)
    y_ini = crop_y
    y_fim = (crop_y + crop_h) if crop_h else H

    # Agrupa por posicao aproximada (celulas de 25px) para unir deteccoes do mesmo @
    acumulado = {}

    for i in range(num_amostras):
        pos = i / max(num_amostras - 1, 1)
        # min(..., total-1): pos=1.0 na ultima amostra mapeia pro index
        # `total`, um frame alem do fim (invalido) - sem o clamp, o
        # cap.read() falha e a ultima amostra e descartada em silencio
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(total * pos), total - 1))
        ret, frame = cap.read()
        if not ret:
            continue
        # Recorta apenas a area do video real
        frame_video = frame[y_ini:y_fim, :, :]
        rgb = cv2.cvtColor(frame_video, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)

        for versao, escala in [
            (pil, 1),
            (pil.resize((W*2, H*2), Image.LANCZOS), 2),
            (ImageEnhance.Contrast(pil.resize((W*2, H*2), Image.LANCZOS)).enhance(2.5), 2),
        ]:
            data = pytesseract.image_to_data(
                versao, output_type=pytesseract.Output.DICT,
                config='--psm 11 --oem 3'
            )
            for j, text in enumerate(data['text']):
                t = text.strip()
                # Aceita @ em qualquer posicao (ex: "ig/@user", "@user", "Ig/@user")
                if '@' not in t or len(t) < 3:
                    continue
                if int(data['conf'][j]) < 15:
                    continue
                # Extrai o username real via regex
                match = re.search(r'@[\w.]+', t)
                if not match:
                    continue
                username = match.group(0)
                if len(username) < 3:
                    continue
                x = data['left'][j] // escala
                y = data['top'][j] // escala + y_ini  # converte para coordenada do frame original
                w = data['width'][j] // escala
                h = data['height'][j] // escala
                # Agrupa por posicao (celulas de 25px) para unir variacoes do mesmo texto
                key = f"{x//25}_{y//25}"
                if key not in acumulado:
                    acumulado[key] = {'text': username, 'coords': []}
                acumulado[key]['coords'].append((x, y, w, h))

    cap.release()

    resultado = []
    for key, info in acumulado.items():
        coords = info['coords']
        if len(coords) < 2:
            continue
        resultado.append({
            'text': info['text'],
            'x': int(np.median([c[0] for c in coords])),
            'y': int(np.median([c[1] for c in coords])),
            'w': int(np.median([c[2] for c in coords])),
            'h': int(np.median([c[3] for c in coords])),
        })

    return resultado





def construir_vf(crop_x, crop_y, crop_w, crop_h, usernames, padding_blur=10, escalar=True):
    """
    Monta filtro ffmpeg: crop + delogo + scale.
    - crop_x, crop_y, crop_w, crop_h: regiao do video real no frame original
    - usernames: lista de {x, y, w, h} no espaco do FRAME ORIGINAL
    - Converte coordenadas para o espaco do FRAME CORTADO antes de passar ao ffmpeg
    - Descarta qualquer delogo que fique fora do frame cortado
    - escalar: se True, adiciona scale=1080:-2 por ULTIMO (apos crop/delogo),
      levando a saida para a largura padrao de redes sociais mantendo a
      proporcao do crop - nao recorta nada alem do que ja foi detectado
      como video real, so redimensiona.
    """
    partes = [f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}"]

    for u in usernames:
        p = padding_blur

        # Caixa com padding no espaco original
        ox1 = u['x'] - p
        oy1 = u['y'] - p
        ox2 = u['x'] + u['w'] + p
        oy2 = u['y'] + u['h'] + p

        # Converte para espaco do frame cortado
        dx1 = ox1 - crop_x
        dy1 = oy1 - crop_y
        dx2 = ox2 - crop_x
        dy2 = oy2 - crop_y

        # Clip dentro do frame cortado
        cx1 = max(0, dx1)
        cy1 = max(0, dy1)
        cx2 = min(crop_w, dx2)
        cy2 = min(crop_h, dy2)
        cw  = cx2 - cx1
        ch  = cy2 - cy1

        # Descarta se area invalida ou completamente fora
        if cw < 4 or ch < 4:
            continue
        if cx1 >= crop_w or cy1 >= crop_h:
            continue

        partes.append(f"delogo=x={int(cx1)}:y={int(cy1)}:w={int(cw)}:h={int(ch)}:show=0")

    if escalar:
        partes.append(f"scale={TARGET_LARGURA}:-2:flags=lanczos")

    return ",".join(partes)


def processar_video(caminho_entrada, pasta_saida_base, pasta_usados,
                    padding, dry_run, blur_username):
    """
    Recorta o video E ja classifica por dimensao na saida.
    Salva em pasta_saida_base/<perfil>/<ratio>/<nome>_cortado.mp4
    """
    print(f"\n{'─'*60}")
    print(f"  {caminho_entrada.name}")

    try:
        regiao = detectar_regiao(str(caminho_entrada), padding=padding)
    except Exception as e:
        print(f"  ERRO ao analisar: {e}")
        return False

    cap_tmp = cv2.VideoCapture(str(caminho_entrada))
    W_orig  = int(cap_tmp.get(cv2.CAP_PROP_FRAME_WIDTH))
    H_orig  = int(cap_tmp.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap_tmp.release()

    if regiao is None:
        crop_x, crop_y, crop_w, crop_h = 0, 0, W_orig, H_orig
        sem_crop = True
    else:
        crop_x, crop_y, crop_w, crop_h, W, H = regiao
        sem_crop = (crop_w >= W_orig - 4 and crop_h >= H_orig - 4 and crop_x <= 4)

    if sem_crop:
        crop_x, crop_y, crop_w, crop_h = 0, 0, W_orig, H_orig
        print(f"  Dimensoes : {W_orig}x{H_orig} (sem bordas estaticas)")
    else:
        topo   = crop_y
        rodape = H_orig - crop_y - crop_h
        print(f"  Original  : {W_orig}x{H_orig}")
        print(f"  Corte     : {crop_w}x{crop_h}"
              + (f"  [topo={topo}px]"       if topo   > 4 else "")
              + (f"  [rodape={rodape}px]"   if rodape > 4 else "")
              + (f"  [lateral={crop_x}px]" if crop_x > 4 else ""))

    # Classifica por ratio usando as dimensoes apos o corte
    ratio = classificar_ratio(crop_w, crop_h)
    alvo_w, alvo_h = TARGET_DIMS[ratio]
    saida_h = round((crop_h * TARGET_LARGURA / crop_w) / 2) * 2 if crop_w else alvo_h
    print(f"  Ratio     : {ratio}  (saida ~{TARGET_LARGURA}x{saida_h}, alvo {alvo_w}x{alvo_h})")

    usernames = []
    if blur_username:
        print(f"  OCR       : buscando @username no video...")
        usernames = detectar_usernames(str(caminho_entrada), crop_y=crop_y, crop_h=crop_h)
        if usernames:
            for u in usernames:
                print(f"  @username : '{u['text']}'  x={u['x']} y={u['y']}  {u['w']}x{u['h']}px")
        else:
            print(f"  @username : nenhum detectado")

    # Saida: DONWLOADS/<ratio>/ dentro do mesmo perfil
    pasta_ratio = pasta_saida_base / ratio
    pasta_ratio.mkdir(parents=True, exist_ok=True)
    caminho_saida = pasta_ratio / (caminho_entrada.stem + "_cortado" + caminho_entrada.suffix)

    if sem_crop and not usernames and crop_w == TARGET_LARGURA:
        # Ja esta no tamanho padrao e nao ha nada para cortar/borrar
        cmd = [FFMPEG_BIN, "-y", "-i", str(caminho_entrada), "-c", "copy", str(caminho_saida)]
        print(f"  Acao      : copia direta (ja {TARGET_LARGURA}px de largura)")
    else:
        vf  = construir_vf(crop_x, crop_y, crop_w, crop_h, usernames)
        cmd = [FFMPEG_BIN, "-y", "-i", str(caminho_entrada),
               "-vf", vf, "-c:v", "libx264", "-crf", "18", "-preset", "medium",
               "-c:a", "copy", str(caminho_saida)]
        print(f"  Filtros   : {vf}")

    print(f"  Saida     : {ratio}/{caminho_saida.name}")

    if dry_run:
        print("  [dry-run] nao executado.")
        return True

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"  ERRO: ffmpeg nao encontrado em '{FFMPEG_BIN}'. Pulando este video.")
        return False
    if proc.returncode != 0:
        print(f"  ERRO ffmpeg:\n{proc.stderr[-1000:]}")
        return False

    print(f"  OK! -> {ratio}/")
    return True


# ─────────────────────────────────────────────
# MENU INTERATIVO
# ─────────────────────────────────────────────

def _ler_versao_local():
    try:
        with open(Path(__file__).resolve().parent / "version.json", encoding="utf-8") as f:
            return json.load(f).get("version", "dev")
    except Exception:
        return "dev"


APP_VERSAO = _ler_versao_local()


def _cabecalho(nicho="", perfil=""):
    print()
    print("═" * 60)
    print(f"  🎬 fnkRecortador  v{APP_VERSAO}  ·  Corte automatico + classificacao")
    if nicho:  print(f"  Nicho  : {nicho}")
    if perfil: print(f"  Perfil : {perfil}")
    print("═" * 60)


def _contar_videos(pasta: Path):
    if not pasta.exists():
        return 0
    return sum(1 for p in pasta.iterdir()
               if p.is_file() and p.suffix.lower() in VIDEO_EXT)


def _menu_nicho():
    nichos = sorted([p for p in FNKPERFIS_DIR.iterdir() if p.is_dir()]) if FNKPERFIS_DIR.exists() else []
    if not nichos:
        print(f"\n  ERRO: Nenhum nicho em {FNKPERFIS_DIR}")
        input("  Enter para fechar...")
        return None
    while True:
        _cabecalho()
        print()
        print("  Selecione o NICHO:")
        print()
        for i, n in enumerate(nichos, 1):
            print(f"    {i} - {n.name}")
        print()
        print("    0 - Sair")
        print()
        esc = input("  Digite o numero: ").strip()
        if esc == "0": return None
        if esc.isdigit() and 1 <= int(esc) <= len(nichos):
            return nichos[int(esc) - 1]
        print("  Opcao invalida.")


def _menu_perfil(nicho_path: Path):
    perfis = sorted([p for p in nicho_path.iterdir() if p.is_dir()])
    if not perfis:
        print(f"\n  Nenhum perfil em {nicho_path.name}")
        input("  Enter para voltar...")
        return None
    while True:
        _cabecalho(nicho=nicho_path.name)
        print()
        print("  Selecione os PERFIS (numeros separados por virgula ou 'todos'):")
        print()
        for i, p in enumerate(perfis, 1):
            qtd = _contar_videos(p / PASTA_ENTRADA)
            status = f"{qtd} video(s) em DONWLOADS" if qtd > 0 else "DONWLOADS vazio"
            print(f"    {i} - {p.name}  [{status}]")
        print()
        print("    0 - Voltar")
        print()
        esc = input("  Escolha: ").strip().lower()
        if esc == "0": return None
        if esc == "todos": return perfis
        nums = [x.strip() for x in esc.split(",")]
        sel, ok = [], True
        for n in nums:
            if n.isdigit() and 1 <= int(n) <= len(perfis):
                p = perfis[int(n) - 1]
                if p not in sel: sel.append(p)
            else:
                print(f"  Invalido: {n}"); ok = False; break
        if ok and sel: return sel
        input("  Enter para tentar novamente...")


def _menu_acao(nicho_path, perfis):
    sem_blur = OCR_DISPONIVEL is False
    while True:
        _cabecalho(nicho=nicho_path.name, perfil=", ".join(p.name for p in perfis))
        print()
        print("  Entrada : DONWLOADS\\ (videos soltos)")
        print("  Saida   : VIDEOS RECORTADOS\\<perfil>\\<ratio>\\")
        print("  Usados  : VIDEOS USADOS\\")
        print(f"  Blur @  : {'SIM (Tesseract OK)' if OCR_DISPONIVEL else 'NAO (Tesseract nao encontrado)'}")
        print()
        print("    1 - Processar agora")
        print("    2 - Testar sem executar (dry-run)")
        print("    3 - Voltar")
        print("    0 - Sair")
        print()
        esc = input("  Escolha: ").strip()
        if esc == "0": return "sair"
        if esc == "3": return "voltar"
        if esc in ("1", "2"):
            return {"dry_run": esc == "2", "sem_blur": sem_blur}
        print("  Opcao invalida.")


def main():
    global OCR_DISPONIVEL

    if not garantir_ffmpeg():
        print("\n  ERRO: ffmpeg e obrigatorio para recortar os videos e nao pode ser usado.")
        input("  Pressione Enter para fechar...")
        return

    # Suporte a chamada via linha de comando pelo .bat (retrocompativel)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pasta",    "-p", default=None)
    parser.add_argument("--destino",        default=None)
    parser.add_argument("--padding",  type=int, default=PADDING_PADRAO)
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--sem-blur", action="store_true")
    args, _ = parser.parse_known_args()

    # So tenta instalar o Tesseract se o blur de @username foi pedido e
    # ainda nao esta disponivel - nao faz sentido atrasar quem nao usa OCR.
    if not args.sem_blur and not OCR_DISPONIVEL:
        caminho = _tentar_instalar_tesseract()
        if caminho:
            try:
                import pytesseract as _pt  # nao-op se ja importado; tenta de novo se falhou antes
                _pt.pytesseract.tesseract_cmd = caminho
                globals()["pytesseract"] = _pt
                OCR_DISPONIVEL = True
            except ImportError:
                pass

    # Modo linha de comando — voce aponta a pasta de entrada (qualquer uma) e
    # o perfil de destino (fnkPerfis/<nicho>/<perfil>); ele processa e salva
    # em VIDEOS RECORTADOS/<perfil>/<ratio> dentro do perfil escolhido.
    if args.pasta:
        pasta_entrada = Path(args.pasta.strip('"').strip("'"))

        if not pasta_entrada.exists():
            print(f"\n  ERRO: Pasta de entrada nao encontrada: {pasta_entrada}")
            input("  Pressione Enter para fechar...")
            return

        if not args.destino:
            print(f"\n  ERRO: Nenhum perfil de destino informado (--destino).")
            input("  Pressione Enter para fechar...")
            return

        pasta_perfil = Path(args.destino.strip('"').strip("'"))
        if not pasta_perfil.exists():
            print(f"\n  ERRO: Perfil de destino nao encontrado: {pasta_perfil}")
            input("  Pressione Enter para fechar...")
            return

        videos = sorted(f for f in pasta_entrada.iterdir()
                        if f.is_file() and f.suffix.lower() in VIDEO_EXT)

        if not videos:
            print(f"\n  Nenhum video encontrado em: {pasta_entrada}")
            input("  Pressione Enter para fechar...")
            return

        pasta_saida_base = pasta_perfil / PASTA_SAIDA / pasta_perfil.name

        sep = "═" * 60
        print(f"\n{sep}")
        print(f"  Pasta   : {pasta_entrada}")
        print(f"  Videos  : {len(videos)}")
        print(f"  Perfil  : {pasta_perfil.name}")
        print(f"  Saida   : {pasta_saida_base}\\1por1  |  4por5  |  9por16")
        print(f"{sep}\n")

        ok = 0
        for v in videos:
            if processar_video(v, pasta_saida_base, pasta_saida_base,
                               args.padding, args.dry_run, not args.sem_blur):
                ok += 1

        print(f"\n{sep}")
        print(f"  CONCLUIDO: {ok}/{len(videos)} processados.")
        print(f"{sep}")
        input("\n  Pressione Enter para fechar...")
        return

    # Modo menu interativo
    if not FNKPERFIS_DIR.exists():
        print(f"\n  ERRO: {FNKPERFIS_DIR} nao encontrada.")
        input("  Enter para fechar...")
        return

    while True:
        nicho_path = _menu_nicho()
        if nicho_path is None:
            print("\n  Ate logo!")
            break

        while True:
            perfis = _menu_perfil(nicho_path)
            if perfis is None:
                break

            resultado = _menu_acao(nicho_path, perfis)
            if resultado == "sair":   return
            if resultado == "voltar": continue

            dry_run  = resultado["dry_run"]
            sem_blur = resultado["sem_blur"]
            ok_total = 0
            err_total = 0

            for perfil_path in perfis:
                pasta_entrada = perfil_path / PASTA_ENTRADA
                pasta_saida   = perfil_path / PASTA_SAIDA / perfil_path.name
                pasta_usados  = perfil_path / PASTA_USADOS

                pasta_saida.mkdir(parents=True, exist_ok=True)
                pasta_usados.mkdir(parents=True, exist_ok=True)

                videos = sorted(f for f in pasta_entrada.iterdir()
                                 if f.is_file() and f.suffix.lower() in VIDEO_EXT) if pasta_entrada.exists() else []

                if not videos:
                    print(f"\n  [{perfil_path.name}] Nenhum video em DONWLOADS, pulando.")
                    continue

                print(f"\n{'═'*60}")
                print(f"  PERFIL : {perfil_path.name}")
                print(f"  Videos : {len(videos)}")
                print(f"  Blur @ : {'SIM' if not sem_blur else 'NAO'}")
                if dry_run: print(f"  Modo   : DRY-RUN")
                print(f"{'═'*60}")

                for video in videos:
                    if processar_video(video, pasta_saida, pasta_usados, args.padding, dry_run, not sem_blur):
                        ok_total += 1
                    else:
                        err_total += 1

            print(f"\n{'═'*60}")
            print(f"  CONCLUIDO: {ok_total} OK  |  {err_total} erros")
            print(f"{'═'*60}")
            continuar = input("\n  Processar mais perfis neste nicho? (S/N): ").strip().upper()
            if continuar != "S":
                break


if __name__ == "__main__":
    main()
