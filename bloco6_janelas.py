"""
Bloco 6 — Processar janelas de duração variável (bônus).

Para uma estação e um dia:
    1. Baixa o RINEX do FTP do IBGE (ou usa o ficheiro local se já existir)
    2. Descompacta o Hatanaka (com CRX2RNX)
    3. Corta o RINEX em janelas de N horas (com GFZRNX)
    4. Envia cada janela ao PPP
    5. Compara com a coordenada oficial (do JSON do Bloco 1)
    6. Gera CSV e gráfico consolidados com todos os dados acumulados
"""

import os
import re
import sys
import json
import math
import time
import glob
import zipfile
import subprocess
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
DIA = int(sys.argv[3]) if len(sys.argv) > 3 else 1
DURACOES_STR = sys.argv[4] if len(sys.argv) > 4 else "2,4,6,12"
DURACOES = [int(d.strip()) for d in DURACOES_STR.split(",") if d.strip().isdigit()]

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
PASTA_DADOS = os.path.join(PASTA_PROJETO, "dados")
PASTA_EXTRAIDOS = os.path.join(PASTA_DADOS, "extraidos")
PASTA_JANELAS = os.path.join(PASTA_DADOS, "janelas")
PASTA_RESPOSTAS = os.path.join(PASTA_DADOS, "respostas", "janelas")
PASTA_FERRAMENTAS = os.path.join(PASTA_PROJETO, "ferramentas")

CAMINHO_JSON_OFICIAL = os.path.join(PASTA_DADOS, f"coordenada_oficial_{ESTACAO}.json")

GFZRNX_EXE = os.path.join(PASTA_FERRAMENTAS, "gfzrnx_2.2.2_win10_64.exe")
CRX2RNX_EXE = os.path.join(PASTA_FERRAMENTAS, "CRX2RNX.exe")

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


def carregar_oficial() -> dict:
    if not os.path.exists(CAMINHO_JSON_OFICIAL):
        print(f"[Bloco 6] ERRO: JSON oficial não encontrado: {CAMINHO_JSON_OFICIAL}")
        print(f"[Bloco 6] Rode primeiro: python bloco1_rbmc.py {ESTACAO}")
        raise SystemExit(1)
    with open(CAMINHO_JSON_OFICIAL, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------
# 1. Baixar o RINEX do FTP (com suporte offline se o ZIP já existir)
# ----------------------------------------------------------------------
def baixar_zip() -> str:
    caminho_remoto_dir = f"{CAMINHO_BASE_FTP}/{ANO}/{DIA:03d}/"
    os.makedirs(PASTA_DADOS, exist_ok=True)

    prefixo = f"{ESTACAO.lower()}{DIA:03d}"
    zips_existentes = glob.glob(os.path.join(PASTA_DADOS, f"{prefixo}*.zip"))
    
    if zips_existentes:
        caminho_local = zips_existentes[0]
        print(f"  ZIP já existe localmente: {caminho_local}")
    else:
        print(f"  A ligar ao FTP para descarregar o dia {DIA:03d}...")
        ftp = FTP(HOST_FTP)
        ftp.login()
        ftp.cwd(caminho_remoto_dir)

        linhas = []
        ftp.retrlines("LIST", linhas.append)

        nome_zip = None
        for linha in linhas:
            partes = linha.split()
            if partes and partes[-1].startswith(prefixo) and partes[-1].endswith(".zip"):
                nome_zip = partes[-1]
                break

        if not nome_zip:
            ftp.quit()
            raise FileNotFoundError(f"ZIP não encontrado para {ESTACAO} dia {DIA:03d}")

        caminho_local = os.path.join(PASTA_DADOS, nome_zip)
        with open(caminho_local, "wb") as f:
            ftp.retrbinary(f"RETR {caminho_remoto_dir}{nome_zip}", f.write)
        print(f"  Descarregado: {caminho_local}")
        ftp.quit()

    os.makedirs(PASTA_EXTRAIDOS, exist_ok=True)
    with zipfile.ZipFile(caminho_local, "r") as z:
        z.extractall(PASTA_EXTRAIDOS)

    return caminho_local


# ----------------------------------------------------------------------
# 2. Descompactar Hatanaka (CRX2RNX)
# ----------------------------------------------------------------------
def descompactar_hatanaka() -> str:
    candidatos = glob.glob(os.path.join(PASTA_EXTRAIDOS, f"{ESTACAO.lower()}{DIA:03d}*.*d"))
    if not candidatos:
        candidatos = glob.glob(os.path.join(PASTA_EXTRAIDOS, f"{ESTACAO.lower()}{DIA:03d}*.crx"))
    if not candidatos:
        raise FileNotFoundError(f"Nenhum ficheiro Hatanaka encontrado em {PASTA_EXTRAIDOS}")

    caminho_d = candidatos[0]
    base = os.path.splitext(caminho_d)[0]
    
    ext_o = f".{str(ANO)[-2:]}o"
    caminho_o = base + ext_o

    if os.path.exists(caminho_o):
        print(f"  RINEX já existe: {caminho_o}")
        return caminho_o

    print(f"  A descompactar: {caminho_d}")
    subprocess.run([CRX2RNX_EXE, caminho_d], check=True)

    if not os.path.exists(caminho_o):
        gerados = glob.glob(base + ".*o")
        if gerados:
            return gerados[0]
        raise FileNotFoundError(f"CRX2RNX não gerou o ficheiro RINEX correspondente.")

    return caminho_o


# ----------------------------------------------------------------------
# 3. Cortar janelas com GFZRNX
# ----------------------------------------------------------------------
def cortar_janela(caminho_o: str, duracao_h: int) -> str:
    os.makedirs(PASTA_JANELAS, exist_ok=True)

    nome_saida = f"{ESTACAO.lower()}{DIA:03d}_{duracao_h}h.26o"
    caminho_saida = os.path.join(PASTA_JANELAS, nome_saida)

    if os.path.exists(caminho_saida):
        print(f"  Janela {duracao_h}h já existe: {caminho_saida}")
        return caminho_saida

    ano, mes, dia_cal = ano_dia_para_data(ANO, DIA)

    comando = [
        GFZRNX_EXE,
        "-finp", caminho_o,
        "-fout", caminho_saida,
        "-vo", "2",
        "-epo_beg", f"{ano:04d}-{mes:02d}-{dia_cal:02d}_00:00:00",
        "-d", str(duracao_h * 3600),
    ]

    print(f"  A cortar janela de {duracao_h}h...")
    resultado = subprocess.run(comando, capture_output=True, text=True)

    if resultado.returncode != 0 or not os.path.exists(caminho_saida):
        print(f"  [ERRO] GFZRNX falhou para {duracao_h}h")
        print(resultado.stdout[-500:])
        print(resultado.stderr[-500:])
        return None

    return caminho_saida


def ano_dia_para_data(ano: int, dia_do_ano: int):
    data = datetime(ano, 1, 1) + timedelta(days=dia_do_ano - 1)
    return data.year, data.month, data.day


# ----------------------------------------------------------------------
# 4. Enviar ao PPP (com tentativas)
# ----------------------------------------------------------------------
def enviar_janela(caminho_janela: str, oficial: dict, tentativas: int = 3) -> dict:
    for t in range(tentativas):
        try:
            with open(caminho_janela, "rb") as f:
                arquivos = {
                    "arquivo": (os.path.basename(caminho_janela), f, "application/octet-stream"),
                }
                dados = {
                    "tipo-levantamento": TIPO_LEVANTAMENTO,
                    "modelo-antena": oficial["modelo_igs"],
                    "altura-antena": str(oficial["altura_antena_m"]),
                    "email": EMAIL,
                    "autorizacao-uso": AUTORIZACAO_USO,
                }
                r = requests.post(URL_PPP, files=arquivos, data=dados, timeout=600)

            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"    Tentativa {t+1}/{tentativas} falhou: {e}")
            if t < tentativas - 1:
                print(f"    A aguardar 10 s...")
                time.sleep(10)
            else:
                raise


# ----------------------------------------------------------------------
# 5. Comparar
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
    print(f"[Bloco 6] Estação: {ESTACAO}, ano {ANO}, dia {DIA:03d}")
    print(f"[Bloco 6] Durações: {DURACOES} horas\n")

    os.makedirs(PASTA_JANELAS, exist_ok=True)
    os.makedirs(PASTA_RESPOSTAS, exist_ok=True)

    oficial = carregar_oficial()
    print(f"[Bloco 6] Coordenada oficial carregada de: {CAMINHO_JSON_OFICIAL}\n")

    # 1-2. Processamento da data atual da iteração
    print("=== Preparação de dados ===")
    try:
        baixar_zip()
        caminho_o = descompactar_hatanaka()
    except Exception as e:
        print(f"Aviso na preparação: {e}")
        caminho_o = None

    # 3-5. Processa as durações solicitadas para o dia atual (se o RINEX estiver disponível)
    if caminho_o and os.path.exists(caminho_o):
        for dur in DURACOES:
            print(f"=== Janela de {dur}h (Dia {DIA:03d}) ===")
            try:
                caminho_janela = cortar_janela(caminho_o, dur)
                if not caminho_janela:
                    continue

                caminho_resp = os.path.join(PASTA_RESPOSTAS, f"ppp_{os.path.basename(caminho_janela)}.json")

                resposta_valida = False
                if os.path.exists(caminho_resp):
                    try:
                        with open(caminho_resp, "r", encoding="utf-8") as f:
                            resp_temp = json.load(f)
                        if "resumo" in resp_temp and "LAT" in resp_temp["resumo"]:
                            resposta_valida = True
                            print(f"  Resposta válida já existe, a reaproveitar...")
                    except Exception:
                        resposta_valida = False

                if not resposta_valida:
                    print(f"  A enviar para o PPP...")
                    time.sleep(2)
                    resposta = enviar_janela(caminho_janela, oficial)
                    with open(caminho_resp, "w", encoding="utf-8") as f:
                        json.dump(resposta, f, indent=2, ensure_ascii=False)

                time.sleep(2)
            except Exception as e:
                print(f"  ERRO na janela {dur}h: {e}\n")
                continue

    # 6. Consolidação global: varre TODOS os JSONs na pasta de respostas para gerar o gráfico unificado
    arquivos_respostas = glob.glob(os.path.join(PASTA_RESPOSTAS, f"ppp_{ESTACAO.lower()}*.json"))
    resultados_totais = []

    for caminho_resp in arquivos_respostas:
        try:
            with open(caminho_resp, "r", encoding="utf-8") as f:
                resp_temp = json.load(f)
            resumo = resp_temp.get("resumo", {})
            if "LAT" in resumo:
                nome_arq = os.path.basename(caminho_resp)
                m_dur = re.search(r"_(\d+)h", nome_arq)
                m_dia = re.search(r"ifsc(\d{3})", nome_arq)
                
                dur_h = int(m_dur.group(1)) if m_dur else 2
                dia_arq = int(m_dia.group(1)) if m_dia else DIA

                r = comparar(resumo, oficial)
                r["duracao_h"] = dur_h
                r["dia"] = dia_arq
                resultados_totais.append(r)
        except Exception:
            continue

    if resultados_totais:
        # Ordena cronologicamente por dia e duração
        resultados_totais.sort(key=lambda x: (x["dia"], x["duracao_h"]))

        caminho_csv = os.path.join(PASTA_DADOS, f"resultados_janelas_{ESTACAO}.csv")
        campos = ["dia", "duracao_h", "dlat_m", "dlon_m", "dalt_m", "dtotal_m", "orbita"]
        with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            writer.writeheader()
            for r in resultados_totais:
                writer.writerow({k: r.get(k, "") for k in campos})
        print(f"\nCSV unificado salvo: {caminho_csv}\n")

        print("=== RESULTADOS CONSOLIDADOS GLOBAIS ===")
        print(f"{'Dia':<8}{'Duração (h)':<12}{'Órbita':<10}{'Δtotal (m)':<12}")
        for r in resultados_totais:
            print(f"{r['dia']:<8}{r['duracao_h']:<12}{r['orbita']:<10}{r['dtotal_m']:.4f}")
        print()

        labels_x = [f"Dia {r['dia']} ({r['duracao_h']}h)" for r in resultados_totais]
        dtotais = [r["dtotal_m"] for r in resultados_totais]
        dalts = [r["dalt_m"] for r in resultados_totais]

        plt.figure(figsize=(10, 5))
        plt.plot(labels_x, dtotais, "o-", label="Δ horizontal total", markersize=8)
        plt.plot(labels_x, dalts, "s--", label="Δ altitude", markersize=8)
        plt.xlabel("Casos processados (Dia / Duração)")
        plt.ylabel("Afastamento (m)")
        plt.title(f"Convergência do PPP — {ESTACAO} {ANO}")
        plt.xticks(rotation=30)
        plt.grid(True)
        plt.legend()
        plt.tight_layout()

        timestamp = datetime.now().strftime("%H%M%S")
        caminho_png = os.path.join(PASTA_DADOS, f"grafico_janelas_{ESTACAO}_{timestamp}.png")
        caminho_png_padrao = os.path.join(PASTA_DADOS, f"grafico_janelas_{ESTACAO}.png")
        
        plt.savefig(caminho_png, dpi=120)
        plt.savefig(caminho_png_padrao, dpi=120)
        plt.close()
        
        print(f"Gráfico unificado salvo: {caminho_png_padrao}")