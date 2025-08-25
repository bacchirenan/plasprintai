import streamlit as st
import pandas as pd
import json, base64, os, re, requests, io
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import unicodedata  # 🔹 para remover acentos

# ===== Configuração da página =====
st.set_page_config(page_title="PlasPrint IA", page_icon="📊", layout="wide")

# ===== Funções utilitárias =====
def remove_accents(txt):
    return ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')

def resolve_ws_title(sh, name):
    for ws in sh.worksheets():
        if remove_accents(ws.title.lower()) == remove_accents(name.lower()):
            return ws.title
    return name

def read_ws(sheet_name):
    ws = sh.worksheet(sheet_name)
    rows = ws.get_all_records()
    return pd.DataFrame(rows)

# ===== Credenciais Google Sheets =====
SERVICE_ACCOUNT_B64 = st.secrets["SERVICE_ACCOUNT_B64"]
SHEET_ID = st.secrets["SHEET_ID"]

service_account_info = json.loads(base64.b64decode(SERVICE_ACCOUNT_B64))
creds = Credentials.from_service_account_info(service_account_info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
client = gspread.authorize(creds)
sh = client.open_by_key(SHEET_ID)

# ===== Carregar abas =====
erros_df = read_ws(resolve_ws_title(sh, "erros"))
trabalhos_df = read_ws(resolve_ws_title(sh, "trabalhos"))
dacen_df = read_ws(resolve_ws_title(sh, "dacen"))
psi_df = read_ws(resolve_ws_title(sh, "psi"))
info_title = resolve_ws_title(sh, "informações gerais")
informacoes_df = read_ws(info_title)

# ===== Sidebar =====
st.sidebar.header("📑 Dados carregados")
st.sidebar.write("✅ Erros:", len(erros_df))
st.sidebar.write("✅ Trabalhos:", len(trabalhos_df))
st.sidebar.write("✅ Dacen:", len(dacen_df))
st.sidebar.write("✅ Psi:", len(psi_df))
st.sidebar.write("✅ Informações gerais:", len(informacoes_df))

# ===== Dicionário de DataFrames =====
dfs = {
    "erros": erros_df,
    "trabalhos": trabalhos_df,
    "dacen": dacen_df,
    "psi": psi_df,
    "informacoes_gerais": informacoes_df,
}

# ===== Cotação do dólar =====
@st.cache_data(ttl=3600)
def get_usd_rate():
    try:
        resp = requests.get("https://economia.awesomeapi.com.br/json/last/USD-BRL")
        data = resp.json()
        return float(data["USDBRL"]["bid"])
    except:
        return None

usd_rate = get_usd_rate()

# ===== Conversão de valores em dólar =====
def format_dollar_values(text, rate):
    if "$" not in text or rate is None:
        return text

    money_regex = re.compile(r'\$\d+(?:[.,]\d{1,3})*(?:[.,]\d+)?')

    def parse_money_str(s):
        s = s.strip().replace(" ", "")
        if s.startswith('$'):
            s = s[1:]

        if ',' in s and '.' not in s:
            return float(s.replace('.', '').replace(',', '.'))
        if '.' in s and ',' not in s:
            parts = s.split('.')
            if len(parts) > 1 and len(parts[-1]) <= 3:
                return float(s)
            return float(s.replace('.', ''))
        if '.' in s and ',' in s:
            if s.rfind('.') > s.rfind(','):
                return float(s.replace(',', ''))
            else:
                return float(s.replace('.', '').replace(',', '.'))
        return float(s)

    def to_brazilian(n):
        return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def repl(m):
        orig = m.group(0)
        try:
            val = parse_money_str(orig)
            converted = val * rate
            return f"{orig} (R$ {to_brazilian(converted)})"
        except:
            return orig

    formatted = money_regex.sub(repl, text)
    if not formatted.endswith("\n"):
        formatted += "\n"
    formatted += "(valores sem impostos)"
    return formatted

# ===== Configuração Gemini =====
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# ===== Interface principal =====
st.title("🤖 PlasPrint IA")
query = st.text_area("Digite sua pergunta:")

if st.button("Consultar") and query:
    context = ""
    for name, df in dfs.items():
        if not df.empty:
            context += f"\n===== {name.upper()} =====\n"
            context += df.to_csv(index=False)

    prompt = f"""
    Você é um assistente que responde com base nos dados abaixo.
    Pergunta: {query}

    Dados disponíveis:
    {context}
    """

    response = model.generate_content(prompt)
    output = response.text if response else "Sem resposta"
    output = format_dollar_values(output, usd_rate)
    st.write(output)

# ===== Botão de atualização manual =====
if st.sidebar.button("🔄 Atualizar planilha"):
    st.cache_data.clear()
    st.rerun()
