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

STOPWORDS = {"di", "ke", "yang", "dan", "dari", "untuk", "ya", "ini", "itu", "dong", "nih", "dgn", "pakai"}

# --- FUNGSI UTIL ---
def prepare_tokens(q: str):
    q = (q or "").lower()
    tokens = re.findall(r"\w+", q)
    tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens

def count_column_matches(row: pd.Series, tokens: list):
    cols = ['NAMA_PROMO', 'PERIODE', 'SYARAT_UTAMA', 'DETAIL_DISKON', 'BANK_PARTNER']
    count = 0
    for col in cols:
        text = str(row.get(col, "")).lower()
        if any(t in text for t in tokens):
            count += 1
    return count

def count_keyword_matches(row: pd.Series, tokens: list):
    # safer: use row.tolist() then join, convert to lowercase
    all_text = " ".join(map(str, row.tolist())).lower()
    return sum(1 for t in tokens if t in all_text)

def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    tokens = prepare_tokens(query)
    results = []  # list of tuples (index, row, level)

    # quick path: prefer active promos first (if column exists)
    prefer_active = 'PROMO_STATUS' in df.columns

    rows_iter = df.iterrows()
    for idx, row in rows_iter:
        # If prefer active, skip non-AKTIF to speed up (but still allow if no active found later)
        if prefer_active and str(row.get('PROMO_STATUS', '')).strip().upper() != "AKTIF":
            # mark but still consider later by skipping now
            pass

        cm = count_column_matches(row, tokens)
        km = count_keyword_matches(row, tokens)

        if cm >= 2:
            results.append((idx, row, "high"))
        elif km >= 2:
            results.append((idx, row, "medium"))
        # else ignore

    if not results:
        return pd.DataFrame()  # empty

    # prefer high-confidence results
    high_rows = [r for i, r, lvl in results if lvl == "high"]
    med_rows = [r for i, r, lvl in results if lvl == "medium"]

    chosen = high_rows if high_rows else med_rows
    # convert list of Series to DataFrame (reset index)
    return pd.DataFrame(chosen)

def detect_intent(text: str) -> str:
    t = (text or "").lower()
    if re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", t):
        return "greeting"
    if re.search(r"\b(terima kasih|makasih|thanks)\b", t):
        return "thanks"
    if re.search(r"\b(bye|dah|sampai jumpa)\b", t):
        return "goodbye"
    # promo-related keywords (expanded)
    if re.search(r"\b(promo|diskon|potongan|harga|cashback|bank|voucher|kupon|pluxee|evoucher|e-voucher|map|nota|manual|kode)\b", t):
        return "promo"
    return "other"

# --- UI CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT ---
if prompt := st.chat_input("Ketik pertanyaan di sini..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent = detect_intent(prompt)
    answer = ""

    if intent == "greeting":
        answer = "Halo. Kozy bantu cek ya — mau info promo atau aturan voucher apa?"
    elif intent == "thanks":
        answer = "Sama-sama. Kalau mau cek promo lain tinggal ketik."
    elif intent == "goodbye":
        answer = "Sip, semoga shift-nya lancar. 👋"
    elif intent == "promo":
        matches = find_smart_matches(df, prompt)

        if matches.empty:
            # fallback message (concise & internal)
            answer = (
                "Hmm, sepertinya promo atau voucher yang kamu maksud belum ada di data aku nih. "
                "Untuk lebih pastinya, silakan tanyakan langsung ke finance rep area kamu ya 😊"
            )
        else:
            # format results for internal/cashier tone
            promos = []
            for _, r in matches.iterrows():
                promos.append(
                    f"• **{r.get('NAMA_PROMO','')}** — {r.get('PROMO_STATUS','')}\n"
                    f"  Periode: {r.get('PERIODE','')}\n"
                    f"  Syarat utama: {r.get('SYARAT_UTAMA','')}\n"
                    f"  Detail: {r.get('DETAIL_DISKON','')}\n"
                    f"  Bank/Partner: {r.get('BANK_PARTNER','')}"
                )
            hasil = "\n\n".join(promos)

            # Use Gemini to rephrase in internal tone, but keep it short
            model = genai.GenerativeModel("models/gemini-flash-latest")
            instr = (
                "Kamu adalah Kozy, asisten internal untuk cashier AZKO. "
                "Gunakan bahasa kerja yang sopan, lugas, dan singkat. "
                "Sampaikan hanya informasi relevan untuk cashier, jangan bersikap seperti layanan pelanggan."
            )
            try:
                resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                # prefer model text but fallback to hasil if empty
                model_text = getattr(resp, "text", "").strip()
                answer = model_text if model_text else hasil
            except Exception:
                answer = hasil
    else:
        answer = "Maaf, bisa jelaskan maksudnya sedikit lagi? Mau bahas promo/voucher atau hal lain?"

    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.last_intent = intent
