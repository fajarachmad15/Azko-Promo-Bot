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

@st.cache_data(ttl=3600)
def detect_intent_ai(text: str) -> str:
    text = text.lower().strip()
    
    simple_greetings = re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam)|morning|afternoon|evening)\b", text)
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
        
        - "promo_search": User MENCARI info promo spesifik. (Contoh: "ada promo apa", "cicilan BCA", "voucher MAP", "diskon BSI", "tukar poin", "redeem point", "installment").
        - "smalltalk": Basa-basi ATAU pertanyaan TENTANG kamu (si bot). (Contoh: "apa kabar", "kamu siapa", "bener kamu bisa jawab?", "lagi apa", "morning").
        - "other": Pertanyaan di luar topik.
        
        User: "{text}"
        Intent:
        """
        response = model.generate_content(prompt).text.strip().lower()
        
        if "promo_search" in response: return "promo"
        if "smalltalk" in response: return "smalltalk"
        if "other" in response: return "other"
        
        # Fallback jika AI bingung
        if "promo" in text or "diskon" in text or "voucher" in text or "poin" in text or "redeem" in text or "installment" in text:
            return "promo"
        return "smalltalk" 
    except Exception:
        # Fallback jika AI error
        if "promo" in text or "diskon" in text or "voucher" in text or "poin" in text or "redeem" in text or "installment" in text:
            return "promo"
        return "smalltalk"

# ==========================================================
# === FUNGSI PENCARIAN STABIL (Skor Relevan) ===
# ==========================================================
def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    df_scored = df.copy()
    
    # === PERBAIKAN 1: Menambahkan kata-kata umum ke STOP_WORDS ===
    STOP_WORDS = set([
        "ada", "apa", "aja", "bisa", "buat", "biar", "cara", "cek", "coba",
        "dari", "dengan", "dong", "di", "gak", "gimana", "kalau", "ka",
        "ke", "kok", "kita", "lagi", "mau", "nih", "ngga", "pakai",
        "saja", "saya", "sekarang", "tolong", "untuk", "ya", "yg", "transaksi",
        "digunakan", "dipakai", "berarti",
        "bank", "pake", "point", "program" # <- TAMBAHAN BARU
    ])
    
    # 1. Ambil semua kata dari query (minimal 3 huruf)
    words = re.findall(r'\b\w{3,}\b', query.lower())
    
    # 2. Saring kata-kata, buang stop words
    keywords = [word for word in words if word not in STOP_WORDS]

    if not keywords:
        # Fallback jika semua kata adalah stop words
        keywords = [word for word in words if word in ["voucher", "promo", "diskon", "cashback", "cicilan", "poin", "redeem", "installment"]]
        if not keywords:
            keywords = words # Gunakan kata asli jika fallback gagal

    if not keywords:
        return pd.DataFrame(columns=df.columns) # Return empty

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
        
    # ATURAN KETAT (DIPERTAHANKAN):
    # Skor tertinggi (max_score) HARUS SAMA DENGAN jumlah kata kunci.
    # Ini penting untuk memblokir "cicilan TANPA kartu kredit"
    if max_score < len(keywords):
        return pd.DataFrame(columns=df.columns) # Kembalikan nol jika tidak semua keyword cocok
        
    # Kembalikan baris dengan skor tertinggi (yang skornya = len(keywords))
    return df_scored[df_scored['match_score'] == max_score].drop(columns=['match_score'])
# ==========================================================
# === AKHIR FUNGSI PENCARIAN ===
# ==========================================================

# ==========================================================
# === FUNGSI BARU: Normalisasi Kueri ===
# ==========================================================
def normalize_query(query: str) -> str:
    """
    Menerjemahkan sinonim (Inggris/Singkatan) ke istilah
    yang ada di database (Indonesia).
    """
    q = query.lower()
    
    # Urutan penting: ganti yang spesifik dulu
    q = q.replace("redeem point", "tukar poin")
    q = q.replace("reward point", "tukar poin")
    
    # Ganti yang umum
    q = q.replace("installment", "cicilan")
    q = q.replace("redeem", "tukar")
    q = q.replace("point", "poin")
    
    return q
# ==========================================================

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
    
    # --- JAWABAN TEMPLATE ---
    default_fallback_answer = "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."
    finrep_template_answer = (
        "Untuk kepastian lebih lanjut, silakan **cek email dari Partnership/PNA** "
        "atau **bertanya ke Finrep Area kamu** ya. Selalu pastikan info promo sebelum transaksi. 👍"
    )
    # --- AKHIR TEMPLATE ---

    if intent == "greeting":
        greet = "Halo 👋"
        prompt_lower = prompt.lower()
        if "pagi" in prompt_lower or "morning" in prompt_lower: greet = "Selamat pagi 🌞"
        elif "siang" in prompt_lower or "afternoon" in prompt_lower: greet = "Selamat siang ☀️"
        elif "sore" in prompt_lower or "evening" in prompt_lower: greet = "Selamat sore 🌇"
        elif "malam" in prompt_lower: greet = "Selamat malam 🌙"
        answer = f"{greet}! Aku Kozy, asisten promo internal AZKO. Ada yang bisa dibantu?"

    elif intent == "smalltalk":
        try:
            with st.spinner("..."):
                model = genai.GenerativeModel("models/gemini-flash-latest")
                prompt_smalltalk = f"""
                Kamu adalah Kozy, asisten kasir AZKO. Nada bicaramu ramah, percaya diri, dan to-the-point (seperti teman kerja).
                User baru saja bilang: "{prompt}"
                Beri respon smalltalk yang sesuai. JANGAN mencari promo.
                
                Contoh 1:
                User: bener kamu bisa jawab seputar promo?
                Kamu: Bener dong, coba aja siapa takut! 😉 Ada promo apa yang kamu cari?
                
                Contoh 2:
                User: kamu siapa?
                Kamu: Aku Kozy, asisten promo kamu. Siap bantu!
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
            # === PERBAIKAN 2: Gunakan fungsi normalisasi ===
            normalized_prompt = normalize_query(prompt)
            
            # Mencari menggunakan kueri yang sudah dinormalisasi
            matches = find_smart_matches(df_original, normalized_prompt)

            if matches.empty:
                # ==========================================================
                # === BLOK JIKA DATA TIDAK DITEMUKAN (LOGIKA 3-LANGKAH) ===
                # ==========================================================
                
                try:
                    # LANGKAH 1: Info dari Database (Selalu 'tidak ada')
                    # Tampilkan prompt asli dari user, bukan yang sudah dinormalisasi
                    step_1_db = f"Aku sudah cek di database Kozy, tapi **ketentuan untuk '{prompt}' di AZKO belum terdaftar** nih."
                    
                    # LANGKAH 2: Klarifikasi dari Gemini (Pengetahuan Umum)
                    step_2_gemini = ""
                    with st.spinner(f"Mencari info publik soal '{prompt}'..."):
                        gemini_model = genai.GenerativeModel("models/gemini-flash-latest")
                        
                        gemini_prompt = f"""
                        Anda adalah asisten AI. Kasir bertanya tentang '{prompt}' yang tidak ada di database internal.
                        Berdasarkan pengetahuan publik Anda, berikan klarifikasi singkat dan netral tentang '{prompt}' tersebut. 
                        
                        Fokus pada:
                        - Jika itu voucher: Apakah itu voucher umum atau spesifik untuk grup tertentu?
                        - Jika itu metode pembayaran (cth: cicilan tanpa CC, installment): Apakah itu layanan yang umum ada (seperti PayLater atau cicilan kartu kredit)?
                        
                        Mulai jawaban Anda dengan "Setelah aku klarifikasi lebih lanjut...".
                        
                        Contoh jika user bertanya 'voucher MAP':
                        "Setelah aku klarifikasi lebih lanjut, voucher MAP itu setahuku untuk toko-toko di bawah grup Mitra Adiperkasa (seperti Sogo, Zara, dll), dan AZKO sepertinya belum termasuk."
                        
                        Contoh jika user bertanya 'Cicilan tanpa kartu kredit bisa ngga?':
                        "Setelah aku klarifikasi lebih lanjut, 'cicilan tanpa kartu kredit' itu biasanya merujuk ke layanan 'PayLater' (seperti Kredivo, Akulaku, dll.). Setahuku, ketersediaan layanan itu tergantung kerjasama langsung antara AZKO dengan penyedia layanan tersebut."
                        
                        Contoh jika user bertanya 'installment bisa pakai bank apa saja?':
                        "Setelah aku klarifikasi lebih lanjut, pertanyaan mengenai 'installment' itu biasanya merujuk pada metode pembayaran cicilan kartu kredit (credit card installment). Ini adalah layanan umum yang disediakan oleh bank penerbit kartu kredit."
                        """
                        gemini_response = gemini_model.generate_content(gemini_prompt)
                        step_2_gemini = gemini_response.text.strip()

                    # LANGKAH 3: Template Finrep (Selalu disertakan)
                    answer = (
                        f"Oke, aku bantu cek ya untuk **{prompt}**:\n\n"
                        f"1. {step_1_db}\n\n"
                        f"2. {step_2_gemini}\n\n"
                        f"3. {finrep_template_answer}"
                    )

                except Exception as e:
                    # Fallback jika Langkah 2 (Gemini) gagal
                    st.error(f"AI Gemini check (langkah 2) gagal: {e}")
                    answer = (
                        f"Oke, aku bantu cek ya untuk **{prompt}**:\n\n"
                        f"1. Aku sudah cek di database Kozy, tapi **ketentuan untuk '{prompt}' di AZKO belum terdaftar**.\n\n"
                        f"2. {finrep_template_answer}" # Langsung ke langkah 3
                    )
                # ==========================================================
                # === AKHIR BLOK DATA TIDAK DITEMUKAN ===
                # ==========================================================
                
            else:
                # --- BLOK JIKA DATA DITEMUKAN (AI Perangkum) ---
                # Hanya akan masuk ke sini jika SEMUA kata kunci cocok
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
                    with st.spinner("Merangkum info..."):
                        model = genai.GenerativeModel("models/gemini-flash-latest")
                        instr = (
                            "Kamu adalah Kozy, asisten internal kasir AZKO. Nada bicaramu ramah, percaya diri, dan to-the-point.\n"
                            f"User baru saja bertanya: '{prompt}'\n"
                            "Aku sudah menemukan data promo berikut dari database:\n\n"
                            f"{hasil}\n\n"
                            "Tugasmu: Berikan jawaban yang merangkum data ini. JANGAN berhalusinasi atau menambah info di luar data. Mulai dengan sapaan ramah.\n"
                            "Contoh 1: 'Oke, nemu nih! Untuk cicilan, kita ada...'\n"
                            "Contoh 2: 'Siap. Ini dia info untuk voucher yang kamu cari...'"
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
    st.session_state.context += f"User: {prompt}\nKozy: {answer}\n"
    st.session_state.last_intent = intent
