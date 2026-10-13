"""
Bloco 5 — Série temporal de processamentos PPP.

Para cada data na série:
    1. Verifica a idade e avisa se a efeméride final pode não estar disponível.
    2. Baixa o RINEX da RBMC (FTP) considerando o ano correto.
    3. Envia ao PPP.
    4. Compara com a coordenada oficial (do JSON do Bloco 1).
    5. Guarda resultado. Se o PPP não processar, avisa e pula.

Uso:
    python bloco5_serie.py                     # IFSC, 2026, dia 1, 3 dias, intervalo 1
    python bloco5_serie.py IFSC 2026 1 3 1     # explícito
    python bloco5_serie.py POAL 2026 1 5 1     # POAL, 5 dias consecutivos
"""

import os
import re
import sys
import json
import math
import time
import zipfile
import csv
from datetime import datetime, timedelta
from ftplib import FTP

import requests

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# Parâmetros
# ----------------------------------------------------------------------
ESTACAO = sys.argv[1].upper() if len(sys.argv) > 1 else "IFSC"
ANO = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
DIA_INICIAL = int(sys.argv[3]) if len(sys.argv) > 3 else 1
NUM_DIAS = int(sys.argv[4]) if len(sys.argv) > 4 else 3
INTERVALO = int(sys.argv[5]) if len(sys.argv) > 5 else 1

DIAS = [DIA_INICIAL + i * INTERVALO for i in range(NUM_DIAS)]

PASTA_DADOS = "dados"
PASTA_EXTRAIDOS = os.path.join(PASTA_DADOS, "extraidos")
PASTA_RESPOSTAS = os.path.join(PASTA_DADOS, "respostas")
CAMINHO_JSON_OFICIAL = os.path.join(PASTA_DADOS, f"coordenada_oficial_{ESTACAO}.json")

HOST_FTP = "geoftp.ibge.gov.br"
CAMINHO_BASE_FTP = "/informacoes_sobre_posicionamento_geodesico/rbmc/dados"

URL_PPP = "https://servicodados.ibge.gov.br/api/v1/ppp"
EMAIL = "teste.ppp@exemplo.com"
TIPO_LEVANTAMENTO = "estatico"
AUTORIZACAO_USO = "true"


# ----------------------------------------------------------------------
# Conversões
# ----------------------------------------------------------------------
def gms_para_decimal(gms_str: str) -> float:
    texto = gms_str.replace(",", ".")
    negativo = texto.strip().startswith("-")
    numeros = re.findall(r"\d+\.?\d*", texto)
    if len(numeros) < 3:
        raise ValueError(f"GMS inválido: {gms_str}")
    decimal = float(numeros[0]) + float(numeros[1]) / 60 + float(numeros[2]) / 3600
    return -decimal if negativo else decimal


def grau_para_metro(delta_grau: float, lat_ref: float, tipo: str) -> float:
    if tipo == "lat":
        return delta_grau * 111320
    return delta_grau * 111320 * math.cos(math.radians(lat_ref))


# ----------------------------------------------------------------------
# Verificação de disponibilidade de efeméride final (estimativa)
# ----------------------------------------------------------------------
def verificar_efemeride(ano: int, dia: int, limite_final: int = 17, limite_rapida: int = 12):
    try:
        data_rastreio = datetime(ano, 1, 1) + timedelta(days=dia - 1)
    except Exception:
        return (0, "DESCONHECIDO")

    idade = (datetime.now() - data_rastreio).days

    if idade >= limite_final:
        return (idade, "FINAL")
    elif idade >= limite_rapida:
        return (idade, "RÁPIDA")
    else:
        return (idade, "MUITO RECENTE")


# ----------------------------------------------------------------------
# Carrega a coordenada oficial do JSON (produzido pelo Bloco 1)
# ----------------------------------------------------------------------
def carregar_oficial() -> dict:
    if not os.path.exists(CAMINHO_JSON_OFICIAL):
        print(f"[Bloco 5] ERRO: JSON oficial não encontrado: {CAMINHO_JSON_OFICIAL}")
        print(f"[Bloco 5] Rode primeiro: python bloco1_rbmc.py {ESTACAO}")
        raise SystemExit(1)

    with open(CAMINHO_JSON_OFICIAL, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------
# Baixar RINEX (Corrigido para respeitar o ano correto)
# ----------------------------------------------------------------------
def baixar_zip(ano: int, dia: int) -> str:
    caminho_remoto_dir = f"{CAMINHO_BASE_FTP}/{ano}/{dia:03d}/"
    os.makedirs(PASTA_DADOS, exist_ok=True)

    ftp = FTP(HOST_FTP)
    ftp.login()
    ftp.cwd(caminho_remoto_dir)

    linhas = []
    ftp.retrlines("LIST", linhas.append)

    # Identifica o sufixo correto do ano (ex: 2024 -> 24, 2025 -> 25)
    ano_str = str(ano)[-2:]
    prefixo = f"{ESTACAO.lower()}{dia:03d}0.{ano_str}"
    
    nome_zip = None
    for linha in linhas:
        partes = linha.split()
        if partes and partes[-1].endswith(".zip"):
            nome_arquivo = partes[-1].lower()
            if nome_arquivo.startswith(f"{ESTACAO.lower()}{dia:03d}") and (f".{ano_str}z" in nome_arquivo or f"_{ano_str}" in nome_arquivo or nome_arquivo.startswith(prefixo)):
                nome_zip = partes[-1]
                break

    # Fallback genérico caso o padrão exato varie ligeiramente
    if not nome_zip:
        for linha in linhas:
            partes = linha.split()
            if partes and partes[-1].startswith(f"{ESTACAO.lower()}{dia:03d}") and partes[-1].endswith(".zip"):
                nome_zip = partes[-1]
                break

    if not nome_zip:
        ftp.quit()
        raise FileNotFoundError(f"ZIP não encontrado para {ESTACAO} no ano {ano} dia {dia:03d}")

    # Prefixa o nome local com o ano para evitar conflito de cache entre anos diferentes
    nome_local_zip = f"{ano}_{nome_zip}"
    caminho_local = os.path.join(PASTA_DADOS, nome_local_zip)

    if os.path.exists(caminho_local):
        print(f"  ZIP já existe: {caminho_local}")
    else:
        with open(caminho_local, "wb") as f:
            ftp.retrbinary(f"RETR {caminho_remoto_dir}{nome_zip}", f.write)
        print(f"  Baixado: {caminho_local}")

    ftp.quit()

    os.makedirs(PASTA_EXTRAIDOS, exist_ok=True)
    with zipfile.ZipFile(caminho_local, "r") as z:
        z.extractall(PASTA_EXTRAIDOS)

    return caminho_local


# ----------------------------------------------------------------------
# Enviar ao PPP
# ----------------------------------------------------------------------
def enviar_ppp(caminho_zip: str, oficial: dict) -> dict:
    with open(caminho_zip, "rb") as f:
        arquivos = {
            "arquivo": (os.path.basename(caminho_zip), f, "application/zip"),
        }
        dados = {
            "tipo-levantamento": TIPO_LEVANTAMENTO,
            "modelo-antena": oficial["modelo_igs"],
            "altura-antena": str(oficial["altura_antena_m"]),
            "email": EMAIL,
            "autorizacao-uso": AUTORIZACAO_USO,
        }
        r = requests.post(URL_PPP, files=arquivos, data=dados, timeout=300)

    r.raise_for_status()
    return r.json()


# ----------------------------------------------------------------------
# Comparar
# ----------------------------------------------------------------------
def comparar(resumo: dict, oficial: dict) -> dict:
    lat_ppp = gms_para_decimal(resumo["LAT"])
    lon_ppp = gms_para_decimal(resumo["LON"])
    alt_ppp = float(resumo["HGEO"].replace(",", ".").replace(" m", ""))

    lat_of = gms_para_decimal(oficial["latitude_gms"])
    lon_of = gms_para_decimal(oficial["longitude_gms"])
    alt_of = oficial["altitude_m"]

    dlat_m = grau_para_metro(lat_ppp - lat_of, lat_of, "lat")
    dlon_m = grau_para_metro(lon_ppp - lon_of, lat_of, "lon")
    dalt_m = alt_ppp - alt_of
    dtotal = math.sqrt(dlat_m**2 + dlon_m**2)

    return {
        "dlat_m": dlat_m,
        "dlon_m": dlon_m,
        "dalt_m": dalt_m,
        "dtotal_m": dtotal,
        "orbita": resumo.get("ORBITA", "?"),
    }


# ----------------------------------------------------------------------
# Execução principal
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print(f"[Bloco 5] Estação: {ESTACAO}, ano {ANO}")
    print(f"[Bloco 5] Dias: {DIAS}\n")

    os.makedirs(PASTA_RESPOSTAS, exist_ok=True)

    oficial = carregar_oficial()
    print(f"[Bloco 5] Coordenada oficial carregada de: {CAMINHO_JSON_OFICIAL}")
    print(f"[Bloco 5] Antena: {oficial['modelo_igs']}")
    print(f"[Bloco 5] Altura: {oficial['altura_antena_m']} m\n")

    resultados = []

    for dia in DIAS:
        print(f"=== Processando dia {dia:03d}/{ANO} ===")

        idade, status_estimado = verificar_efemeride(ANO, dia)

        if status_estimado == "FINAL":
            print(f"  Idade da data: {idade} dias. Efeméride FINAL esperada.")
        elif status_estimado == "RÁPIDA":
            print(f"  [ATENÇÃO] Dia {dia:03d}: idade {idade} dias, "
                  f"efeméride provável RÁPIDA.")
        else:
            print(f"  [ATENÇÃO] Dia {dia:03d}: idade {idade} dias, "
                  f"efeméride provável ULTRA-RÁPIDA ou indisponível.")

        try:
            caminho_zip = baixar_zip(ANO, dia)
            time.sleep(2)

            resposta = enviar_ppp(caminho_zip, oficial)

            caminho_resp = os.path.join(PASTA_RESPOSTAS, f"ppp_{ESTACAO}_{ANO}_{dia:03d}.json")
            with open(caminho_resp, "w", encoding="utf-8") as f:
                json.dump(resposta, f, indent=2, ensure_ascii=False)

            resumo = resposta.get("resumo", {})
            if "LAT" not in resumo:
                motivo = resumo.get("Arquivo", "motivo desconhecido")
                print(f"  [AVISO] O PPP não processou o dia {dia:03d}. Motivo: {motivo}")
                print(f"          Resposta salva em: {caminho_resp}\n")
                time.sleep(2)
                continue

            r = comparar(resumo, oficial)
            r["dia"] = dia
            resultados.append(r)

            print(f"  Órbita (informada pelo PPP): {r['orbita']}")
            print(f"  Δtotal: {r['dtotal_m']:.4f} m\n")

            time.sleep(2)

        except Exception as e:
            print(f"  ERRO no dia {dia}: {e}\n")
            continue

    if resultados:
        caminho_csv = os.path.join(PASTA_DADOS, f"resultados_{ESTACAO}_{ANO}.csv")
        with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=resultados[0].keys())
            writer.writeheader()
            writer.writerows(resultados)
        print(f"CSV salvo: {caminho_csv}\n")

        dias = [r["dia"] for r in resultados]
        dtotais = [r["dtotal_m"] for r in resultados]
        dalts = [r["dalt_m"] for r in resultados]

        plt.figure(figsize=(8, 5))
        
        x_indices = list(range(len(dias)))
        labels_x = [f"Dia {d}" for d in dias]

        plt.plot(x_indices, dtotais, "o-", label="Δ horizontal total")
        plt.plot(x_indices, dalts, "s--", label="Δ altitude")
        
        plt.xticks(x_indices, labels_x)
        plt.xlabel("Casos processados (Dia)")
        plt.ylabel("Afastamento (m)")
        plt.title(f"Afastamento PPP vs. oficial — {ESTACAO} {ANO}")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        caminho_png = os.path.join(PASTA_DADOS, f"grafico_afastamento_{ESTACAO}_{ANO}.png")
        plt.savefig(caminho_png, dpi=120)
        print(f"Gráfico salvo: {caminho_png}")