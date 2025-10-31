import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai
import random

# =============== KONFIGURASI API DAN GOOGLE SHEETS ===============
API_KEY = st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    st.error("API key Gemini tidak ditemukan. Tambahkan secret 'GEMINI_API_KEY' di Streamlit Secrets, lalu Reboot App.")
    st.stop()

genai.configure(api_key=API_KEY)

if "gcp_service_account" not in st.secrets:
    st.error("Service account Google Sheets tidak ditemukan di Streamlit Secrets.")
    st.stop()

gcp = dict(st.secrets["gcp_service_account"])
gc = gspread.service_account_from_dict(gcp)

SHEET_KEY = st.secrets.get("SHEET_KEY")
if not SHEET_KEY:
    st.error("Tambahkan 'SHEET_KEY' di Streamlit Secrets dengan ID spreadsheet kamu.")
    st.stop()

sheet = gc.open_by_key(SHEET_KEY).worksheet("promo")
df = pd.DataFrame(sheet.get_all_records())

# =============== KONFIGURASI HALAMAN ===============
st.set_page_config(page_title="Kozy - Asisten Promo AZKO", page_icon="🛍️", layout="centered")
st.title("🛍️ Kozy – Asisten Promo AZKO")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hai! Aku Kozy, asisten promo dari AZKO. Lagi cari promo apa nih? 😉"}
    ]
    st.session_state.context = ""

# =============== FUNGSI PENDUKUNG ===============
def random_comment():
    return random.choice([
        "Hehe, lumayan banget promonya 😄",
        "Cocok nih buat yang suka hemat!",
        "Wah, promo ini sering banget dicari orang juga!",
        "Mantap, bisa dipakai tiap akhir pekan lho!"
    ])

def detect_intent(text: str) -> str:
    text = text.lower().strip()
    if re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", text): return "greeting"
    if re.search(r"\b(apa kabar|gimana kabar|lagi ngapain)\b", text): return "smalltalk"
    if re.search(r"\b(terima kasih|makasih|thanks)\b", text): return "thanks"
    if re.search(r"\b(dah|bye|sampai jumpa)\b", text): return "goodbye"
    return "promo"

# =============== SMART SEARCH (AI-ASSISTED MATCHING) ===============
def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Gunakan model Gemini buat ambil kata kunci penting dari pertanyaan user."""
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"Tentukan 3 kata kunci utama dari pertanyaan berikut untuk mencari promo: '{query}'. Balas hanya kata kunci dipisahkan koma."
    try:
        keywords = model.generate_content(prompt).text.lower().split(",")
        keywords = [k.strip() for k in keywords if k.strip()]
    except Exception:
        keywords = [query.lower()]

    mask = pd.Series([False] * len(df))
    for kw in keywords:
        for c in df.columns:
            mask |= df[c].astype(str).str.lower().str.contains(kw, na=False)
    return df[mask]

# =============== UI CHAT ===============
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ketik pesanmu di sini..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    intent = detect_intent(prompt)
    answer = ""

    # ---- Greet, Smalltalk, Dll ----
    if intent == "greeting":
        if "pagi" in prompt.lower(): greet = "Selamat pagi 🌞"
        elif "siang" in prompt.lower(): greet = "Selamat siang ☀️"
        elif "sore" in prompt.lower(): greet = "Selamat sore 🌇"
        elif "malam" in prompt.lower(): greet = "Selamat malam 🌙"
        else: greet = "Halo 👋"
        answer = f"{greet}! Aku Kozy, asisten promo dari AZKO. Mau aku bantu cari promo apa hari ini?"

    elif intent == "smalltalk":
        answer = "Aku baik nih, makasih udah nyapa 😄 Lagi siap bantu kamu cari promo menarik!"

    elif intent == "thanks":
        answer = "Sama-sama! Senang bisa bantu. Mau cek promo lain juga?"

    elif intent == "goodbye":
        answer = "Sampai jumpa ya! Semoga harimu menyenangkan dan dapet promo terbaik 🛍️"

    # ---- Promo Search ----
    else:
        matches = find_smart_matches(df, prompt)
        if matches.empty:
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                instr = (
                    "Kamu adalah Kozy, asisten promo AZKO yang santai tapi cerdas. "
                    "Jika user menanyakan promo yang tidak ada, jawab sopan, ramah, dan arahkan untuk hubungi finance rep area mereka."
                )
                resp = model.generate_content(instr + "\nUser: " + prompt)
                answer = getattr(resp, "text", "Maaf, untuk promo itu aku belum dapat konfirmasi. Coba hubungi finance rep area kamu ya 🙏")
            except Exception:
                answer = "Maaf, untuk promo itu aku belum dapat konfirmasi. Coba hubungi finance rep area kamu ya 🙏"
        else:
            promos = []
            for _, r in matches.iterrows():
                promos.append(
                    f"• **{r.get('NAMA_PROMO','')}** ({r.get('PROMO_STATUS','')})\n"
                    f"📅 {r.get('PERIODE','')}\n📝 {r.get('SYARAT_UTAMA','')}\n💰 {r.get('DETAIL_DISKON','')}\n🏦 {r.get('BANK_PROV','')}"
                )
            hasil = "\n\n".join(promos)
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                instr = "Sampaikan hasil promo berikut dengan gaya hangat dan alami seperti asisten pribadi."
                resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                answer = getattr(resp, "text", hasil + "\n\n" + random_comment())
            except Exception:
                answer = hasil + "\n\n" + random_comment()

    # ---- Tampilkan Balasan ----
    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.context += f"User: {prompt}\nKozy: {answer}\n"
