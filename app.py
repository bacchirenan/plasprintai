# app.py
import streamlit as st
import pandas as pd
import json, base64, os, re
import gspread
from google.oauth2.service_account import Credentials
from google import genai

st.set_page_config(page_title="PlasPrint IA", layout="wide")

st.title("PlasPrint IA")

# === Carregar segredos (streamlit secrets) ===
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SHEET_ID = st.secrets["SHEET_ID"]
    SERVICE_ACCOUNT_B64 = st.secrets["SERVICE_ACCOUNT_B64"]
except Exception as e:
    st.error("Por favor, configure os segredos: GEMINI_API_KEY, SHEET_ID, SERVICE_ACCOUNT_B64 (veja instruções).")
    st.stop()

# === Decodificar service account e conectar ao Google Sheets ===
sa_json = json.loads(base64.b64decode(SERVICE_ACCOUNT_B64).decode())
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
gc = gspread.authorize(creds)

# Abrir planilha
try:
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error(f"Não consegui abrir a planilha. Verifique o SHEET_ID e se a planilha foi compartilhada com o service account.\nErro: {e}")
    st.stop()

# Ler abas (se não existir, retorna DF vazio)
def read_ws(name):
    try:
        ws = sh.worksheet(name)
        return pd.DataFrame(ws.get_all_records())
    except Exception:
        return pd.DataFrame()

erros_df = read_ws("erros")
trabalhos_df = read_ws("trabalhos")
dacen_df = read_ws("dacen")
psi_df = read_ws("psi")

# Mostrar contagens simples
st.sidebar.header("Dados carregados")
st.sidebar.write("erros:", len(erros_df))
st.sidebar.write("trabalhos:", len(trabalhos_df))
st.sidebar.write("dacen:", len(dacen_df))
st.sidebar.write("psi:", len(psi_df))

# === Preparar Gemini client ===
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
client = genai.Client()

# Função: construir contexto textual
def build_context(dfs, max_chars=30000):
    parts = []
    for name, df in dfs.items():
        if df.empty:
            continue
        parts.append(f"--- {name} ---")
        for r in df.to_dict(orient="records"):
            row_items = [f"{k}: {v}" for k,v in r.items() if (v is not None and str(v).strip()!='')]
            parts.append(" | ".join(row_items))
    context = "\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n...[CONTEXTO TRUNCADO]"
    return context

# UI: pergunta do usuário
pergunta = st.text_input("Qual a sua dúvida?")

if st.button("Buscar"):
    if not pergunta.strip():
        st.warning("Digite uma pergunta.")
    else:
        dfs = {"erros": erros_df, "trabalhos": trabalhos_df, "dacen": dacen_df, "psi": psi_df}

        q_tokens = [t for t in re.findall(r"\w+", pergunta.lower()) if len(t) > 2]
        matches = []
        for name, df in dfs.items():
            if df.empty: continue
            for i, row in df.iterrows():
                text = " ".join([str(v).lower() for v in row.values if v is not None])
                if any(tok in text for tok in q_tokens):
                    matches.append((name, row.to_dict()))

        st.subheader("Resposta")
        context = build_context(dfs)
        prompt = f"""
Você é um assistente técnico que responde em português.
Baseie-se **apenas** nos dados abaixo (planilhas). Dê uma resposta objetiva e diga, se houver, links de imagens relacionados.
Dados:
{context}

Pergunta:
{pergunta}

Responda objetivo, cite a aba e a linha se aplicável.
"""
        try:
            resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            st.markdown(resp.text)
        except Exception as e:
            st.error(f"Erro ao chamar Gemini: {e}")

# === Marca de versão no canto inferior direito ===
st.markdown(
    """
    <style>
    .version-tag {
        position: fixed;
        bottom: 50px;
        right: 10px;
        font-size: 12px;
        color: white;
        opacity: 0.7;
        z-index: 100;
    }
    </style>
    <div class="version-tag">V1.0</div>
    """,
    unsafe_allow_html=True
)


