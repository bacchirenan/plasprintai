import streamlit as st
import pandas as pd
import json, base64, os, re, requests, io
import gspread
from google.oauth2.service_account import Credentials
from google import genai
import yfinance as yf

# ===== Configuração da página =====
st.set_page_config(page_title="PlasPrint IA", page_icon="favicon")

# ===== Função para buscar cotação USD/BRL =====
@st.cache_data(ttl=600)  # mantém cache por 10 minutos
def get_usd_brl_rate():
    """Busca a cotação do dólar em BRL com fallback e cache."""
    # --- Tentativa 1: AwesomeAPI ---
    try:
        url = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        if "USDBRL" in data and "ask" in data["USDBRL"]:
            rate = float(data["USDBRL"]["ask"])
            st.session_state["last_usd_brl"] = rate
            return rate
    except Exception as e:
        st.warning(f"Falha na AwesomeAPI: {e}")

    # --- Tentativa 2: Yahoo Finance ---
    try:
        ticker = yf.Ticker("USDBRL=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            st.session_state["last_usd_brl"] = rate
            return rate
    except Exception as e:
        st.warning(f"Falha no Yahoo Finance: {e}")

    # --- Tentativa 3: Última cotação válida ---
    if "last_usd_brl" in st.session_state:
        st.info("Usando última cotação válida salva em cache.")
        return st.session_state["last_usd_brl"]

    return None


# ===== Função para processar resposta da IA =====
def process_response(texto):
    """
    Procura valores em dólar no texto da IA.
    Se houver, converte para BRL e adiciona aviso.
    """
    padrao_dolar = r"\$\s?\d+(?:\.\d+)?"
    valores_encontrados = re.findall(padrao_dolar, texto)

    if valores_encontrados:
        usd_brl = get_usd_brl_rate()  # só chama se encontrou valores em USD
        if usd_brl:
            for v in valores_encontrados:
                try:
                    valor_usd = float(v.replace("$", "").strip())
                    valor_brl = valor_usd * usd_brl
                    texto = texto.replace(
                        v, f"{v} (≈ R${valor_brl:,.2f})"
                    )
                except:
                    continue
            texto += "\n\n(valores sem impostos)"
        else:
            texto += "\n\n[Não foi possível obter a cotação do dólar no momento.]"

    return texto


# ===== Exemplo de uso =====
st.title("PlasPrint IA")

pergunta = st.text_area("Digite sua pergunta:")
if st.button("Enviar") and pergunta.strip():
    # Aqui você chamaria a IA (simulando com texto de teste)
    resposta_ia = "O custo estimado é $12.5 por unidade."
    
    resposta_final = process_response(resposta_ia)
    st.write(resposta_final)
