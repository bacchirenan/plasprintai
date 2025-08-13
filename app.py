import streamlit as st
import pandas as pd
import json, base64, os, re, requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import io

# ===== Funções auxiliares =====

# Cotação do dólar
def get_usd_brl_rate():
    try:
        res = requests.get("https://economia.awesomeapi.com.br/json/last/USD-BRL")
        data = res.json()
        return float(data["USDBRL"]["ask"])
    except Exception as e:
        st.error(f"Erro ao obter cotação do dólar: {e}")
        return None

# Formatar valores em dólar
def format_dollar_values(text, rate):
    def repl(match):
        dollar_str = match.group(0)
        try:
            val = float(dollar_str.replace("$", "").replace(",", "").strip())
            converted = val * rate
            return f"{dollar_str} (R$ {converted:,.2f})"
        except:
            return dollar_str

    if "$" in text:
        formatted = re.sub(r"\$\d+(?:\.\d+)?", repl, text)
        if not formatted.endswith("\n"):
            formatted += "\n"
        formatted += "(valores sem impostos)"
        return formatted
    else:
        return text

# ===== Configuração da página =====
st.set_page_config(page_title="PlasPrint IA", page_icon="favicon.ico", layout="wide")

def inject_favicon():
    favicon_path = "favicon.ico"
    try:
        with open(favicon_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        favicon_html = f"""<link rel="icon" href="data:image/x-icon;base64,{data}" type="image/x-icon" />"""
        st.markdown(favicon_html, unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Não foi possível carregar o favicon: {e}")

inject_favicon()

def get_base64_of_jpg(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

def get_base64_font(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

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
        font-size: 380%;
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

# ===== Carregar segredos =====
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
    st.error(f"Não consegui abrir a planilha. Erro: {e}")
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

# ===== Cliente Gemini =====
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
client = genai.Client()

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

def show_drive_images_from_text(text):
    # Extrai IDs válidos de arquivos do Google Drive
    drive_links = re.findall(r'https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)[^/]*/view', text)
    if drive_links:
        for file_id in drive_links:
            file_id = file_id.rstrip("_")  # Remove underscore final se houver
            direct_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            try:
                response = requests.get(direct_url)
                response.raise_for_status()
                img_bytes = io.BytesIO(response.content)
                st.image(img_bytes, use_container_width=True)
            except Exception as e:
                st.warning(f"Não foi possível carregar a imagem do Drive: {direct_url}\nErro: {e}")

# ===== Layout principal =====
col_esq, col_meio, col_dir = st.columns([1, 2, 1])
with col_meio:
    st.markdown("<h1 class='custom-font'>PlasPrint IA</h1><br>", unsafe_allow_html=True)
    st.markdown("<p class='custom-font'>Qual a sua dúvida?</p>", unsafe_allow_html=True)
    pergunta = st.text_input("", key="central_input", label_visibility="collapsed")

    # ===== Estado do botão =====
    if "botao_texto" not in st.session_state:
        st.session_state.botao_texto = "Buscar"

    buscar = st.button(st.session_state.botao_texto, use_container_width=True)

    if buscar:
        if not pergunta.strip():
            st.warning("Digite uma pergunta.")
        else:
            st.session_state.botao_texto = "Aguarde"
            with st.spinner("Processando resposta..."):
                rate = get_usd_brl_rate()
                if rate is None:
                    st.error("Não foi possível obter a cotação do dólar.")
                else:
                    dfs = {
                        "erros": erros_df,
                        "trabalhos": trabalhos_df,
                        "dacen": dacen_df,
                        "psi": psi_df
                    }
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
                        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                        output_fmt = format_dollar_values(resp.text, rate)

                        # Mostra o texto formatado
                        st.markdown(
                            f"<div style='text-align:center; margin-top:20px;'>{output_fmt.replace(chr(10),'<br/>')}</div>",
                            unsafe_allow_html=True
                        )

                        # Mostra apenas as imagens do Google Drive
                        show_drive_images_from_text(resp.text)

                    except Exception as e:
                        st.error(f"Erro ao chamar Gemini: {e}")
            st.session_state.botao_texto = "Buscar"

# ===== Versão no rodapé =====
st.markdown(
    """
    <style>
    .version-tag {
        position: fixed;
        bottom: 50px;
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

# ===== Logo no rodapé =====
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
