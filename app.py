import streamlit as st
import pandas as pd
import json, base64, os, re, requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai

# ========================
# CONFIGURAÇÃO DA PÁGINA
# ========================
st.set_page_config(page_title="PlasPrint IA", page_icon="favicon.ico", layout="wide")

# ========================
# FAVICON
# ========================
def inject_favicon():
    favicon_path = "favicon.ico"
    try:
        with open(favicon_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        favicon_html = f"""
        <link rel="icon" href="data:image/x-icon;base64,{data}" type="image/x-icon" />
        """
        st.markdown(favicon_html, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Não foi possível carregar o favicon: {e}")

inject_favicon()

# ========================
# FUNÇÕES DE BASE64
# ========================
def get_base64_of_jpg(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

def get_base64_font(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ========================
# FUNDO E FONTES
# ========================
background_image = "background.jpg"
img_base64 = get_base64_of_jpg(background_image)
font_base64 = get_base64_font("font.ttf")

st.markdown(
    f"""
    <style>
    @font-face {{
        font-family: 'CustomFont';
        src: url(data:font/ttf;base64,{font_base64}) format('truetype');
        font-weight: normal;
        font-style: normal;
    }}
    h1.custom-font {{
        font-family: 'CustomFont', sans-serif !important;
        text-align: center;
    }}
    p.custom-font {{
        font-family: 'CustomFont', sans-serif !important;
        font-weight: bold;
        text-align: left;
    }}
    div.stButton > button {{
        font-family: 'CustomFont', sans-serif !important;
    }}
    div.stTextInput > div > input {{
        font-family: 'CustomFont', sans-serif !important;
    }}
    .stApp {{
        background-image: url("data:image/jpg;base64,{img_base64}");
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

# ========================
# SEGREDOS
# ========================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SHEET_ID = st.secrets["SHEET_ID"]
    SERVICE_ACCOUNT_B64 = st.secrets["SERVICE_ACCOUNT_B64"]
except Exception as e:
    st.error("Por favor, configure os segredos: GEMINI_API_KEY, SHEET_ID, SERVICE_ACCOUNT_B64.")
    st.stop()

sa_json = json.loads(base64.b64decode(SERVICE_ACCOUNT_B64).decode())
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
gc = gspread.authorize(creds)

try:
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error(f"Não consegui abrir a planilha. Verifique o SHEET_ID e o compartilhamento.\nErro: {e}")
    st.stop()

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

st.sidebar.header("Dados carregados")
st.sidebar.write("erros:", len(erros_df))
st.sidebar.write("trabalhos:", len(trabalhos_df))
st.sidebar.write("dacen:", len(dacen_df))
st.sidebar.write("psi:", len(psi_df))

# ========================
# CLIENTE GEMINI
# ========================
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
client = genai.Client()

# ========================
# MONTA CONTEXTO
# ========================
def build_context(dfs, max_chars=30000):
    parts = []
    for name, df in dfs.items():
        if df.empty:
            continue
        parts.append(f"--- {name} ---")
        for r in df.to_dict(orient="records"):
            row_items = [f"{k}: {v}" for k, v in r.items() if (v is not None and str(v).strip() != '')]
            parts.append(" | ".join(row_items))
    context = "\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n...[CONTEXTO TRUNCADO]"
    return context

# ========================
# FUNÇÃO PARA BUSCAR COTAÇÃO USD
# ========================
def fetch_usd_brl_rate():
    try:
        url = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        rate = float(data["USDBRL"]["bid"])
        return rate
    except Exception as e:
        st.error(f"Erro ao obter cotação do dólar: {e}")
        return None

# ========================
# CONVERSÃO SOMENTE PARA PREÇOS EM USD
# ========================
def convert_usd_in_text(text, rate):
    # Detecta apenas se tiver símbolo $ ou USD explícito
    pattern = re.compile(
        r'(\$\s?\d+(?:[.,]\d{1,2})|\d+(?:[.,]\d{1,2})\s?USD)',
        re.IGNORECASE
    )

    def repl(match):
        raw = match.group(0)
        amt_str = re.sub(r'[^\d,\.]', '', raw)  # remove símbolos, deixa só números e vírgulas/pontos
        amt_clean = amt_str.replace(",", ".")
        try:
            value = float(amt_clean)
        except:
            return raw
        reais = value * rate
        return f"{raw} (~R$ {reais:,.2f})"

    return pattern.sub(repl, text)

# ========================
# INTERFACE
# ========================
col_esq, col_meio, col_dir = st.columns([1, 2, 1])
with col_meio:
    st.markdown("<h1 class='custom-font'>PlasPrint IA</h1>", unsafe_allow_html=True)
    st.markdown("<p class='custom-font'>Qual a sua dúvida?</p>", unsafe_allow_html=True)
    pergunta = st.text_input("", key="central_input", label_visibility="collapsed")
    buscar = st.button("Buscar", use_container_width=True)

    if buscar:
        if not pergunta.strip():
            st.warning("Digite uma pergunta.")
        else:
            dfs = {"erros": erros_df, "trabalhos": trabalhos_df, "dacen": dacen_df, "psi": psi_df}
            context = build_context(dfs)
            prompt = f"""
Você é um assistente técnico que responde em português.
Baseie-se **apenas** nos dados abaixo (planilhas). 
Responda de forma objetiva, sem citar de onde veio a informação ou a fonte.
Se houver links de imagens, inclua-os no final.

Dados:
{context}

Pergunta:
{pergunta}

Responda de forma clara, sem citar a aba ou linha da planilha.
"""
            try:
                rate = fetch_usd_brl_rate()
                resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                text = resp.text
                if rate:
                    text = convert_usd_in_text(text, rate)
                st.markdown(
                    f"<div style='text-align:center; margin-top:20px;'>{text}</div>",
                    unsafe_allow_html=True
                )
            except Exception as e:
                st.error(f"Erro ao chamar Gemini: {e}")

# ========================
# VERSÃO
# ========================
st.markdown(
    """
    <style>
    .version-tag {
        position: fixed;
        bottom: 10px;
        right: 25px;
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

# ========================
# LOGO NO RODAPÉ
# ========================
def get_base64_img(path):
    with open(path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

img_base64_logo = get_base64_img("logo.png")

st.markdown(
    f"""
    <style>
    .logo-footer {{
        position: fixed;
        bottom: 5px;
        left: 50%;
        transform: translateX(-50%);
        width: 120px;
        z-index: 100;
    }}
    </style>
    <img src="data:image/png;base64,{img_base64_logo}" class="logo-footer" />
    """,
    unsafe_allow_html=True
)
