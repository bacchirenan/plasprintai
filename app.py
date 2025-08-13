import streamlit as st
import pandas as pd
import json, base64, os, re, io, requests
import gspread
from google.oauth2.service_account import Credentials
from google import genai

st.set_page_config(page_title="PlasPrint IA", layout="wide")

# === Carregar segredos (streamlit secrets) ===
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    SHEET_ID = st.secrets["SHEET_ID"]
    GOOGLE_SHEETS_CREDENTIALS = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
except Exception as e:
    st.error("Erro ao carregar segredos. Verifique o arquivo .streamlit/secrets.toml.")
    st.stop()

# === Conectar ao Google Sheets ===
try:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(GOOGLE_SHEETS_CREDENTIALS, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1
except Exception as e:
    st.error(f"Erro ao conectar ao Google Sheets: {e}")
    st.stop()

# === Função para exibir imagens do Google Drive ===
def show_drive_images_from_text(text):
    """
    Procura links do Google Drive no texto e exibe as imagens no Streamlit.
    Funciona tanto para links com 'id=' quanto para links já no formato export/view.
    """
    drive_links = re.findall(
        r'(https?://drive\.google\.com[^\s]+)',
        text,
        re.IGNORECASE
    )

    if drive_links:
        st.markdown("### Imagens do Google Drive:")
        for link in drive_links:
            try:
                if "export=view" in link:
                    img_url = link
                else:
                    match = re.search(r"id=([a-zA-Z0-9_-]+)", link)
                    if match:
                        file_id = match.group(1)
                        img_url = f"https://drive.google.com/uc?export=view&id={file_id}"
                    else:
                        continue
                st.image(img_url, use_container_width=True)
            except Exception as e:
                st.warning(f"Não foi possível carregar a imagem: {link}\nErro: {e}")

# === Configurar cliente do Gemini ===
try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as e:
    st.error(f"Erro ao configurar Gemini API: {e}")
    st.stop()

model = genai.GenerativeModel("gemini-1.5-pro")

# === Interface ===
st.markdown("<h1 style='text-align: center; font-size: 40px;'>PlasPrint IA</h1>", unsafe_allow_html=True)
st.write("\n")
st.markdown("<h3 style='text-align: left;'>Qual a sua dúvida?</h3>", unsafe_allow_html=True)

user_input = st.text_area("", height=100)

if st.button("Enviar"):
    if user_input.strip():
        try:
            resp = model.generate_content(user_input)
            if hasattr(resp, "text"):
                st.markdown(f"<div style='text-align: center;'>{resp.text}</div>", unsafe_allow_html=True)
                # Exibir imagens do Google Drive encontradas na resposta
                show_drive_images_from_text(resp.text)
            else:
                st.warning("A resposta não contém texto.")
        except Exception as e:
            st.error(f"Erro ao gerar resposta: {e}")
    else:
        st.warning("Por favor, digite uma pergunta.")

# === Rodapé ===
st.markdown(
    """
    <div style='text-align: right; color: white; font-size: 10px;'>
        V1.0
    </div>
    """,
    unsafe_allow_html=True
)
