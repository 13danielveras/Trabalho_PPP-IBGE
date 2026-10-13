"""
Bloco 1 — Obter a coordenada oficial de qualquer estação da RBMC.

Endpoint do IBGE: https://servicodados.ibge.gov.br/api/v1/rbmc/relatorio/{estacao}

O código IGS da antena é descoberto em duas etapas:
    1. Se o PDF já traz o código IGS entre parênteses (ex.: "ZEPHYR 3
       GEODETIC (TRM115000.00)"), usa direto.
    2. Caso contrário, faz lookup no rcvr_ant.tab do IGS.

Uso:
    python bloco1_rbmc.py            # usa IFSC como padrão
    python bloco1_rbmc.py POAL       # usa POAL
"""

import io
import os
import re
import sys
import json

import requests

try:
    from pypdf import PdfReader
except ImportError:
    from PyPDF2 import PdfReader


# ----------------------------------------------------------------------
# Parâmetros
# ----------------------------------------------------------------------
ESTACAO = sys.argv[1].upper() if len(sys.argv) > 1 else "IFSC"
PASTA_DADOS = "dados"

URL_RELATORIO = f"https://servicodados.ibge.gov.br/api/v1/rbmc/relatorio/{ESTACAO}"
CAMINHO_PDF = os.path.join(PASTA_DADOS, f"Descritivo_{ESTACAO}.pdf")
CAMINHO_JSON = os.path.join(PASTA_DADOS, f"coordenada_oficial_{ESTACAO}.json")

URL_RCVR_ANT = "https://files.igs.org/pub/station/general/rcvr_ant.tab"
CAMINHO_RCVR_ANT = os.path.join(PASTA_DADOS, "rcvr_ant.tab")


# ----------------------------------------------------------------------
# 1. Baixar o PDF descritivo da estação
# ----------------------------------------------------------------------
def baixar_descritivo() -> bytes:
    print(f"[Bloco 1] Estação: {ESTACAO}")
    print(f"[Bloco 1] Baixando descritivo: {URL_RELATORIO}")

    os.makedirs(PASTA_DADOS, exist_ok=True)

    if os.path.exists(CAMINHO_PDF):
        print(f"[Bloco 1] PDF já existe: {CAMINHO_PDF}")
        with open(CAMINHO_PDF, "rb") as f:
            return f.read()

    resposta = requests.get(URL_RELATORIO, timeout=60)
    resposta.raise_for_status()

    with open(CAMINHO_PDF, "wb") as f:
        f.write(resposta.content)

    print(f"[Bloco 1] PDF salvo: {CAMINHO_PDF} ({len(resposta.content)} bytes)")
    return resposta.content


# ----------------------------------------------------------------------
# 2. Baixar o rcvr_ant.tab do IGS
# ----------------------------------------------------------------------
def baixar_rcvr_ant() -> str:
    os.makedirs(PASTA_DADOS, exist_ok=True)

    if os.path.exists(CAMINHO_RCVR_ANT):
        print(f"[Bloco 1] rcvr_ant.tab já existe: {CAMINHO_RCVR_ANT}")
        return CAMINHO_RCVR_ANT

    print(f"[Bloco 1] Baixando rcvr_ant.tab: {URL_RCVR_ANT}")
    resposta = requests.get(URL_RCVR_ANT, timeout=60)
    resposta.raise_for_status()

    with open(CAMINHO_RCVR_ANT, "wb") as f:
        f.write(resposta.content)

    print(f"[Bloco 1] rcvr_ant.tab salvo: {CAMINHO_RCVR_ANT} ({len(resposta.content)} bytes)")
    return CAMINHO_RCVR_ANT


# ----------------------------------------------------------------------
# 3. Parsear o rcvr_ant.tab
# ----------------------------------------------------------------------
def parsear_rcvr_ant(caminho: str) -> dict:
    """
    Lê o rcvr_ant.tab. Formato:
        TRM115000.00     NONE    ZEPHYR 3 GEODETIC
    Retorna:
        { "ZEPHYR 3 GEODETIC": ("TRM115000.00", "NONE"), ... }
    """
    mapeamento = {}

    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        linhas = f.readlines()

    for linha in linhas:
        if len(linha) < 24:
            continue

        codigo = linha[0:20].strip()
        radome = linha[20:24].strip()
        nome = linha[24:].strip()

        if not codigo or not nome:
            continue
        if codigo.startswith("-") or codigo.startswith("=") or codigo.startswith("#"):
            continue

        mapeamento[nome.upper()] = (codigo, radome if radome else "NONE")

    return mapeamento


# ----------------------------------------------------------------------
# 4. Mapear nome amigável -> código IGS
# ----------------------------------------------------------------------
def mapear_antena_para_igs(nome_amigavel: str, mapeamento: dict) -> str:
    """
    1. Se o nome já tiver código IGS entre parênteses, usa direto.
    2. Caso contrário, tenta match exato no mapeamento.
    3. Se falhar, tenta match parcial.
    4. Fallback: NONE NONE.
    """
    nome_original = nome_amigavel.strip()

    # ETAPA 1 — código IGS entre parênteses
    m = re.search(r"\(([A-Z0-9\.\-\+]+)\)", nome_original)
    if m:
        codigo = m.group(1).strip()
        # Valida se o código existe no mapeamento (opcional, mas informativo)
        for nome_igs, (cod, radome) in mapeamento.items():
            if cod == codigo:
                return f"{codigo:<15}{radome}"
        # Mesmo que não esteja no mapeamento, usa o código do PDF
        return f"{codigo:<15}NONE"

    # ETAPA 2 — match exato
    chave = nome_original.upper()
    if chave in mapeamento:
        codigo, radome = mapeamento[chave]
        return f"{codigo:<15}{radome}"

    # ETAPA 3 — match parcial
    if len(chave) >= 5:
        for nome_igs, (codigo, radome) in mapeamento.items():
            if len(nome_igs) >= 5 and (nome_igs in chave or chave in nome_igs):
                return f"{codigo:<15}{radome}"

    # ETAPA 4 — fallback
    print(f"[Bloco 1] AVISO: antena '{nome_amigavel}' não encontrada")
    return "NONE            NONE"


# ----------------------------------------------------------------------
# 5. Extrair texto do PDF
# ----------------------------------------------------------------------
def extrair_texto_pdf(conteudo: bytes) -> str:
    leitor = PdfReader(io.BytesIO(conteudo))
    texto = ""
    for pagina in leitor.pages:
        texto += (pagina.extract_text() or "") + "\n"
    return texto


# ----------------------------------------------------------------------
# 6. Extrair coordenada e antena
# ----------------------------------------------------------------------
def extrair_coordenadas(texto: str) -> dict:
    resultado = {}

    padrao_lat = r"Latitude\s*[:\-]?\s*([-\d°º'\",\.\s]+?)\""
    padrao_lon = r"Longitude\s*[:\-]?\s*([-\d°º'\",\.\s]+?)\""
    padrao_alt = r"Alt\.?\s*Elip\.?\s*[:\-]?\s*([\d\.,]+)\s*m"

    m_lat = re.search(padrao_lat, texto, re.IGNORECASE)
    m_lon = re.search(padrao_lon, texto, re.IGNORECASE)
    m_alt = re.search(padrao_alt, texto, re.IGNORECASE)

    if m_lat:
        resultado["latitude_gms"] = m_lat.group(1).strip() + '"'
    if m_lon:
        resultado["longitude_gms"] = m_lon.group(1).strip() + '"'
    if m_alt:
        resultado["altitude_m"] = float(m_alt.group(1).replace(",", "."))

    return resultado


def extrair_antena(texto: str, mapeamento_antenas: dict) -> dict:
    resultado = {}

    m = re.search(r"Tipo\s+de\s+Antena\s*[-:]\s*(.+?)(?:\n|URL|Número|$)",
                  texto, re.IGNORECASE)
    if m:
        modelo = m.group(1).strip()
        resultado["modelo_antena"] = modelo
        resultado["modelo_igs"] = mapear_antena_para_igs(modelo, mapeamento_antenas)

    m = re.search(r"Altura\s+da\s+Antena\s*\(m\)\s*[-:]\s*([\d\.,]+)",
                  texto, re.IGNORECASE)
    if m:
        resultado["altura_antena_m"] = float(m.group(1).replace(",", "."))

    return resultado


# ----------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------
if __name__ == "__main__":
    conteudo = baixar_descritivo()

    caminho_tab = baixar_rcvr_ant()
    mapeamento_antenas = parsear_rcvr_ant(caminho_tab)
    print(f"[Bloco 1] {len(mapeamento_antenas)} antenas carregadas do rcvr_ant.tab\n")

    texto = extrair_texto_pdf(conteudo)

    coords = extrair_coordenadas(texto)
    antena = extrair_antena(texto, mapeamento_antenas)

    dados = {
        "estacao": ESTACAO,
        "latitude_gms": coords.get("latitude_gms"),
        "longitude_gms": coords.get("longitude_gms"),
        "altitude_m": coords.get("altitude_m"),
        "modelo_antena": antena.get("modelo_antena"),
        "modelo_igs": antena.get("modelo_igs"),
        "altura_antena_m": antena.get("altura_antena_m"),
    }

    print("=== DADOS EXTRAÍDOS ===")
    for k, v in dados.items():
        print(f"  {k}: {v}")
    print("=======================\n")

    with open(CAMINHO_JSON, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

    print(f"[Bloco 1] JSON salvo: {CAMINHO_JSON}")