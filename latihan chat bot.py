import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai
import random

# Ambil API key dengan fallback (tidak memicu KeyError)
API_KEY = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    st.error("API key Gemini tidak ditemukan. Tambahkan secret 'GEMINI_API_KEY' (atau 'GOOGLE_API_KEY') di Streamlit Secrets, lalu Reboot App.")
    st.stop()

genai.configure(api_key=API_KEY)

# Koneksi Google Sheets (service account harus ada di secrets)
if "gcp_service_account" not in st.secrets:
    st.error("Service account Google Sheets tidak ditemukan di Streamlit Secrets sebagai 'gcp_service_account'.")
    st.stop()

gcp = dict(st.secrets["gcp_service_account"])
gc = gspread.service_account_from_dict(gcp)

SHEET_KEY = st.secrets.get("SHEET_KEY") or st.secrets.get("SHEET_ID")
if not SHEET_KEY:
    st.error("SHEET_KEY / SHEET_ID tidak ditemukan di Streamlit Secrets. Tambahkan key 'SHEET_KEY' dengan ID spreadsheet.")
    st.stop()

sheet = gc.open_by_key(SHEET_KEY).worksheet("promo")
df = pd.DataFrame(sheet.get_all_records())

st.set_page_config(page_title="AZKO Promo Chatbot", page_icon="🤖", layout="centered")
st.title("🤖 AZKO – Asisten Promo Bank")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hai! Aku AZKO, asisten promo. Mau cari promo apa hari ini?"}
    ]
    st.session_state.context = ""

def random_comment():
    choices = [
        "Hehe, promo ini lumayan menarik nih.",
        "Wah, cocok banget buat yang suka hemat.",
        "Waduh, sayang aku cuma bot, gak bisa ikutan belanja 😅"
    ]
    return random.choice(choices)

def detect_intent(text: str) -> str:
    text = text.lower().strip()
    if re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", text): return "greeting"
    if re.search(r"\b(apa kabar|gimana kabar|lagi ngapain)\b", text): return "smalltalk"
    if re.search(r"\b(terima kasih|makasih|thanks)\b", text): return "thanks"
    if re.search(r"\b(dah|bye|sampai jumpa)\b", text): return "goodbye"
    if re.search(r"\b(maaf|salah|error|gagal)\b", text): return "apology"
    return "promo"

def find_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    q = query.lower().strip()
    if not q: return df.iloc[0:0]
    mask = pd.Series([False] * len(df))
    for c in df.columns:
        mask |= df[c].astype(str).str.lower().str.contains(q, na=False)
    return df[mask]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ketik pesanmu di sini..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent = detect_intent(prompt)
    answer = ""

    if intent == "greeting":
        lower = prompt.lower()
        if "pagi" in lower: greet = "Selamat pagi 🌞"
        elif "siang" in lower: greet = "Selamat siang ☀️"
        elif "sore" in lower: greet = "Selamat sore 🌇"
        elif "malam" in lower: greet = "Selamat malam 🌙"
        else: greet = "Halo 👋"
        answer = f"{greet}! Saya AZKO — asisten promo yang siap bantu. Mau cari promo apa hari ini?"

    elif intent == "smalltalk":
        answer = "Saya baik, terima kasih! Siap bantu cari promo keren buat kamu 😄"

    elif intent == "thanks":
        answer = "Sama-sama 🙏 Kalau mau cek promo lain tinggal ketik saja."

    elif intent == "goodbye":
        answer = "Sampai jumpa! Semoga harimu menyenangkan 👋"

    elif intent == "apology":
        answer = "Gak apa-apa — lanjut aja, mau cari promo apa?"

    else:
        # gunakan konteks singkat
        context_prompt = st.session_state.context + f"User: {prompt}\n"
        matches = find_matches(df, prompt)
        if matches.empty:
            instr = (
                "Kamu adalah AZKO, asisten promo bank yang pintar dan santai. "
                "Jika user menanyakan promo yang tidak ada di data, jawab sopan, singkat, dan sarankan langkah berikutnya."
            )
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                resp = model.generate_content(instr + "\n\n" + context_prompt + "\nUser: " + prompt)
                answer = getattr(resp, "text", "Maaf, saya belum punya konfirmasi untuk promo itu. Coba hubungi finance rep area.")
            except Exception:
                answer = "Maaf, saya belum punya konfirmasi untuk promo itu. Coba hubungi finance rep area."
        else:
            promos = []
            for _, r in matches.iterrows():
                promos.append(
                    f"• **{r.get('NAMA_PROMO','')}** ({r.get('PROMO_STATUS','')})\n  📅 {r.get('PERIODE','')}\n  📝 {r.get('SYARAT_UTAMA','')}\n  💰 {r.get('DETAIL_DISKON','')}"
                )
            hasil = "\n\n".join(promos)
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                instr = "Jelaskan ringkas dan ramah berdasarkan data promo berikut:"
                resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                answer = getattr(resp, "text", hasil + "\n\n" + random_comment())
            except Exception:
                answer = hasil + "\n\n" + random_comment()

    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.context += f"User: {prompt}\nAZKO: {answer}\n"
