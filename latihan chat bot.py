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
st.title("🛍️ Kozy – Asisten Promo AZKO")

# --- STATE INISIALISASI ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hai! Aku Kozy, asisten promo AZKO. Lagi cari promo apa nih? 😉"}
    ]
if "context" not in st.session_state:
    st.session_state.context = ""
if "last_intent" not in st.session_state:
    st.session_state.last_intent = "greeting"

# --- FUNGSI PENDUKUNG ---
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
    if re.search(r"\b(promo|diskon|potongan|harga|cashback|bank)\b", text): return "promo"
    return "other"

def detect_topic_change(last_intent: str, new_text: str):
    new_intent = detect_intent(new_text)
    # Kalau intent baru beda dari sebelumnya, berarti ganti topik
    if new_intent != last_intent:
        return True, new_intent
    return False, new_intent

def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
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

# --- UI CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT ---
if prompt := st.chat_input("Ketik pesanmu di sini..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    topic_changed, intent = detect_topic_change(st.session_state.last_intent, prompt)

    # --- Reset konteks kalau ganti topik ---
    if topic_changed:
        st.session_state.context = ""
    
    answer = ""

    if intent == "greeting":
        greet = "Halo 👋"
        if "pagi" in prompt: greet = "Selamat pagi 🌞"
        elif "siang" in prompt: greet = "Selamat siang ☀️"
        elif "sore" in prompt: greet = "Selamat sore 🌇"
        elif "malam" in prompt: greet = "Selamat malam 🌙"
        answer = f"{greet}! Aku Kozy, asisten promo dari AZKO. Mau aku bantu cari promo apa hari ini?"

    elif intent == "smalltalk":
        answer = "Aku baik nih 😄 Siap bantu kamu cari promo menarik!"

    elif intent == "thanks":
        answer = "Sama-sama! Mau aku bantu cari promo lain juga?"

    elif intent == "goodbye":
        answer = "Sampai jumpa ya! Semoga harimu menyenangkan dan dapet promo terbaik 🛍️"

    elif intent == "promo":
        matches = find_smart_matches(df, prompt)
        if matches.empty:
            model = genai.GenerativeModel("gemini-2.5-flash")
            instr = (
                "Kamu adalah Kozy, asisten promo AZKO yang ramah. "
                "Jika user menanyakan promo yang tidak ada, jawab sopan dan arahkan ke finance rep."
            )
            try:
                resp = model.generate_content(instr + "\nUser: " + prompt)
                answer = getattr(resp, "text", "Maaf, promo itu belum tersedia. Coba hubungi finance rep area kamu ya 🙏")
            except Exception:
                answer = "Maaf, promo itu belum tersedia. Coba hubungi finance rep area kamu ya 🙏"
        else:
            promos = []
            for _, r in matches.iterrows():
                promos.append(
                    f"• **{r.get('NAMA_PROMO','')}** ({r.get('PROMO_STATUS','')})\n"
                    f"📅 Periode: {r.get('PERIODE','')}\n"
                    f"📝 {r.get('SYARAT_UTAMA','')}\n"
                    f"💰 {r.get('DETAIL_DISKON','')}\n"
                    f"🏦 Bank: {r.get('BANK_PARTNER','')}"
                )
            hasil = "\n\n".join(promos)
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                instr = "Sampaikan hasil promo berikut dengan gaya hangat dan natural seperti asisten pribadi."
                resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                answer = getattr(resp, "text", hasil + "\n\n" + random_comment())
            except Exception:
                answer = hasil + "\n\n" + random_comment()

    else:
        # fallback kalau konteks gak dikenali
        answer = "Hmm, bisa dijelaskan sedikit lagi maksud kamu? Mau bahas promo atau hal lain?"

    # --- Tampilkan jawaban ---
    with st.chat_message("assistant"):
        st.markdown(answer)

    # --- Simpan state ---
    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.context += f"User: {prompt}\nKozy: {answer}\n"
    st.session_state.last_intent = intent
