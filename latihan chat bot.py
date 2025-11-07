import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai
import random

# --- KONFIGURASI API DAN SHEETS ---
API_KEY = (
    st.secrets.get("GEMINI_API_KEY")
    or st.secrets.get("GOOGLE_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
)
if not API_KEY:
    st.error("❌ API key Gemini tidak ditemukan. Tambahkan secret 'GEMINI_API_KEY' di Streamlit Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

if "gcp_service_account" not in st.secrets:
    st.error("❌ Service account Google Sheets tidak ditemukan di Streamlit Secrets.")
    st.stop()

try:
    gcp = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(gcp)
except Exception as e:
    st.error(f"❌ Gagal memuat kredensial GCP: {e}")
    st.stop()

SHEET_KEY = st.secrets.get("SHEET_KEY")
if not SHEET_KEY:
    st.error("Tambahkan 'SHEET_KEY' di Streamlit Secrets.")
    st.stop()

try:
    sheet = gc.open_by_key(SHEET_KEY).worksheet("promo")
    df = pd.DataFrame(sheet.get_all_records())
except Exception as e:
    st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
    st.stop()

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Kozy - Asisten Promo AZKO", page_icon="🛍️", layout="centered")

st.markdown("""
<div style='text-align: center; margin-bottom: 1rem;'>
    <h1 style='margin-bottom: 0;'>🛍️ Kozy – Asisten Promo AZKO</h1>
    <p style='color: gray; font-size: 0.9rem;'>Untuk internal cashier & finance rep</p>
    <p style='color: #d9534f; font-size: 0.8rem;'>⚠️ Kozy dapat membuat kesalahan. Periksa info penting sebelum dipakai.</p>
</div>
""", unsafe_allow_html=True)

# --- STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Halo! Kozy di sini. Mau cek promo atau voucher apa hari ini? 😊"}]
if "last_intent" not in st.session_state:
    st.session_state.last_intent = "greeting"

STOPWORDS = {"di","ke","yang","dan","dari","untuk","ya","ini","itu","dong","nih"}

# --- FUNGSI ---
def prepare_tokens(q):
    q = q.lower()
    return [t for t in re.findall(r"\w+", q) if t not in STOPWORDS]

def count_column_matches(row, tokens):
    cols = ['NAMA_PROMO','PERIODE','SYARAT_UTAMA','DETAIL_DISKON','BANK_PARTNER']
    count = 0
    for col in cols:
        text = str(row.get(col, '')).lower()
        if any(t in text for t in tokens):
            count += 1
    return count

def count_keyword_matches(row, tokens):
    all_text = " ".join(str(v).lower() for v in row.values())
    return sum(1 for t in tokens if t in all_text)

def find_smart_matches(df, query):
    tokens = prepare_tokens(query)
    results = []
    for _, row in df.iterrows():
        cm = count_column_matches(row, tokens)
        km = count_keyword_matches(row, tokens)
        if cm >= 2:
            results.append((row, "high"))
        elif km >= 2:
            results.append((row, "medium"))
    if results:
        highs = [r for r, lvl in results if lvl == "high"]
        meds = [r for r, lvl in results if lvl == "medium"]
        return pd.DataFrame(highs or meds)
    return pd.DataFrame()

def detect_intent(text):
    text = text.lower()
    if re.search(r"\b(halo|hai|hi|hello|selamat (pagi|siang|sore|malam))\b", text): return "greeting"
    if re.search(r"\b(terima kasih|makasih|thanks)\b", text): return "thanks"
    if re.search(r"\b(bye|dah|sampai jumpa)\b", text): return "goodbye"
    return "promo"

# --- UI ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ketik pertanyaan di sini..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent = detect_intent(prompt)
    answer = ""

    if intent == "greeting":
        answer = "Halo! Kozy bantu cek ya, kamu mau info promo atau aturan voucher tertentu?"
    elif intent == "thanks":
        answer = "Siap, sama-sama! Kalau mau cek promo lain, langsung ketik aja ya."
    elif intent == "goodbye":
        answer = "Sip, makasih udah pakai Kozy. Semoga shift-nya lancar! 👋"
    else:
        matches = find_smart_matches(df, prompt)
        if matches.empty:
            answer = (
                "Hmm, sepertinya promo atau voucher itu belum ada di data aku nih. "
                "Biar nggak salah info, coba tanyakan langsung ke *finance rep area kamu* aja ya 😊"
            )
        else:
            promos = []
            for _, r in matches.iterrows():
                promos.append(
                    f"**{r.get('NAMA_PROMO','')}** ({r.get('PROMO_STATUS','')})\n"
                    f"📅 Periode: {r.get('PERIODE','')}\n"
                    f"📝 {r.get('SYARAT_UTAMA','')}\n"
                    f"💰 {r.get('DETAIL_DISKON','')}\n"
                    f"🏦 Bank: {r.get('BANK_PARTNER','')}"
                )
            hasil = "\n\n".join(promos)
            model = genai.GenerativeModel("models/gemini-flash-latest")
            instr = (
                "Kamu adalah Kozy, asisten internal untuk cashier AZKO. "
                "Gunakan bahasa kerja yang sopan tapi lugas. "
                "Sampaikan hasil promo di bawah dengan jelas, hindari gaya promosi ke pelanggan."
            )
            try:
                resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                answer = getattr(resp, "text", hasil)
            except Exception:
                answer = hasil

    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.last_intent = intent
