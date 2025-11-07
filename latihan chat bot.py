import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

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
st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

# --- HEADER UTAMA ---
st.markdown(
    """
    <div style='text-align: center; margin-bottom: 1rem;'>
        <h1 style='margin-bottom: 0;'>🛍️ Kozy – Asisten Kasir AZKO</h1>
        <p style='color: gray; font-size: 0.9rem;'>supported by <b>Gemini AI</b></p>
        <p style='color: #d9534f; font-size: 0.8rem;'>⚠️ Kozy dapat membuat kesalahan. Selalu konfirmasi info penting.</p>
    </div>
    """,
    unsafe_allow_html=True
)

# --- STATE INISIALISASI ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Halo! Aku Kozy, asisten promo internal AZKO. Ada info promo apa yang kamu butuh? 🧐"}
    ]
if "context" not in st.session_state:
    st.session_state.context = ""
if "last_intent" not in st.session_state:
    st.session_state.last_intent = "greeting"

# --- FUNGSI PENDUKUNG ---

# 🛑 FUNGSI LAMA (regex) DIHAPUS: def detect_intent(text: str) -> str:
# 🛑 FUNGSI LAMA DIHAPUS: def detect_topic_change(last_intent: str, new_text: str):
# 🛑 FUNGSI LAMA DIHAPUS: def random_comment():

# ✨ FUNGSI BARU: Deteksi intent menggunakan AI (Gemini)
# Ini akan jauh lebih baik dalam menangani typo seperti "vucher" atau "voucer"
@st.cache_data(ttl=3600) # Cache hasil agar tidak boros API
def detect_intent_ai(text: str) -> str:
    text = text.lower().strip()
    
    # 1. Handle sapaan umum non-AI agar cepat
    simple_greetings = re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", text)
    simple_thanks = re.search(r"\b(terima kasih|makasih|thanks|tq)\b", text)
    simple_goodbye = re.search(r"\b(dah|bye|sampai jumpa|exit)\b", text)
    
    if simple_greetings: return "greeting"
    if simple_thanks: return "thanks"
    if simple_goodbye: return "goodbye"

    # 2. Gunakan AI untuk membedakan "promo" dari "other" (basa-basi/di luar topik)
    try:
        model = genai.GenerativeModel("models/gemini-flash-latest")
        prompt = f"""
        Klasifikasikan maksud (intent) dari user (seorang kasir) berikut.
        Pilih HANYA SATU dari kategori ini: [promo, smalltalk, other]
        
        - "promo": Semua pertanyaan tentang diskon, voucher, bank, metode pembayaran, cashback, dll. (TERMASUK TYPO seperti 'vucher', 'voucer', 'discon', dll).
        - "smalltalk": Basa-basi (apa kabar, lagi apa, kamu siapa).
        - "other": Pertanyaan di luar topik promo.
        
        User: "{text}"
        Intent:
        """
        response = model.generate_content(prompt).text.strip().lower()
        
        # Membersihkan respons AI
        if "promo" in response: return "promo"
        if "smalltalk" in response: return "smallaltk"
        if "other" in response: return "other"
        
        # Fallback jika AI menjawab aneh, anggap saja "promo"
        return "promo"
    except Exception:
        # Failsafe jika API call gagal, anggap "promo"
        return "promo"

def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    model = genai.GenerativeModel("models/gemini-flash-latest")
    # Prompt ini sudah bagus, akan menangani typo "vucher" menjadi "voucher"
    prompt = f"Tentukan 3 kata kunci utama dari pertanyaan berikut untuk mencari promo: '{query}'. Balas hanya kata kunci dipisahkan koma."
    try:
        keywords = model.generate_content(prompt).text.lower().split(",")
        keywords = [k.strip() for k in keywords if k.strip()]
    except Exception:
        keywords = [query.lower()]

    mask = pd.Series([False] * len(df))
    for kw in keywords:
        for c in df.columns:
            # Pastikan kolom adalah string sebelum menggunakan .str
            if pd.api.types.is_string_dtype(df[c]):
                mask |= df[c].str.lower().str.contains(kw, na=False)
            else:
                mask |= df[c].astype(str).str.lower().str.contains(kw, na=False)
    return df[mask]

# --- UI CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT ---
if prompt := st.chat_input("Ketik info promo yang dicari..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # ✨ LOGIKA BARU: Panggil fungsi AI untuk deteksi intent
    intent = detect_intent_ai(prompt)
    topic_changed = (intent != st.session_state.last_intent)
    
    if topic_changed:
        st.session_state.context = ""
    
    answer = ""
    
    # Jawaban default jika terjadi error
    default_fallback_answer = "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."
    # Jawaban "tanya finrep" (nada disesuaikan untuk kasir)
    finrep_answer = (
        "Hmm, aku cek di sistem, data untuk voucher/promo itu **belum ter-update** nih. "
        "Info lebih pastinya, coba **kontak Finrep area kamu** ya, biar aman. 👍"
    )

    if intent == "greeting":
        greet = "Halo 👋"
        if "pagi" in prompt: greet = "Selamat pagi 🌞"
        elif "siang" in prompt: greet = "Selamat siang ☀️"
        elif "sore" in prompt: greet = "Selamat sore 🌇"
        elif "malam" in prompt: greet = "Selamat malam 🌙"
        answer = f"{greet}! Aku Kozy, asisten promo internal AZKO. Ada yang bisa dibantu?"

    elif intent == "smalltalk":
        answer = "Aku Kozy, asisten AI kamu. Siap bantu cari info promo. Ada yang ditanyakan soal promo?"

    elif intent == "thanks":
        answer = "Sama-sama! 👍 Lanjut cari info lain?"

    elif intent == "goodbye":
        answer = "Oke, sampai nanti ya! Selamat bekerja. 🛍️"

    elif intent == "promo":
        try:
            matches = find_smart_matches(df, prompt)

            if matches.empty:
                # === BLOK MODIFIKASI (Indomart vs Ultra) - DARI PERMINTAAN SEBELUMNYA ===
                # (Ini sudah benar, akan menangani kasus "vucher MAP" dan "voucer ultra")
                
                try:
                    # 1. Buat model AI khusus untuk pengecekan
                    check_model = genai.GenerativeModel("models/gemini-flash-latest")
                    
                    # 2. Buat prompt pengecekan
                    check_prompt = f"""
                    Kamu adalah sistem filter untuk chatbot Kozy di toko retail AZKO.
                    Aku tidak menemukan promo untuk '{prompt}' di databasku.
                    Berdasarkan pengetahuan umummu, apakah '{prompt}' ini adalah promo yang PASTI hanya berlaku di tempat lain 
                    (contoh: 'voucher Indomart' hanya di Indomart, 'diskon Shopee' hanya di Shopee)?
                    
                    Jawab HANYA dengan salah satu dari dua ini:
                    1. 'YA' jika kamu sangat yakin ini EKSKLUSIF untuk tempat lain.
                    2. 'TIDAK' jika ini adalah voucher/promo umum (seperti 'voucher Ultra') atau jika kamu tidak yakin.
                    """
                    
                    ai_check_response = check_model.generate_content(check_prompt).text.strip().upper()

                    if "YA" in ai_check_response:
                        # KASUS 1: (Voucher Indomart) - AI yakin ini eksklusif.
                        
                        explain_model = genai.GenerativeModel("models/gemini-flash-latest")
                        # ✨ PROMPT TONE DISESUAIKAN UNTUK KASIR
                        explain_prompt = f"""
                        Kamu adalah Kozy, asisten internal untuk kasir AZKO. Nada bicaramu ramah tapi to-the-point.
                        User (kasir) baru saja bertanya soal '{prompt}'.
                        Jelaskan dengan singkat dan jelas bahwa voucher/promo itu EKSKLUSIF untuk toko/platform lain dan tidak bisa diterima di AZKO.
                        Contoh balasan: "Oh, untuk voucher Indomart, itu khusus untuk di Indomart aja ya. Nggak berlaku di AZKO."
                        """
                        answer = explain_model.generate_content(explain_prompt).text

                    else:
                        # KASUS 2: (Voucher Ultra / Vucher MAP) - AI tidak yakin / ini promo umum.
                        # Beri jawaban "belum terdata, tanya finrep".
                        answer = finrep_answer
                
                except Exception as e:
                    # Failsafe jika AI check gagal, kembali ke jawaban aman
                    st.error(f"AI Check Gagal: {e}") # Untuk debugging Anda
                    answer = finrep_answer
                # === BLOK MODIFIKASI SELESAI ===

            else:
                # ✅ Jika ada promo yang cocok (LOGIKA LAMA ANDA, SUDAH BAGUS)
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
                    model = genai.GenerativeModel("models/gemini-flash-latest")
                    # ✨ PROMPT TONE DISESUAIKAN UNTUK KASIR
                    instr = (
                        "Kamu adalah Kozy, asisten internal kasir AZKO. "
                        "Sampaikan hasil promo ini dengan jelas dan ringkas. Pastikan kasir mudah mengerti."
                    )
                    resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                    # 🛑 Menghapus random_comment()
                    answer = getattr(resp, "text", hasil) 
                except Exception:
                    answer = hasil # 🛑 Menghapus random_comment()
        
        except Exception as e:
            st.error(f"Error saat proses promo: {e}")
            answer = default_fallback_answer

    else: # Ini adalah intent "other"
        answer = "Hmm, maaf, aku Kozy asisten promo. Untuk pertanyaan di luar info promo, aku belum bisa bantu. Ada info promo yang mau dicari?"

    # --- OUTPUT KE CHAT ---
    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.context += f"User: {prompt}\nKozy: {answer}\n"
    st.session_state.last_intent = intent
