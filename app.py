import streamlit as st
import pandas as pd
import re
import base64
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# === Configurações da página ===
st.set_page_config(page_title="PlasPrint IA", page_icon="🖨️", layout="wide")

st.markdown(
    """
    <style>
    .stTextInput label {font-weight: bold;}
    .resposta-box {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #ccc;
        margin-top: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🖨️ PlasPrint IA")
st.caption("Assistente técnico integrado ao Google Sheets")

# === Carregar segredos ===
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SHEET_ID = st.secrets["SHEET_ID"]
    SERVICE_ACCOUNT_B64 = st.secrets["SERVICE_ACCOUNT_B64"]
except Exception:
    st.error("⚠️ Configure os segredos: GEMINI_API_KEY, SHEET_ID, SERVICE_ACCOUNT_B64.")
    st.stop()

# === Configurar Google Sheets ===
service_account_info = base64.b64decode(SERVICE_ACCOUNT_B64).decode()
creds = Credentials.from_service_account_info(eval(service_account_info))
gc = gspread.authorize(creds)

def carregar_aba(nome):
    try:
        ws = gc.open_by_key(SHEET_ID).worksheet(nome)
        df = pd.DataFrame(ws.get_all_records())
        return df
    except:
        return pd.DataFrame()

abas = ["erros", "trabalhos", "dacen", "psi"]
erros_df, trabalhos_df, dacen_df, psi_df = [carregar_aba(a) for a in abas]

# === Configurar Gemini ===
client = genai.Client(api_key=GEMINI_API_KEY)

def build_context(dfs):
    ctx = []
    for name, df in dfs.items():
        if not df.empty:
            ctx.append(f"Aba: {name}\n{df.to_string(index=False)}")
    return "\n\n".join(ctx)

# Entrada do usuário
pergunta = st.text_input("Digite sua pergunta:")

if st.button("🔍 Buscar"):
    if not pergunta.strip():
        st.warning("Digite uma pergunta.")
    else:
        dfs = {"erros": erros_df, "trabalhos": trabalhos_df, "dacen": dacen_df, "psi": psi_df}
        context = build_context(dfs)

        prompt = f"""
Você é um assistente técnico que responde em português.
Baseie-se **apenas** nos dados abaixo (planilhas). Dê uma resposta objetiva e cite a aba e a linha, se aplicável.
Se houver links de imagens, mantenha-os no texto.
Dados:
{context}

Pergunta:
{pergunta}
"""

        try:
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            resposta = resp.text

            # Procurar links do Google Drive e mostrar imagens
            drive_links = re.findall(r"https?://drive\.google\.com/[^\s)]+", resposta)
            imagem_exibida = False
            for link in drive_links:
                match = re.search(r"/d/([a-zA-Z0-9_-]+)", link)
                if match:
                    file_id = match.group(1)
                    img_url = f"https://drive.google.com/uc?export=view&id={file_id}"
                    st.image(img_url, use_column_width=True)
                    imagem_exibida = True

            # Caixa para o texto
            st.markdown(f"<div class='resposta-box'>{resposta}</div>", unsafe_allow_html=True)

        except Exception as e:
            st.error(f"Erro ao chamar Gemini: {e}")
