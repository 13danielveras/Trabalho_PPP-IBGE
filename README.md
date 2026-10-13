# Trabalho PPP-RBMC

Compara o resultado do IBGE-PPP com a coordenada oficial de estações da RBMC.

## Antes de rodar

Instale as dependências:

    python -m venv .venv
    .venv\Scripts\activate.bat
    pip install -r requirements.txt

Ou, se preferir, instale manualmente:

    pip install requests pandas matplotlib pyproj pypdf

Crie a pasta `ferramentas/` e coloque dentro os executáveis:
GFZRNX (gnss.gfz-potsdam.de/services/gfzrnx) e CRX2RNX (terras.gsi.go.jp/ja/crx2rnx.html).
Sem eles, o Bloco 6 (janelas de tempo) não funciona.

## Como rodar

Rode `python app.py` para abrir uma interface gráfica onde é possível
escolher datas, estações da RBMC e janelas de tempo.
