#!/usr/bin/env python3
"""
publish.py - Publica uma nova versao do app como GitHub Release.

Uso:
    python publish.py <versao> [mensagem]
    python publish.py auto                 (incrementa patch + timestamp)

Cada release ganha 2 assets:
    payload_vX.Y.Z.zip   - codigo que o launcher baixa a cada update
    launcher_setup.zip   - launcher.exe + update_config.json (nome fixo,
                            link permanente para instalar em PC novo)
"""

import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
VERSION_PATH = BASE_DIR / "version.json"
CONFIG_PATH = BASE_DIR / "update_config.json"
DIST_DIR = BASE_DIR / "dist"

# Arquivos que compoe o "payload": o que o launcher baixa e sobrescreve
# na pasta do app a cada atualizacao. NAO inclui launcher.py/launcher.exe
# nem update_config.json (esses vao so no launcher_setup.zip, instalado
# uma vez). Import por watch_and_publish.py para evitar lista duplicada.
PAYLOAD_FILES = [
    "detect_and_crop.py",
    "detect_and_crop.bat",
    "version.json",
    "requirements.txt",
    "cookies/.gitkeep",
]


def resolver_gh() -> str:
    caminho = shutil.which("gh")
    if caminho:
        return caminho
    fallback = Path(r"C:\Program Files\GitHub CLI\gh.exe")
    if fallback.exists():
        return str(fallback)
    raise RuntimeError(
        "gh (GitHub CLI) nao encontrado no PATH nem em 'C:\\Program Files\\GitHub CLI\\gh.exe'.\n"
        "Instale em https://cli.github.com/ e rode 'gh auth login'."
    )


def ler_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def ler_versao() -> str:
    with open(VERSION_PATH, encoding="utf-8") as f:
        return json.load(f).get("version", "0.0.0")


def gravar_versao(versao: str):
    with open(VERSION_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": versao}, f, indent=2)
        f.write("\n")


def bump_patch(versao: str) -> str:
    partes = versao.split(".")
    while len(partes) < 3:
        partes.append("0")
    partes[-1] = str(int(partes[-1]) + 1)
    return ".".join(partes[:3])


def run(cmd, **kwargs):
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def git_add_commit_push(payload_files, mensagem):
    existentes = [f for f in payload_files if (BASE_DIR / f).exists()]
    run(["git", "add"] + existentes, cwd=BASE_DIR, check=True)

    # Se nao ha nada novo pra commitar (so a versao mudou, por exemplo,
    # ou nem isso), nao trava o script - pula o commit graciosamente.
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=BASE_DIR)
    if diff.returncode == 0:
        print("  Nada novo para commitar - pulando commit.")
    else:
        run(["git", "commit", "-m", mensagem], cwd=BASE_DIR, check=True)

    run(["git", "push"], cwd=BASE_DIR, check=True)


def empacotar_payload(versao: str) -> Path:
    zip_path = BASE_DIR / f"payload_v{versao}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in PAYLOAD_FILES:
            caminho = BASE_DIR / rel
            if caminho.exists():
                z.write(caminho, arcname=rel)
    return zip_path


def empacotar_launcher_setup() -> Path | None:
    launcher_exe = DIST_DIR / "launcher.exe"
    if not launcher_exe.exists():
        print("  AVISO: dist/launcher.exe nao encontrado - launcher_setup.zip nao sera atualizado.")
        print("         Compile primeiro: pyinstaller --onefile --windowed --name launcher launcher.py")
        return None
    zip_path = BASE_DIR / "launcher_setup.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(launcher_exe, arcname="launcher.exe")
        z.write(CONFIG_PATH, arcname="update_config.json")
    return zip_path


def publicar_release(gh, repo, versao, mensagem, assets):
    tag = f"v{versao}"
    criar = run(
        [gh, "release", "create", tag, *[str(a) for a in assets],
         "--repo", repo, "--title", tag, "--notes", mensagem],
        cwd=BASE_DIR,
    )
    if criar.returncode != 0:
        # Release ja existe (republicando a mesma versao) - sobrescreve os assets.
        print("  Release ja existe - atualizando assets com --clobber...")
        run(
            [gh, "release", "upload", tag, *[str(a) for a in assets],
             "--repo", repo, "--clobber"],
            cwd=BASE_DIR, check=True,
        )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg_versao = sys.argv[1]
    config = ler_config()
    repo = config["repo"]

    if arg_versao == "auto":
        versao = bump_patch(ler_versao())
        mensagem = sys.argv[2] if len(sys.argv) > 2 else \
            f"Publicacao automatica - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    else:
        versao = arg_versao.lstrip("vV")
        mensagem = sys.argv[2] if len(sys.argv) > 2 else f"v{versao}"

    print(f"═══ Publicando {config.get('app_title', repo)} v{versao} ═══")

    gh = resolver_gh()
    gravar_versao(versao)

    print("\n[1/4] git add / commit / push")
    git_add_commit_push(PAYLOAD_FILES, f"Release v{versao}: {mensagem}")

    print("\n[2/4] Empacotando payload")
    payload_zip = empacotar_payload(versao)
    print(f"  {payload_zip.name}")

    print("\n[3/4] Empacotando launcher_setup.zip")
    launcher_zip = empacotar_launcher_setup()
    if launcher_zip:
        print(f"  {launcher_zip.name}")

    print("\n[4/4] Publicando release no GitHub")
    assets = [payload_zip] + ([launcher_zip] if launcher_zip else [])
    publicar_release(gh, repo, versao, mensagem, assets)

    print(f"\n✔ v{versao} publicada em https://github.com/{repo}/releases/tag/v{versao}")


if __name__ == "__main__":
    main()
