#!/usr/bin/env python3
"""
launcher.py - Launcher com auto-update via GitHub Releases.

Compilado uma unica vez com:
    pyinstaller --onefile --windowed --name launcher launcher.py

So precisa ser recompilado se ESTE arquivo mudar. O payload (codigo do
app) e atualizado via download de zip, sem nunca recompilar o launcher.
"""

import json
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from tkinter import messagebox, scrolledtext

APP_USER_AGENT = "fnkRecortador-launcher"


def base_dir() -> Path:
    """Pasta onde o launcher (fonte ou .exe compilado) esta - nunca
    hardcode caminho, sempre derive de onde o processo esta rodando."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = base_dir()
CONFIG_PATH = BASE_DIR / "update_config.json"
VERSION_PATH = BASE_DIR / "version.json"


def ler_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def ler_versao_local() -> str:
    try:
        with open(VERSION_PATH, encoding="utf-8") as f:
            return json.load(f).get("version", "0.0.0")
    except (FileNotFoundError, json.JSONDecodeError):
        return "0.0.0"


def _resolver_python() -> str | None:
    """sys.executable aponta pro proprio launcher.exe quando congelado -
    NAO serve para rodar um .py. Precisa achar um interpretador Python de
    verdade instalado no sistema."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    for candidato in ("python", "python3", "py"):
        caminho = shutil.which(candidato)
        if caminho:
            return caminho
    return None


class LauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = ler_config()
        self.root.title(self.config.get("app_title", "Launcher"))
        self.root.geometry("560x360")
        self.root.resizable(False, False)

        titulo = tk.Label(
            root, text=self.config.get("app_title", "Launcher"),
            font=("Segoe UI", 16, "bold"),
        )
        titulo.pack(pady=(16, 0))

        self.versao_label = tk.Label(root, text=f"Versao instalada: {ler_versao_local()}",
                                      font=("Segoe UI", 9), fg="#555")
        self.versao_label.pack(pady=(2, 12))

        botoes = tk.Frame(root)
        botoes.pack(pady=4)

        self.btn_atualizar = tk.Button(
            botoes, text="🔄 Atualizar App", width=20, height=2,
            command=self.on_atualizar,
        )
        self.btn_atualizar.grid(row=0, column=0, padx=8)

        self.btn_iniciar = tk.Button(
            botoes, text="▶ Iniciar App", width=20, height=2,
            command=self.on_iniciar,
        )
        self.btn_iniciar.grid(row=0, column=1, padx=8)

        self.log_box = scrolledtext.ScrolledText(root, width=68, height=14, state="disabled",
                                                   font=("Consolas", 9))
        self.log_box.pack(padx=12, pady=12, fill="both", expand=True)

        self.log(f"Pasta do app: {BASE_DIR}")
        self.log(f"Repositorio : {self.config.get('repo')}")

    def log(self, msg: str):
        def _escrever():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _escrever)

    def _travar_botoes(self, travado: bool):
        estado = "disabled" if travado else "normal"
        self.root.after(0, lambda: self.btn_atualizar.configure(state=estado))
        self.root.after(0, lambda: self.btn_iniciar.configure(state=estado))

    # ------------------------------------------------------------------
    # Atualizar App
    # ------------------------------------------------------------------
    def on_atualizar(self):
        threading.Thread(target=self._atualizar_thread, daemon=True).start()

    def _atualizar_thread(self):
        self._travar_botoes(True)
        try:
            self._atualizar()
        except Exception as e:
            self.log(f"ERRO: {e}")
            messagebox.showerror("Atualizar App", f"Falha ao atualizar:\n{e}")
        finally:
            self._travar_botoes(False)

    def _atualizar(self):
        repo = self.config["repo"]
        self.log(f"Consultando ultima release de {repo}...")
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": APP_USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                dados = json.load(r)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GitHub respondeu {e.code} ao consultar releases") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Sem conexao com o GitHub: {e.reason}") from e

        tag_remota = str(dados.get("tag_name", "")).lstrip("vV")
        versao_local = ler_versao_local()
        self.log(f"Versao local: {versao_local}  |  Versao remota: {tag_remota}")

        if tag_remota == versao_local:
            self.log("Ja esta na versao mais recente.")
            self.root.after(0, lambda: messagebox.showinfo("Atualizar App", "Voce ja esta na versao mais recente."))
            return

        # Selecao ESPECIFICA do asset: a release tem mais de um .zip
        # (o payload de codigo E o launcher_setup.zip). Pegar "o primeiro
        # .zip que achar" ja causou um bug real: o launcher baixou o
        # pacote errado e tentou sobrescrever o proprio .exe em execucao,
        # e o Windows bloqueia isso (PermissionError: [Errno 13]).
        assets = dados.get("assets", [])
        asset_payload = next(
            (a for a in assets if a["name"].startswith("payload_") and a["name"].endswith(".zip")),
            None,
        )
        if asset_payload is None:
            raise RuntimeError("Nenhum asset 'payload_*.zip' encontrado nesta release.")

        self.log(f"Baixando {asset_payload['name']}...")
        zip_local = BASE_DIR / f"_update_{asset_payload['name']}"
        req_dl = urllib.request.Request(asset_payload["browser_download_url"],
                                         headers={"User-Agent": APP_USER_AGENT})
        with urllib.request.urlopen(req_dl, timeout=120) as resp, open(zip_local, "wb") as f:
            shutil.copyfileobj(resp, f)

        self.log("Extraindo atualizacao...")
        ignorados = 0
        with zipfile.ZipFile(zip_local) as z:
            for membro in z.namelist():
                nome_base = Path(membro).name
                # Segunda camada de protecao: nunca sobrescreve o proprio
                # launcher.exe em execucao, nao importa o que vier no zip.
                if nome_base.lower() == "launcher.exe":
                    ignorados += 1
                    continue
                z.extract(membro, BASE_DIR)

        zip_local.unlink(missing_ok=True)
        if ignorados:
            self.log(f"Aviso: {ignorados} arquivo(s) 'launcher.exe' no zip foram ignorados por seguranca.")

        nova_versao = ler_versao_local()
        self.log(f"Atualizado com sucesso para a versao {nova_versao}.")
        self.root.after(0, lambda: self.versao_label.configure(text=f"Versao instalada: {nova_versao}"))
        self.root.after(0, lambda: messagebox.showinfo("Atualizar App", f"Atualizado para a versao {nova_versao}!"))

    # ------------------------------------------------------------------
    # Iniciar App
    # ------------------------------------------------------------------
    def on_iniciar(self):
        entry_point = self.config.get("entry_point")
        entry_path = BASE_DIR / entry_point
        if not entry_path.exists():
            messagebox.showerror("Iniciar App", f"Arquivo nao encontrado:\n{entry_path}\n\nUse 'Atualizar App' primeiro.")
            return

        python_exe = _resolver_python()
        if not python_exe:
            messagebox.showerror(
                "Iniciar App",
                "Python nao foi encontrado neste PC.\n"
                "Instale o Python (python.org) e tente novamente.",
            )
            return

        self.log(f"Iniciando {entry_point}...")
        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([python_exe, str(entry_path)], cwd=str(BASE_DIR), **kwargs)
        except Exception as e:
            messagebox.showerror("Iniciar App", f"Falha ao iniciar o app:\n{e}")


def main():
    if not CONFIG_PATH.exists():
        tk.Tk().withdraw()
        messagebox.showerror("Launcher", f"update_config.json nao encontrado em:\n{BASE_DIR}")
        return
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
