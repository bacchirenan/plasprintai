# app.py
import streamlit as st
import pandas as pd
import json, base64, os, re
import gspread
from google.oauth2.service_account import Credentials
from google import genai

st.set_page_config(page_title="PlasPrint IA", layout="wide")

st.title("Bem vindo a PlasPrint IA")

# === Carregar segredos (streamlit secrets) ===
# Você vai definir esses valores no Streamlit Cloud (ou num .streamlit/secrets.toml local)
# GEMINI_API_KEY: chave do Gemini
# SHEET_ID: id do Google Sheet (o trecho entre /d/ e /edit na URL)
# SERVICE_ACCOUNT_B64: conteúdo base64 do JSON do service account

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
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY  # client pega da env
client = genai.Client()

# Função: construir contexto textual (cuidado com tamanho)
def build_context(dfs, max_chars=30000):
    parts = []
    for name, df in dfs.items():
        if df.empty:
            continue
        parts.append(f"--- {name} ---")
        # transformar cada linha em texto
        for r in df.to_dict(orient="records"):
            # filtrar chaves vazias
            row_items = [f"{k}: {v}" for k,v in r.items() if (v is not None and str(v).strip()!='')]
            parts.append(" | ".join(row_items))
    context = "\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n...[CONTEXTO TRUNCADO]"
    return context

# UI: pergunta do usuário
pergunta = st.text_input("Digite sua pergunta:")

if st.button("Buscar"):
    if not pergunta.strip():
        st.warning("Qual é a sua dúvida?")
    else:
        dfs = {"erros": erros_df, "trabalhos": trabalhos_df, "dacen": dacen_df, "psi": psi_df}

        # 1) Busca simples por palavras-chave para sugerir linhas e imagens
        q_tokens = [t for t in re.findall(r"\w+", pergunta.lower()) if len(t) > 2]
        matches = []
        for name, df in dfs.items():
            if df.empty: continue
            for i, row in df.iterrows():
                text = " ".join([str(v).lower() for v in row.values if v is not None])
                if any(tok in text for tok in q_tokens):
                    matches.append((name, row.to_dict()))
        if matches:
            st.subheader("Linhas que podem ser relevantes (busca rápida)")
            for name, row in matches:
                st.markdown(f"**{name}** — {row}")
                # mostrar imagem se tiver campo 'Imagem' ou 'imagem'
                for key in row:
                    if key.lower().startswith("imagem") and row[key]:
                        st.image(row[key], width=300)

        # 2) Montar contexto e perguntar ao Gemini
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
