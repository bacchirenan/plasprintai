# ===== Importações =====
import streamlit as st
import pandas as pd
import json, base64, os
import gspread
from google.oauth2.service_account import Credentials
import unicodedata  # 🔹 para remover acentos

# ===== Configuração da página =====
st.set_page_config(
    page_title="PlasPrint IA",   # Título da aba do navegador
    page_icon="🖨️",              # Ícone da aba
    layout="wide"                # Layout em tela cheia
)

# ===== Função para remover acentos de textos =====
def normalize(text):
    """
    Remove acentos e normaliza textos para facilitar buscas.
    """
    if not isinstance(text, str):
        return ""
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8").lower()

# ===== Conectar ao Google Sheets =====
def connect_gsheet():
    """
    Faz a autenticação com o Google Sheets usando a chave de serviço 
    armazenada na variável de ambiente SERVICE_ACCOUNT_B64.
    """
    service_account_info = json.loads(base64.b64decode(os.environ["SERVICE_ACCOUNT_B64"]))
    creds = Credentials.from_service_account_info(
        service_account_info, 
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.environ["SHEET_ID"])  # abre planilha pelo ID
    return sheet

# ===== Ler aba da planilha =====
@st.cache_data
def read_ws(ws_name):
    """
    Lê os dados de uma aba (worksheet) da planilha e retorna como DataFrame.
    Os dados são cacheados para evitar recarregamento constante.
    """
    sheet = connect_gsheet()
    ws = sheet.worksheet(ws_name)
    data = ws.get_all_records()
    return pd.DataFrame(data)

# ===== Atualizar todos os dados =====
def refresh_data():
    """
    Atualiza e recarrega todas as abas da planilha no cache.
    """
    st.cache_data.clear()
    global erros_df, trabalhos_df, dacen_df, psi_df, gerais_df
    erros_df = read_ws("erros")
    trabalhos_df = read_ws("trabalhos")
    dacen_df = read_ws("dacen")
    psi_df = read_ws("psi")
    gerais_df = read_ws("gerais")

# ===== Carregar dados na inicialização =====
try:
    refresh_data()
except Exception as e:
    st.error("⚠️ Erro ao carregar dados da planilha. Verifique as credenciais e o ID da planilha.")
    st.stop()

# ===== Barra lateral com menu =====
st.sidebar.title("📌 Menu")
menu = st.sidebar.radio(
    "Escolha uma aba:", 
    ["Erros", "Trabalhos", "DACEN", "PSI", "Gerais"]
)

# ===== Botão para atualizar planilha =====
st.sidebar.markdown("---")  # separador visual
if st.sidebar.button("🔄 Atualizar planilha"):
    refresh_data()
    st.sidebar.success("✅ Planilhas atualizadas com sucesso!")
    st.rerun()  # 🔹 reinicia a execução do app (compatível com Streamlit Cloud)

# ===== Exibição de cada aba =====
if menu == "Erros":
    st.header("❌ Lista de Erros")
    st.dataframe(erros_df)

elif menu == "Trabalhos":
    st.header("📂 Trabalhos")
    st.dataframe(trabalhos_df)

elif menu == "DACEN":
    st.header("📊 DACEN")
    st.dataframe(dacen_df)

elif menu == "PSI":
    st.header("🧾 PSI")
    st.dataframe(psi_df)

elif menu == "Gerais":
    st.header("ℹ️ Informações Gerais")
    # Mostra cada linha da aba "Gerais" com coluna de texto e coluna de imagem
    for _, row in gerais_df.iterrows():
        col1, col2 = st.columns([2, 1])  # duas colunas (texto maior que imagem)
        with col1:
            st.markdown(f"**{row['Informações']}**")
        with col2:
            if row.get("Imagem"):  # verifica se existe imagem
                st.image(row["Imagem"], use_container_width=True)

# ===== Campo de dúvidas no final =====
st.markdown("<p class='custom-font'>Qual a sua dúvida?</p>", unsafe_allow_html=True)
