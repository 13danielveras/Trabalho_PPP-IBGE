"""
Front-end Tkinter para o pipeline PPP-RBMC.

Este app NÃO implementa o pipeline — ele coleta parâmetros e chama
os scripts existentes (bloco1, bloco5, bloco6) via subprocess.

Uso:
    python app.py
"""

import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox


# ----------------------------------------------------------------------
# Caminhos
# ----------------------------------------------------------------------
PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(PASTA_PROJETO, ".venv", "Scripts", "python.exe")

if not os.path.exists(PYTHON):
    PYTHON = "python"


# ----------------------------------------------------------------------
# Função para rodar um script e capturar saída
# ----------------------------------------------------------------------
def rodar_script(nome_script: str, argumentos: list, log_widget: tk.Text) -> bool:
    caminho = os.path.join(PASTA_PROJETO, nome_script)

    if not os.path.exists(caminho):
        log_widget.insert(tk.END, f"[ERRO] Script não encontrado: {nome_script}\n")
        log_widget.see(tk.END)
        return False

    comando = [PYTHON, caminho] + [str(a) for a in argumentos]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    log_widget.insert(tk.END, f"\n>>> {' '.join(comando)}\n")
    log_widget.see(tk.END)
    log_widget.update()

    try:
        processo = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=PASTA_PROJETO,
            env=env,
        )

        for linha in processo.stdout:
            log_widget.insert(tk.END, linha)
            log_widget.see(tk.END)
            log_widget.update()

        processo.wait()

        if processo.returncode != 0:
            log_widget.insert(tk.END, f"[ERRO] Script terminou com código {processo.returncode}\n")
            log_widget.see(tk.END)
            return False

        return True

    except Exception as e:
        log_widget.insert(tk.END, f"[EXCEÇÃO] {e}\n")
        log_widget.see(tk.END)
        return False


# ----------------------------------------------------------------------
# Pipeline principal (roda em thread separada)
# ----------------------------------------------------------------------
def executar_pipeline(parametros: dict, log_widget: tk.Text, botao):
    botao.configure(state="disabled", text="Processando...")

    estacao = parametros["estacao"]
    ano = parametros["ano"]
    dia_inicial = parametros["dia_inicial"]
    num_dias = parametros["num_dias"]
    intervalo = parametros["intervalo"]
    duracoes_str = parametros["duracoes"]
    fazer_janelas = parametros["fazer_janelas"]

    log_widget.delete("1.0", tk.END)
    log_widget.insert(tk.END, "=== INÍCIO DO PIPELINE ===\n")
    log_widget.see(tk.END)

    log_widget.insert(tk.END, "\n--- Bloco 1: coordenada oficial ---\n")
    if not rodar_script("bloco1_rbmc.py", [estacao], log_widget):
        log_widget.insert(tk.END, "\n[PIPELINE ABORTADO no Bloco 1]\n")
        botao.configure(state="normal", text="Processar")
        return

    log_widget.insert(tk.END, "\n--- Bloco 5: série temporal ---\n")
    if not rodar_script(
        "bloco5_serie.py",
        [estacao, ano, dia_inicial, num_dias, intervalo],
        log_widget,
    ):
        log_widget.insert(tk.END, "\n[PIPELINE ABORTADO no Bloco 5]\n")
        botao.configure(state="normal", text="Processar")
        return

    if fazer_janelas and duracoes_str:
        log_widget.insert(tk.END, "\n--- Bloco 6: janelas ---\n")
        # Calcula os dias efetivos com base no intervalo e número de dias
        dias_a_processar = [dia_inicial + i * intervalo for i in range(num_dias)]
        
        # Limpa e formata as durações (ex: "2, 4" -> "2,4" ou lida individualmente)
        duracoes_limpa = duracoes_str.replace(" ", "")

        for d in dias_a_processar:
            log_widget.insert(tk.END, f"\nProcessando janelas para o dia do ano: {d}\n")
            log_widget.see(tk.END)
            # O bloco6_janelas aceita: estacao ano dia_do_ano duracao(s)
            rodar_script(
                "bloco6_janelas.py",
                [estacao, ano, d, duracoes_limpa],
                log_widget,
            )

    log_widget.insert(tk.END, "\n=== PIPELINE CONCLUÍDO ===\n")
    log_widget.see(tk.END)

    pasta_dados = os.path.join(PASTA_PROJETO, "dados")
    if os.path.exists(pasta_dados):
        try:
            os.startfile(pasta_dados)
        except Exception:
            pass

    botao.configure(state="normal", text="Processar")


# ----------------------------------------------------------------------
# Interface Tkinter
# ----------------------------------------------------------------------
def criar_interface():
    root = tk.Tk()
    root.title("Pipeline PPP-RBMC")
    root.geometry("900x720")
    root.minsize(780, 600)

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("Titulo.TLabel", font=("Segoe UI", 14, "bold"))
    style.configure("Subtitulo.TLabel", font=("Segoe UI", 9), foreground="#555")
    style.configure("TButton", padding=6)

    frame_titulo = ttk.Frame(root, padding=(12, 12, 12, 0))
    frame_titulo.pack(fill="x")

    ttk.Label(frame_titulo, text="Pipeline PPP-RBMC", style="Titulo.TLabel").pack(anchor="w")
    ttk.Label(
        frame_titulo,
        text="Compara o resultado do IBGE-PPP com a coordenada oficial da estação.",
        style="Subtitulo.TLabel",
    ).pack(anchor="w")

    frame_param = ttk.LabelFrame(root, text=" Parâmetros ", padding=12)
    frame_param.pack(fill="x", padx=12, pady=(12, 6))

    # --- Estação ---
    ttk.Label(frame_param, text="Estação:").grid(row=0, column=0, sticky="w", padx=(0, 6))
    entrada_estacao = ttk.Entry(frame_param, width=10)
    entrada_estacao.insert(0, "IFSC")
    entrada_estacao.grid(row=0, column=1, sticky="w", padx=(0, 18))

    # --- Ano ---
    ttk.Label(frame_param, text="Ano:").grid(row=0, column=2, sticky="w", padx=(0, 6))
    entrada_ano = ttk.Spinbox(frame_param, from_=1980, to=2100, width=8)
    entrada_ano.set(2024)
    entrada_ano.grid(row=0, column=3, sticky="w", padx=(0, 18))

    # --- Dia inicial ---
    ttk.Label(frame_param, text="Dia do ano inicial:").grid(row=0, column=4, sticky="w", padx=(0, 6))
    entrada_doy = ttk.Spinbox(frame_param, from_=1, to=366, width=6)
    entrada_doy.set(30)
    entrada_doy.grid(row=0, column=5, sticky="w")

    # --- Nº de dias ---
    ttk.Label(frame_param, text="Nº total de dias:").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(8, 0))
    entrada_num = ttk.Spinbox(frame_param, from_=1, to=20, width=6)
    entrada_num.set(1)
    entrada_num.grid(row=1, column=1, sticky="w", padx=(0, 18), pady=(8, 0))

    # --- Intervalo ---
    ttk.Label(frame_param, text="Intervalo (dias):").grid(row=1, column=2, sticky="w", padx=(0, 6), pady=(8, 0))
    entrada_int = ttk.Spinbox(frame_param, from_=1, to=365, width=6)
    entrada_int.set(1)
    entrada_int.grid(row=1, column=3, sticky="w", padx=(0, 18), pady=(8, 0))

    # --- Durações ---
    ttk.Label(frame_param, text="Durações (h, ex: 2 ou 2,4):").grid(row=1, column=4, sticky="w", padx=(0, 6), pady=(8, 0))
    entrada_dur = ttk.Entry(frame_param, width=10, state="disabled")
    entrada_dur.insert(0, "2")
    entrada_dur.grid(row=1, column=5, sticky="w", pady=(8, 0))

    # --- Checkbox janelas ---
    var_janelas = tk.BooleanVar(value=False)

    def ao_mudar_janelas():
        if var_janelas.get():
            entrada_dur.configure(state="normal")
        else:
            entrada_dur.configure(state="disabled")

    ttk.Checkbutton(
        frame_param,
        text="Processar janelas (Bloco 6, opcional)",
        variable=var_janelas,
        command=ao_mudar_janelas,
    ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))

    # --- Botões ---
    frame_botao = ttk.Frame(root)
    frame_botao.pack(fill="x", padx=12, pady=(0, 6))

    botao_processar = ttk.Button(frame_botao, text="Processar", width=18)
    botao_processar.pack(side="right")

    botao_limpar = ttk.Button(frame_botao, text="Limpar log", width=12)
    botao_limpar.pack(side="right", padx=(0, 8))

    # --- Log ---
    frame_log = ttk.LabelFrame(root, text=" Log ", padding=6)
    frame_log.pack(fill="both", expand=True, padx=12, pady=(6, 12))

    log_widget = tk.Text(frame_log, wrap="word", bg="#111", fg="#ddd",
                         font=("Consolas", 9), insertbackground="#ddd")
    log_widget.pack(fill="both", expand=True, side="left")

    scrollbar = ttk.Scrollbar(frame_log, command=log_widget.yview)
    scrollbar.pack(side="right", fill="y")
    log_widget.config(yscrollcommand=scrollbar.set)

    def ao_limpar():
        log_widget.delete("1.0", tk.END)

    botao_limpar.configure(command=ao_limpar)

    def ao_clicar():
        try:
            parametros = {
                "estacao": entrada_estacao.get().strip().upper(),
                "ano": int(entrada_ano.get()),
                "dia_inicial": int(entrada_doy.get()),
                "num_dias": int(entrada_num.get()),
                "intervalo": int(entrada_int.get()),
                "duracoes": entrada_dur.get().strip(),
                "fazer_janelas": var_janelas.get(),
            }
        except ValueError:
            messagebox.showerror("Erro", "Verifique os campos numéricos.")
            return

        if not parametros["estacao"]:
            messagebox.showerror("Erro", "Informe a estação.")
            return

        thread = threading.Thread(
            target=executar_pipeline,
            args=(parametros, log_widget, botao_processar),
            daemon=True,
        )
        thread.start()

    botao_processar.configure(command=ao_clicar)

    root.mainloop()


if __name__ == "__main__":
    criar_interface()