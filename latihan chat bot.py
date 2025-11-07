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

@st.cache_data(ttl=3600)
def detect_intent_ai(text: str) -> str:
    text = text.lower().strip()
    
    simple_greetings = re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", text)
    simple_thanks = re.search(r"\b(terima kasih|makasih|thanks|tq)\b", text)
    simple_goodbye = re.search(r"\b(dah|bye|sampai jumpa|exit)\b", text)
    
    if simple_greetings: return "greeting"
    if simple_thanks: return "thanks"
    if simple_goodbye: return "goodbye"

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
        
        if "promo" in response: return "promo"
        if "smalltalk" in response: return "smallaltk"
        if "other" in response: return "other"
        
        return "promo"
    except Exception:
        return "promo"

# ✨ FUNGSI UNTUK CEK "VOUCHER"
@st.cache_data(ttl=3600)
def is_voucher_query(text: str) -> bool:
    text = text.lower().strip()
    if re.search(r"\b(v(ou|u)c(h)?er|vocer)\b", text):
        return True
    
    try:
        model = genai.GenerativeModel("models/gemini-flash-latest")
        prompt = f"""
        User (seorang kasir) bertanya: "{text}"
        Apakah pertanyaan ini spesifik tentang "Voucher"? 
        Jawab HANYA dengan 'YA' atau 'TIDAK'.
        
        Contoh:
        - User: "voucer ultra bisa?" -> YA
        - User: "promo bca" -> TIDAK
        """
        response = model.generate_content(prompt).text.strip().upper()
        return "YA" in response
    except Exception:
        return bool(re.search(r"\b(v(ou|u)c(h)?er|vocer)\b", text))

# ✨ FUNGSI UNTUK STEP 2 (DIPERBARUI)
@st.cache_data(ttl=3600)
def get_voucher_clarity(text: str) -> str:
    try:
        model = genai.GenerativeModel("models/gemini-flash-latest")
        # --- PERUBAHAN DI SINI ---
        # "Voucher Telkomsel" ditambahkan sebagai contoh TIDAK_BERLAKU
        prompt = f"""
        Kamu adalah sistem filter. User (kasir) bertanya soal '{text}', yang mana datanya tidak ada di database.
        Berdasarkan pengetahuan umum, apakah '{text}' ini adalah voucher yang PASTI EKSKLUSIF dan HANYA BERLAKU di toko lain (Contoh: 'Voucher Indomart', 'Voucher Alfamart', 'Voucher Telkomsel')?
        
        Jawab HANYA dengan salah satu dari dua label ini:
        1. "TIDAK_BERLAKU" (jika kamu 100% yakin ini eksklusif toko lain)
        2. "TIDAK_DIKETAHUI" (untuk SEMUA voucher lainnya, seperti 'Voucher Ultra', 'Voucher MAP', atau jika kamu tidak yakin)
        
        Label:
        """
        response = model.generate_content(prompt).text.strip().upper()
        
        if "TIDAK_BERLAKU" in response:
            return "TIDAK_BERLAKU"
        else:
            return "TIDAK_DIKETAHUI" # Default aman
            
    except Exception:
        return "TIDAK_DIKETAHUI" # Failsafe

def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    model = genai.GenerativeModel("models/gemini-flash-latest")
    prompt = f"Tentukan 3 kata kunci utama dari pertanyaan berikut untuk mencari promo: '{query}'. Balas hanya kata kunci dipisahkan koma."
    try:
        keywords = model.generate_content(prompt).text.lower().split(",")
        keywords = [k.strip() for k in keywords if k.strip()]
    except Exception:
        keywords = [query.lower()]

    mask = pd.Series([False] * len(df))
    for kw in keywords:
        for c in df.columns:
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

    intent = detect_intent_ai(prompt)
    topic_changed = (intent != st.session_state.last_intent)
    
    if topic_changed:
        st.session_state.context = ""
    
    answer = ""
    default_fallback_answer = "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."

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
                # === INI LOGIKA 3 LANGKAH ANDA ===
                
                is_voucher = is_voucher_query(prompt)
                
                if is_voucher:
                    # --- LOGIKA 3 LANGKAH (VOUCHER) ---
                    
                    # 1. Narasi Cek Database
                    narasi_1 = f"Hmm, aku cek di databasku, info untuk **'{prompt}'** memang belum ter-update nih."
                    
                    # 2. Narasi Tanya Gemini (Clarity)
                    clarity = get_voucher_clarity(prompt)
                    
                    narasi_2 = "" 
                    if clarity == "TIDAK_BERLAKU":
                        narasi_2 = "Setelah aku cek silang, voucher itu sepertinya memang **khusus untuk di merchant lain** ya (tidak berlaku di AZKO)."
                    elif clarity == "TIDAK_DIKETAHUI":
                        narasi_2 = "Aku coba cek silang ke sistem AI, tapi infonya juga **belum ada** di sana."
                    
                    # 3. Narasi Template Respon (Finrep)
                    narasi_3 = "Untuk kepastian 100%, boleh tolong **cek info terbaru dari Partnership/PNA** atau langsung **kontak Finrep Area kamu** ya. Biar aman. 👍"
                    
                    answer = f"{narasi_1}\n\n{narasi_2}\n\n{narasi_3}"
                    
                else:
                    # --- LOGIKA 2 LANGKAH (BUKAN VOUCHER) ---
                    
                    narasi_1 = f"Hmm, aku cek di sistem, data untuk promo **'{prompt}'** sepertinya **belum ter-update** nih."
                    narasi_3 = "Info lebih pastinya, coba **kontak Finrep Area kamu** ya, biar aman. 👍"
                    answer = f"{narasi_1}\n\n{narasi_3}"
                
            else:
                # ✅ Jika ada promo yang cocok
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
                    instr = (
                        "Kamu adalah Kozy, asisten internal kasir AZKO. "
                        "Sampaikan hasil promo ini dengan jelas dan ringkas. Pastikan kasir mudah mengerti."
                    )
                    resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                    answer = getattr(resp, "text", hasil)
                except Exception:
                    answer = hasil
        
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
