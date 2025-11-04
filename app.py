import streamlit as st
import pandas as pd
import json, base64, os, re, requests, io
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import yfinance as yf
import datetime
import time
from difflib import SequenceMatcher
import math

# ====== Configuração da página ======
st.set_page_config(page_title="PlasPrint IA", page_icon="favicon.ico", layout="wide")

# ====== Helpers financeiros / texto ======
def get_usd_brl_rate():
    if "usd_brl_cache" in st.session_state:
        cached = st.session_state.usd_brl_cache
        if (datetime.datetime.now() - cached["timestamp"]).seconds < 600:
            return cached["rate"]
    rate = None
    url = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            data = res.json()
            if "USDBRL" in data and "ask" in data["USDBRL"]:
                rate = float(data["USDBRL"]["ask"])
                break
        except:
            pass
    if rate is None:
        try:
            ticker = yf.Ticker("USDBRL=X")
            hist = ticker.history(period="1d")
            if not hist.empty:
                rate = float(hist["Close"].iloc[-1])
        except:
            pass
    st.session_state.usd_brl_cache = {"rate": rate, "timestamp": datetime.datetime.now()}
    return rate

def parse_money_str(s):
    s = s.strip()
    if s.startswith('$'):
        s = s[1:]
    s = s.replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except:
        return None

def to_brazilian(n):
    if 0 < n < 0.01:
        n = 0.01
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def format_dollar_values(text, rate):
    money_regex = re.compile(r'\$\s?\d+(?:[.,]\d+)?')
    found = False
    def repl(m):
        nonlocal found
        found = True
        orig = m.group(0)
        val = parse_money_str(orig)
        if val is None or rate is None:
            return orig
        converted = val * float(rate)
        brl = to_brazilian(converted)
        return f"{orig} (R$ {brl})"
    formatted = money_regex.sub(repl, text)
    if found:
        if not formatted.endswith("\n"):
            formatted += "\n"
        formatted += "(valores sem impostos)"
    return formatted

def process_response(texto):
    padrao_dolar = r"\$\s?\d+(?:[.,]\d+)?"
    if re.search(padrao_dolar, texto):
        rate = get_usd_brl_rate()
        if rate:
            return format_dollar_values(texto, rate)
        else:
            return texto
    return texto

# ====== Favicon / fontes / background (mesmo que antes) ======
def inject_favicon():
    try:
        with open("favicon.ico", "rb") as f:
            data = base64.b64encode(f.read()).decode()
        st.markdown(f'<link rel="icon" href="data:image/x-icon;base64,{data}" type="image/x-icon" />', unsafe_allow_html=True)
    except:
        pass
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

st.markdown(f"""
<style>
@font-face {{
    font-family: 'CustomFont';
    src: url(data:font/ttf;base64,{font_base64}) format('truetype');
}}
h1.custom-font {{ font-family: 'CustomFont', sans-serif !important; text-align: center; font-size: 380%; }}
p.custom-font {{ font-family: 'CustomFont', sans-serif !important; font-weight: bold; text-align: left; }}
div.stButton > button {{ font-family: 'CustomFont', sans-serif !important; }}
div.stTextInput > div > input {{ font-family: 'CustomFont', sans-serif !important; }}
.stApp {{
    background-image: url("data:image/jpg;base64,{img_base64}");
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    background-attachment: fixed;
}}
</style>
""", unsafe_allow_html=True)

# ====== Segredos / conexão Google Sheets ======
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SHEET_ID = st.secrets["SHEET_ID"]
    SERVICE_ACCOUNT_B64 = st.secrets["SERVICE_ACCOUNT_B64"]
except Exception as e:
    st.error("Configure os segredos GEMINI_API_KEY, SHEET_ID e SERVICE_ACCOUNT_B64.")
    st.stop()

sa_json = json.loads(base64.b64decode(SERVICE_ACCOUNT_B64).decode())
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
gc = gspread.authorize(creds)

try:
    sh = gc.open_by_key(SHEET_ID)
except Exception as e:
    st.error(f"Não consegui abrir a planilha: {e}")
    st.stop()

@st.cache_data
def read_ws(name):
    try:
        ws = sh.worksheet(name)
        return pd.DataFrame(ws.get_all_records())
    except Exception as e:
        st.warning(f"Aba '{name}' não pôde ser carregada: {e}")
        return pd.DataFrame()

def refresh_data():
    st.session_state.erros_df = read_ws("erros")
    st.session_state.trabalhos_df = read_ws("trabalhos")
    st.session_state.dacen_df = read_ws("dacen")
    st.session_state.psi_df = read_ws("psi")
    st.session_state.gerais_df = read_ws("gerais")

if "erros_df" not in st.session_state:
    refresh_data()

st.sidebar.header("Dados carregados")
st.sidebar.write("erros:", len(st.session_state.erros_df))
st.sidebar.write("trabalhos:", len(st.session_state.trabalhos_df))
st.sidebar.write("dacen:", len(st.session_state.dacen_df))
st.sidebar.write("psi:", len(st.session_state.psi_df))
st.sidebar.write("gerais:", len(st.session_state.gerais_df))

if st.sidebar.button("Atualizar planilha"):
    refresh_data()
    st.rerun()

# ====== Gemini client ======
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
client = genai.Client()

# ====== Embeddings helper (tenta genai, se falhar usa fallback) ======
def get_embedding_genai(text):
    """
    Tenta obter embedding via genai. Se falhar, retorna None.
    """
    try:
        emb_resp = client.embeddings.create(model="gemini-1.1", input=[text])
        if hasattr(emb_resp, "data"):
            data = emb_resp.data
            if isinstance(data, list) and len(data) > 0:
                vec = data[0].embedding if hasattr(data[0], "embedding") else data[0]["embedding"]
                return vec
        if hasattr(emb_resp, "embeddings"):
            return emb_resp.embeddings[0]
        if isinstance(emb_resp, dict):
            if "data" in emb_resp and len(emb_resp["data"])>0:
                return emb_resp["data"][0].get("embedding")
    except Exception:
        return None
    return None

def cosine_sim(a, b):
    try:
        dot = sum(x*y for x,y in zip(a,b))
        norm_a = math.sqrt(sum(x*x for x in a))
        norm_b = math.sqrt(sum(x*x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
    except Exception:
        return 0.0

def similarity_ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()

@st.cache_data
def load_drive_image(file_id):
    url = f"https://drive.google.com/uc?export=view&id={file_id}"
    res = requests.get(url, timeout=20)
    res.raise_for_status()
    return res.content

# ====== Construir contexto (igual ao seu) ======
def build_context(dfs, max_chars=50000):
    parts = []
    for name, df in dfs.items():
        if df.empty:
            continue
        parts.append(f"--- {name} ---")
        for r in df.to_dict(orient="records"):
            row_items = [f"{k}: {v}" for k,v in r.items() if v is not None and str(v).strip() != '']
            parts.append(" | ".join(row_items))
    context = "\n".join(parts)
    if len(context) > max_chars:
        context = context[:max_chars] + "\n...[CONTEXTO TRUNCADO]"
    return context

# ====== Layout principal ======
col_esq, col_meio, col_dir = st.columns([1,2,1])
with col_meio:
    st.markdown("<h1 class='custom-font'>PlasPrint IA</h1><br>", unsafe_allow_html=True)
    st.markdown("<p class='custom-font'>Qual a sua dúvida?</p>", unsafe_allow_html=True)
    pergunta = st.text_input("", key="central_input", label_visibility="collapsed")

    if "botao_texto" not in st.session_state:
        st.session_state.botao_texto = "Buscar"

    buscar = st.button(st.session_state.botao_texto, use_container_width=True)

    if buscar:
        if not pergunta.strip():
            st.warning("Digite uma pergunta.")
        else:
            st.session_state.botao_texto = "Aguarde"
            with st.spinner("Processando resposta..."):
                dfs = {
                    "erros": st.session_state.erros_df,
                    "trabalhos": st.session_state.trabalhos_df,
                    "dacen": st.session_state.dacen_df,
                    "psi": st.session_state.psi_df,
                    "gerais": st.session_state.gerais_df
                }
                context = build_context(dfs)
                prompt = f"""
Você é um assistente técnico que responde em português.
Baseie-se apenas nos dados abaixo (planilhas). 
Responda de forma objetiva, sem citar a fonte.
Dados:
{context}
Pergunta:
{pergunta}
"""
                try:
                    model_resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                    # Usamos a variável que você informou: 'Resposta'
                    Resposta = model_resp.text

                    # Processa valores em dólar (opcional)
                    output_fmt = process_response(Resposta)

                    # Exibe a resposta (texto que o usuário vê)
                    st.markdown(f"<div style='text-align:center; margin-top:20px;'>{output_fmt.replace(chr(10),'<br/>')}</div>", unsafe_allow_html=True)

                    # Mostra links embutidos no texto da resposta -> apenas como link (não carregar imagem)
                    drive_links_texto = re.findall(r'https?://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)/view', Resposta)
                    for file_id in drive_links_texto:
                        url = f"https://drive.google.com/file/d/{file_id}/view"
                        st.markdown(f"[Abrir link]({url})")

                    # --- Nova lógica otimizada: encontrar 1 linha relevante usando a coluna "Informações" ---
                    combined = pd.concat(dfs.values(), ignore_index=True)

                    # Prepara candidatos (somente linhas com Informações não vazias)
                    candidates = []
                    if "Informações" in combined.columns:
                        for i, row in combined.iterrows():
                            info_val = row.get("Informações")
                            if isinstance(info_val, str) and info_val.strip() != "":
                                candidates.append((i, info_val, row))

                    # se não há candidatos
                    if not candidates:
                        st.info("Nenhum registro com campo 'Informações' encontrado nas planilhas.")
                        st.session_state.botao_texto = "Buscar"
                        continue

                    # Tenta gerar embedding da resposta (se possível)
                    emb_resp = get_embedding_genai(Resposta)
                    use_embeddings = emb_resp is not None

                    scored = []
                    # keywords de país para boost/penalização
                    user_lower = pergunta.lower()
                    country_keywords = {
                        "alem": ["alemã", "alemao", "alemão", "alemanha", "alemã." , "alemã,"],
                        "china": ["chines", "china", "chinês", "chinês."],
                        "italia": ["ital", "italiana", "italiano", "itália"]
                    }
                    def country_boost(text_lower, user_lower):
                        boost = 0.0
                        for key, kws in country_keywords.items():
                            for kw in kws:
                                if kw in user_lower:
                                    # user requested country -> boost if appears in text, penalize otherwise
                                    if kw in text_lower:
                                        boost += 0.12
                                    else:
                                        boost -= 0.12
                                    return boost
                        return 0.0

                    # score each candidate
                    for idx, info_val, row in candidates:
                        info_lower = info_val.lower()
                        # embedding path
                        score = 0.0
                        if use_embeddings:
                            emb_row = get_embedding_genai(info_val)
                            if emb_row is not None:
                                score = cosine_sim(emb_resp, emb_row)
                            else:
                                score = similarity_ratio(Resposta.lower(), info_lower)
                        else:
                            score = similarity_ratio(Resposta.lower(), info_lower)

                        # Boost / penalização heurística
                        # 1) boost/penaliza por país se usuário mencionou
                        score += country_boost(info_lower, user_lower)

                        # 2) penaliza se não mencionar 'máquina' (ou variações)
                        if not any(w in info_lower for w in ["máquina", "maquina", "printer", "impressora", "impressão"]):
                            score -= 0.20

                        # 3) penaliza textos muito curtos (prováveis dicas)
                        if len(info_lower) < 30:
                            score -= 0.20

                        # 4) boost se conteúdo contém palavra "empresa" ou marca conhecida (heurística simples)
                        if any(w in info_lower for w in ["koenig", "bauer", "dacen", "cx-360", "king", "byd"]):
                            score += 0.08

                        scored.append((score, idx, info_val, row))

                    # Ordena por score desc
                    scored.sort(key=lambda x: x[0], reverse=True)

                    # Se não houver score acima do limiar, não mostramos nada
                    MIN_SCORE = 0.30
                    if len(scored) == 0 or scored[0][0] < MIN_SCORE:
                        st.info("Nenhum registro com imagens foi considerado suficientemente relevante para mostrar (tente refinar a pergunta).")
                        st.session_state.botao_texto = "Buscar"
                        continue

                    # Se top1 for bem dominante, mantemos somente ele
                    if len(scored) > 1 and (scored[0][0] - scored[1][0]) >= 0.20:
                        top_choice = scored[0]
                    else:
                        # se não é dominante, ainda podemos optar por mostrar apenas top1 (com cautela)
                        top_choice = scored[0]

                    # Exibir apenas top_choice (1 linha)
                    score, idx, info_val, row = top_choice

                    # Mostrar a informação (ou link se for drive)
                    if isinstance(info_val, str) and "drive.google.com" in info_val:
                        st.markdown(f"[Abrir Informações (linha relacionada)]({info_val})")
                    else:
                        st.markdown(f"**Contexto relacionado (1)** — {info_val}")

                    # Exibir sempre as imagens da coluna "Imagens" desta linha (se houver)
                    if "Imagens" in row.index:
                        img_cell = row.get("Imagens")
                        if isinstance(img_cell, str) and img_cell.strip() != "":
                            # ----- Aqui: imagens separadas por espaço -----
                            parts = re.split(r'\s+', img_cell.strip())
                            displayed_any = False
                            for p in parts:
                                p = p.strip()
                                if not p:
                                    continue
                                # Drive link?
                                if "drive.google.com" in p:
                                    fid_match = re.findall(r'/d/([a-zA-Z0-9_-]+)/', p)
                                    if fid_match:
                                        fid = fid_match[0]
                                        try:
                                            img_bytes = io.BytesIO(load_drive_image(fid))
                                            st.image(img_bytes, use_container_width=True)
                                            displayed_any = True
                                        except Exception:
                                            st.markdown(f"[Abrir imagem]({p})")
                                    else:
                                        # try direct image
                                        try:
                                            st.image(p, use_container_width=True)
                                            displayed_any = True
                                        except Exception:
                                            st.markdown(f"[Abrir imagem]({p})")
                                else:
                                    # not a drive link: try to render
                                    try:
                                        st.image(p, use_container_width=True)
                                        displayed_any = True
                                    except Exception:
                                        st.markdown(f"[Abrir imagem]({p})")

                            if not displayed_any:
                                st.info("Havia links em 'Imagens', mas não foi possível renderizá-los direto — foram exibidos como links.")

                except Exception as e:
                    st.error(f"Erro ao chamar Gemini ou processar resposta: {e}")
        st.session_state.botao_texto = "Buscar"

# ====== Rodapé ======
st.markdown("""
<style>
.version-tag { position: fixed; bottom: 50px; right: 25px; font-size: 12px; color: white; opacity: 0.8; z-index: 100; }
.logo-footer { position: fixed; bottom: 5px; left: 50%; transform: translateX(-50%); width: 120px; z-index: 100; }
</style>
<div class="version-tag">V1.4</div>
""", unsafe_allow_html=True)

def get_base64_img(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

img_base64_logo = get_base64_img("logo.png")
st.markdown(f'<img src="data:image/png;base64,{img_base64_logo}" class="logo-footer" />', unsafe_allow_html=True)
