"""
Bloco 2 — Baixar o arquivo RINEX de observação da RBMC via FTP.

O FTP do IBGE organiza os dados por ano/dia do ano:
    /informacoes_sobre_posicionamento_geodesico/rbmc/dados/{ano}/{dia:03d}/

Cada estação tem um ZIP no formato:
    {estacao_lower}{dia:03d}{versao}.zip
    Ex.: ifsc0011.zip  = IFSC, dia 001, versão 1

Este script:
  1. Conecta ao FTP do IBGE.
  2. Lista os arquivos do dia.
  3. Baixa o ZIP da estação escolhida.
  4. Lista o conteúdo do ZIP (sem extrair ainda).
"""

import os
import zipfile
from ftplib import FTP


# ----------------------------------------------------------------------
# Parâmetros
# ----------------------------------------------------------------------
ESTACAO = "IFSC"
ANO = 2026
DIA = 1
PASTA_SAIDA = "dados"

HOST_FTP = "geoftp.ibge.gov.br"
CAMINHO_BASE = "/informacoes_sobre_posicionamento_geodesico/rbmc/dados"


# ----------------------------------------------------------------------
# 1. Conectar e listar o diretório do dia
# ----------------------------------------------------------------------
def listar_diretorio(ano: int, dia: int) -> list:
    caminho = f"{CAMINHO_BASE}/{ano}/{dia:03d}/"

    print(f"Conectando ao FTP: {HOST_FTP}")
    ftp = FTP(HOST_FTP)
    ftp.login()
    print(f"Navegando para: {caminho}\n")
    ftp.cwd(caminho)

    linhas = []
    ftp.retrlines("LIST", linhas.append)
    ftp.quit()

    return linhas


# ----------------------------------------------------------------------
# 2. Encontrar o ZIP da estação
# ----------------------------------------------------------------------
def encontrar_zip(linhas: list, estacao: str, dia: int) -> str:
    prefixo = f"{estacao.lower()}{dia:03d}"
    for linha in linhas:
        partes = linha.split()
        if not partes:
            continue
        nome = partes[-1]
        if nome.startswith(prefixo) and nome.endswith(".zip"):
            return nome
    return None


# ----------------------------------------------------------------------
# 3. Baixar o ZIP
# ----------------------------------------------------------------------
def baixar_zip(nome_zip: str, ano: int, dia: int, pasta_saida: str) -> str:
    caminho_remoto = f"{CAMINHO_BASE}/{ano}/{dia:03d}/{nome_zip}"

    os.makedirs(pasta_saida, exist_ok=True)
    caminho_local = os.path.join(pasta_saida, nome_zip)

    print(f"Baixando: {nome_zip}")
    print(f"De: {caminho_remoto}\n")

    ftp = FTP(HOST_FTP)
    ftp.login()

    with open(caminho_local, "wb") as f:
        ftp.retrbinary(f"RETR {caminho_remoto}", f.write)

    ftp.quit()

    print(f"Salvo em: {caminho_local}")
    print(f"Tamanho: {os.path.getsize(caminho_local)} bytes\n")

    return caminho_local


# ----------------------------------------------------------------------
# 4. Listar o conteúdo do ZIP (sem extrair)
# ----------------------------------------------------------------------
def listar_conteudo_zip(caminho_zip: str) -> list:
    print("=== CONTEÚDO DO ZIP ===")
    with zipfile.ZipFile(caminho_zip, "r") as z:
        for nome in z.namelist():
            info = z.getinfo(nome)
            print(f"  {nome}  ({info.file_size} bytes)")
    print("=======================\n")

    with zipfile.ZipFile(caminho_zip, "r") as z:
        return z.namelist()


# ----------------------------------------------------------------------
# 5. Extrair o ZIP
# ----------------------------------------------------------------------
def extrair_zip(caminho_zip: str, pasta_destino: str) -> list:
    """Extrai o ZIP em uma pasta e retorna os caminhos dos arquivos extraídos."""
    os.makedirs(pasta_destino, exist_ok=True)
    print(f"Extraindo {caminho_zip} em {pasta_destino}\n")

    with zipfile.ZipFile(caminho_zip, "r") as z:
        z.extractall(pasta_destino)
        extraidos = [os.path.join(pasta_destino, n) for n in z.namelist()]

    print("Arquivos extraídos:")
    for e in extraidos:
        print(f"  - {e}")
    print()
    return extraidos


# ----------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # 1. Lista o diretório do dia
    linhas = listar_diretorio(ANO, DIA)

    # 2. Encontra o ZIP da estação
    nome_zip = encontrar_zip(linhas, ESTACAO, DIA)
    if not nome_zip:
        print(f"ERRO: não encontrei o ZIP da estação {ESTACAO} no dia {DIA:03d}.")
        raise SystemExit(1)

    # 3. Baixa o ZIP
    caminho_zip = baixar_zip(nome_zip, ANO, DIA, PASTA_SAIDA)

    # 4. Lista o conteúdo do ZIP (sem extrair)
    arquivos = listar_conteudo_zip(caminho_zip)
    print("Arquivos dentro do ZIP:")
    for a in arquivos:
        print(f"  - {a}")
    print()

    # 5. Extrai o ZIP
    pasta_extraidos = os.path.join(PASTA_SAIDA, "extraidos")
    extraidos = extrair_zip(caminho_zip, pasta_extraidos)