import streamlit as st 
import pandas as pd
import json, base64, re, requests, io
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# ===== Configuração da página =====
st.set_page_config(page_title="PlasPrint IA", page_icon="📊", layout="wide")

# ===== Funções utilitárias =====
def read_ws(sheet_name):
    try:
        ws = sh.worksheet(sheet_name)
        rows = ws.get_all_records()
        return pd.DataFrame(rows)
    except Exception as e:
        st.sidebar.error(f"Erro ao ler aba {sheet_name}: {e}")
        return pd.DataFrame()

def load_drive_image(file_id):
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    res = requests.get(url)
    res.raise_for_status()
    return res.content

def format_dollar_values(text, rate):
    """Converte valores em dólar para reais corretamente, sem multiplicar pelo número de unidades."""
    if "$" not in text or rate is None:
        return text
    money_regex = re.compile(r'\$\d+(?:[.,]\d+)?')
    
    def parse_money_str(s):
        s = s.strip().replace(" ", "")
        if s.startswith("$"):
            s = s[1:]
        s = s.replace(",", ".")  # 🔹 só trocar vírgula por ponto
        return float(s)
    
    def to_brazilian(n):
        return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    
    def repl(m):
        orig = m.group(0)
        try:
            val = parse_money_str(orig)
            converted = val * rate  # apenas converte dólar → real
            return f"{orig} (R$ {to_brazilian(converted)})"
        except:
            return orig
    
    formatted = money_regex.sub(repl, text)
    if not formatted.endswith("\n"):
        formatted += "\n"
    formatted += "(valores sem impostos)"
    return formatted

# ===== Segredos e conexão =====
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SHEET_ID = st.secrets["SHEET_ID"]
SERVICE_ACCOUNT_B64 = st.secrets["SERVICE_ACCOUNT_B64"]

sa_json = json.loads(base64.b64decode(SERVICE_ACCOUNT_B64).decode())
creds = Credentials.from_service_account_info(sa_json, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)

# ===== Carregar abas =====
erros_df = read_ws("erros")
trabalhos_df = read_ws("trabalhos")
dacen_df = read_ws("dacen")
psi_df = read_ws("psi")
gerais_df = read_ws("gerais")  # 🔹 aba gerais

dfs = {
    "erros": erros_df,
    "trabalhos": trabalhos_df,
    "dacen": dacen_df,
    "psi": psi_df,
    "gerais": gerais_df
}

# ===== Sidebar =====
st.sidebar.header("📑 Dados carregados")
st.sidebar.write("✅ Erros:", len(erros_df))
st.sidebar.write("✅ Trabalhos:", len(trabalhos_df))
st.sidebar.write("✅ Dacen:", len(dacen_df))
st.sidebar.write("✅ Psi:", len(psi_df))
st.sidebar.write("✅ Gerais:", len(gerais_df))

# Mostrar todas as abas para depuração
st.sidebar.header("Abas disponíveis na planilha")
for ws in sh.worksheets():
    st.sidebar.write(ws.title)

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

# ===== Configuração Gemini =====
client = genai.Client(GEMINI_API_KEY)

# ===== Interface principal =====
st.title("🤖 PlasPrint IA")
query = st.text_area("Digite sua pergunta:")

if st.button("Consultar") and query:
    # Monta o contexto para o Gemini
    context = ""
    
    # Outras abas como CSV
    for name, df in dfs.items():
        if name != "gerais" and not df.empty:
            context += f"\n===== {name.upper()} =====\n"
            context += df.to_csv(index=False)
    
    # Aba gerais como lista de informações
    if not gerais_df.empty:
        context += "\n===== INFORMAÇÕES GERAIS =====\n"
        for idx, row in gerais_df.iterrows():
            info_text = row.get("Informações", "")
            context += f"- {info_text}\n"

    prompt = f"""
Você é um assistente que responde baseado **apenas** nos dados abaixo.
Pergunta: {query}

Dados disponíveis:
{context}
"""
    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        output = resp.text if resp else "Sem resposta"
        output = format_dollar_values(output, usd_rate)
        st.write(output)
    except Exception as e:
        st.error(f"Erro ao chamar Gemini: {e}")

    # ===== Mostrar Gerais com imagens =====
    if not gerais_df.empty:
        st.markdown("### Gerais")
        for idx, row in gerais_df.iterrows():
            info_text = row.get("Informações", "")
            st.markdown(f"<p>{info_text}</p>", unsafe_allow_html=True)
            img_link = row.get("Imagem", "")
            if img_link:
                try:
                    file_id = re.search(r'/d/([a-zA-Z0-9_-]+)/', img_link).group(1)
                    img_bytes = io.BytesIO(load_drive_image(file_id))
                    st.image(img_bytes, use_container_width=True)
                except:
                    st.warning(f"Não foi possível carregar a imagem: {img_link}")

# ===== Botão de atualização =====
if st.sidebar.button("🔄 Atualizar planilha"):
    st.cache_data.clear()
    st.rerun()
