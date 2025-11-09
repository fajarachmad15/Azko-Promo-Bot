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
    # Salin df untuk mencegah error cache
    df_original = pd.DataFrame(sheet.get_all_records())
except Exception as e:
    st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
    st.stop()

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

# ==========================================================
# === CSS KUSTOM (UNIK AZKO) ===
# ==========================================================
st.markdown(
    """
    <style>
    /* 1. Mengatur lebar container utama */
    .css-1d391kg {
        max-width: 700px; /* Lebar lebih nyaman untuk chat */
        padding-left: 1rem;
        padding-right: 1rem;
    }
    /* 2. Mengubah warna Primary Streamlit (Warna Merah AZKO: #BF1E2D) */
    :root {
        --primary-color: #BF1E2D; 
    }
    /* 3. Mengubah Header dan Font */
    h1, h2, h3, h4, .stApp {
        font-family: 'Poppins', sans-serif; /* Ganti font agar lebih modern */
    }
    /* 4. Mengubah warna ikon dan tombol KIRIM menjadi Merah AZKO */
    .stButton > button, .stTextInput > div > div > button {
        background-color: var(--primary-color) !important;
        color: white !important;
        border: none;
    }
    /* 5. Mengubah warna notifikasi Peringatan (Warning) menjadi Kuning/Oranye */
    .stAlert.stWarning {
        background-color: #FFA50040; /* Oranye muda transparan */
        border-left: 5px solid #FFC300; /* Oranye gelap */
        color: #FFC300;
    }
    .stAlert.stWarning p {
        color: white; /* Agar teks di mode gelap tetap terbaca */
    }
    /* 6. Mempercantik Chat Input */
    .stTextInput {
        border-radius: 0.75rem;
    }
    .stTextInput > div > div > input {
        border-radius: 0.75rem;
        border: 1px solid #BF1E2D; /* Border merah di input */
    }
    /* 7. Memperjelas pemisah/garis */
    hr {
        border-top: 1px solid #BF1E2D40; /* Merah transparan */
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- HEADER APLIKASI (DISESUAIKAN DENGAN LOGO) ---
st.markdown(
    f"""
    <div style='text-align: center; margin-bottom: 0.5rem;'>
        <img src="https://raw.githubusercontent.com/fajarachmad15/Azko-Promo-Bot/main/azko-logo-white-on-red.png" alt="AZKO Logo" style="width: 50px; margin-bottom: 0.5rem;">
        <h1 style='margin-bottom: 0.2rem; font-size: 2.2rem;'>Kozy – Asisten Kasir AZKO</h1>
        <p style='color: gray; font-size: 0.8rem;'>supported by <b>Gemini AI</b></p>
        <p style='color: #d9534f; font-size: 0.8rem;'>⚠️ Kozy dapat membuat kesalahan. Selalu konfirmasi info penting.</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("---") # Garis pemisah visual
# ==========================================================
# === AKHIR CSS DAN HEADER ===
# ==========================================================


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

# ==========================================================
# === FUNGSI BARU: AI PEMBERSIH TYPO ===
# ==========================================================
@st.cache_data(ttl=3600) # Cache hasil pembersihan
def clean_prompt_with_ai(text: str) -> str:
    """Menggunakan AI untuk memperbaiki typo sebelum diproses."""
    try:
        model = genai.GenerativeModel("models/gemini-flash-latest")
        prompt_template = f"""
        Kamu adalah ahli ejaan Bahasa Indonesia, perbaiki typo di teks ini.
        Balas HANYA dengan teks yang sudah diperbaiki.
        Contoh:
        User: vocer map
        Kamu: voucher map
        User: cicilan tnpa krtu krdt
        Kamu: cicilan tanpa kartu kredit
        User: bca kartu debitnya ngga bisa tuker point ya?
        Kamu: bca kartu debitnya ngga bisa tukar poin ya?
        
        Teks: "{text}"
        Perbaikan:
        """
        response = model.generate_content(prompt_template)
        cleaned_text = response.text.strip()
        if not cleaned_text: # Failsafe jika AI balikin kosong
            return text
        return cleaned_text
    except Exception as e:
        st.warning(f"AI Typo Cleaner Gagal: {e}. Menggunakan teks asli.")
        return text # Jika AI gagal, gunakan teks asli
# ==========================================================
# === AKHIR FUNGSI BARU ===
# ==========================================================


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
        Pilih HANYA SATU dari kategori ini: [promo_search, smalltalk, other]
        
        - "promo_search": User MENCARI info promo spesifik. (Contoh: "ada promo apa", "cicilan BCA", "voucher MAP", "diskon BSI").
        - "smalltalk": Basa-basi ATAU pertanyaan TENTANG kamu (si bot). (Contoh: "apa kabar", "kamu siapa", "bener kamu bisa jawab?", "lagi apa").
        - "other": Pertanyaan di luar topik.
        
        User: "{text}"
        Intent:
        """
        response = model.generate_content(prompt).text.strip().lower()
        
        if "promo_search" in response: return "promo"
        if "smalltalk" in response: return "smalltalk"
        if "other" in response: return "other"
        
        if "promo" in text: return "promo"
        return "smalltalk"
    except Exception:
        if "promo" in text: return "promo"
        return "smalltalk"

def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    df_scored = df.copy()
    
    STOP_WORDS = set([
        "ada", "apa", "aja", "bisa", "buat", "biar", "cara", "cek", "coba",
        "dari", "dengan", "dong", "di", "gak", "gimana", "kalau", "ka",
        "ke", "kok", "kita", "lagi", "mau", "nih", "ngga", "pakai",
        "saja", "saya", "sekarang", "tolong", "untuk", "ya", "yg", "transaksi",
        "digunakan", "dipakai", "berarti"
    ])
    
    words = re.findall(r'\b\w{3,}\b', query.lower())
    keywords = [word for word in words if word not in STOP_WORDS]

    if not keywords:
        keywords = [word for word in words if word in ["voucher", "promo", "diskon", "cashback", "cicilan"]]
        if not keywords:
            keywords = words

    if not keywords:
        return pd.DataFrame(columns=df.columns) 

    df_scored['match_score'] = 0

    for kw in keywords:
        kw_mask = pd.Series([False] * len(df_scored))
        for c in df_scored.columns:
            if pd.api.types.is_string_dtype(df_scored[c]):
                kw_mask |= df_scored[c].str.lower().str.contains(kw, na=False)
            else:
                kw_mask |= df_scored[c].astype(str).str.lower().str.contains(kw, na=False)
        
        df_scored.loc[kw_mask, 'match_score'] += 1
    
    max_score = df_scored['match_score'].max()
    
    if max_score == 0:
        return pd.DataFrame(columns=df.columns)
        
    # ATURAN KETAT: Jika skor tidak sempurna, anggap tidak relevan.
    if max_score < len(keywords):
        return pd.DataFrame(columns=df.columns)
        
    return df_scored[df_scored['match_score'] == max_score].drop(columns=['match_score'])


# --- UI CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT ---
if prompt := st.chat_input("Ketik info promo yang dicari..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # ==========================================================
    # === PERUBAHAN: LANGKAH 0 - PEMBERSIHAN TYPO ===
    # ==========================================================
    # Simpan prompt asli untuk ditampilkan
    original_prompt = prompt 
    
    # Lakukan pembersihan typo
    with st.spinner("Memproses..."):
        cleaned_prompt = clean_prompt_with_ai(original_prompt)
    # ==========================================================

    # Gunakan 'cleaned_prompt' untuk semua logika internal
    intent = detect_intent_ai(cleaned_prompt)
    topic_changed = (intent != st.session_state.last_intent)
    
    if topic_changed:
        st.session_state.context = ""
    
    answer = ""
    
    # --- JAWABAN TEMPLATE ---
    default_fallback_answer = "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."
    finrep_template_answer = (
        "Untuk kepastian lebih lanjut, silakan **cek email dari Partnership/PNA** "
        "atau **bertanya ke Finrep Area kamu** ya. Selalu pastikan info promo sebelum transaksi. 👍"
    )
    # --- AKHIR TEMPLATE ---

    if intent == "greeting":
        greet = "Halo 👋"
        if "pagi" in prompt: greet = "Selamat pagi 🌞"
        elif "siang" in prompt: greet = "Selamat siang ☀️"
        elif "sore" in prompt: greet = "Selamat sore 🌇"
        elif "malam" in prompt: greet = "Selamat malam 🌙"
        answer = f"{greet}! Aku Kozy, asisten promo internal AZKO. Ada yang bisa dibantu?"

    elif intent == "smalltalk":
        try:
            with st.spinner("..."):
                model = genai.GenerativeModel("models/gemini-flash-latest")
                # Gunakan cleaned_prompt untuk smalltalk
                prompt_smalltalk = f"""
                Kamu adalah Kozy, asisten kasir AZKO. Nada bicaramu ramah, percaya diri, dan to-the-point (seperti teman kerja).
                User baru saja bilang: "{cleaned_prompt}"
                Beri respon smalltalk yang sesuai. JANGAN mencari promo.
                """
                answer = model.generate_content(prompt_smalltalk).text.strip()
        except Exception:
            answer = "Aku Kozy, asisten AI kamu. Siap bantu cari info promo. Ada yang ditanyakan soal promo?"

    elif intent == "thanks":
        answer = "Sama-sama! 👍 Lanjut cari info lain?"

    elif intent == "goodbye":
        answer = "Oke, sampai nanti ya! Selamat bekerja. 🛍️"

    elif intent == "promo":
        try:
            # Gunakan cleaned_prompt untuk mencari
            matches = find_smart_matches(df_original, cleaned_prompt)

            if matches.empty:
                # --- BLOK 'TIDAK DITEMUKAN' (LOGIKA 1&3) ---
                
                # Gunakan cleaned_prompt untuk narasi
                step_1_db = f"Aku sudah cek di database Kozy, tapi **ketentuan untuk '{cleaned_prompt}' belum terdaftar** nih."
                step_3_finrep = finrep_template_answer
                
                answer = (
                    f"Oke, aku bantu cek ya:\n\n"
                    f"1. {step_1_db}\n\n"
                    f"2. {step_3_finrep}"
                )

            else:
                # --- BLOK JIKA DATA DITEMUKAN (AI Perangkum) ---
                promos = []
                for _, r in matches.iterrows():
                    promos.append(
                        f"• **{r.get('NAMA_PROMO','')}** ({r.get('PROMO_STATUS','')})\n"
                        f"📅 Periode: {r.get('PERIO','')}\n" # Typo di kode lama? Seharusnya PERIODE
                        f"📝 {r.get('SYARAT_UTAMA','')}\n"
                        f"💰 {r.get('DETAIL_DISKON','')}\n"
                        f"🏦 Bank: {r.get('BANK_PARTNER','')}"
                    )
                hasil = "\n\n".join(promos)
                
                try:
                    with st.spinner("Merangkum info..."):
                        model = genai.GenerativeModel("models/gemini-flash-latest")
                        # Gunakan cleaned_prompt untuk konteks
                        instr = (
                            "Kamu adalah Kozy, asisten internal kasir AZKO. Nada bicaramu ramah, percaya diri, dan to-the-point.\n"
                            f"User baru saja bertanya (setelah perbaikan typo): '{cleaned_prompt}'\n"
                            "Aku sudah menemukan data promo berikut dari database:\n\n"
                            f"{hasil}\n\n"
                            "Tugasmu: Berikan jawaban yang merangkum data ini. JANGAN berhalusinasi atau menambah info di luar data. Mulai dengan sapaan ramah.\n"
                        )
                        resp = model.generate_content(instr)
                        answer = getattr(resp, "text", hasil) 
                except Exception as e:
                    st.error(f"AI summarizer Gagal: {e}")
                    answer = "Oke, aku nemu info ini di database:\n\n" + hasil
        
        except Exception as e:
            st.error(f"Error saat proses promo: {e}")
            answer = default_fallback_answer

    else: # Ini adalah intent "other"
        answer = "Hmm, maaf, aku Kozy asisten promo. Untuk pertanyaan di luar info promo, aku belum bisa bantu. Ada info promo yang mau dicari?"

    # --- OUTPUT KE CHAT ---
    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.context += f"User: {prompt}\nKozy: {answer}\n" # Simpan prompt asli di konteks
    st.session_state.last_intent = intent
