import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# =S========================================================
# === FUNGSI LOGIN (TIDAK BERUBAH) ===
# ==========================================================
def login_form():
    """
    Menampilkan form login dan mengautentikasi pengguna.
    Menggunakan st.secrets untuk kredensial yang aman.
    """
    
    # Inisialisasi session state untuk status login
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    # Jika pengguna sudah login, langsung jalankan aplikasi utama
    if st.session_state.authenticated:
        run_chatbot_app()
    
    # Jika pengguna belum login, tampilkan form
    else:
        st.set_page_config(page_title="Login - Kozy", page_icon="🔒", layout="centered")
        st.title("🔒 Silakan Login")
        st.write("Masukkan kredensial untuk mengakses Kozy Asisten Kasir.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Username Anda")
            password = st.text_input("Password", type="password", placeholder="Password Anda")
            submitted = st.form_submit_button("Login")

            if submitted:
                # Cek kredensial dari Streamlit Secrets
                try:
                    correct_user = st.secrets["app_credentials"]["APP_USER"]
                    correct_pass = st.secrets["app_credentials"]["APP_PASS"]
                except KeyError:
                    st.error("Kredensial aplikasi belum di-setting di secrets.toml")
                    return
                except Exception as e:
                    st.error(f"Error saat membaca secrets: {e}")
                    return

                # Verifikasi login
                if username == correct_user and password == correct_pass:
                    st.session_state.authenticated = True
                    st.success("Login berhasil! Memuat aplikasi...")
                    st.rerun() # Muat ulang halaman (penting!)
                else:
                    st.error("Username atau Password salah.")

# ==========================================================
# === "OTAK AI" BARU (RAG) ===
# ==========================================================
@st.cache_data(ttl=300) # Cache data GSheet selama 5 menit
def get_database_df(_gc, sheet_key): # <-- PERBAIKAN ERROR CACHE
    """Mengambil dan men-cache DataFrame dari Google Sheets."""
    try:
        sheet = _gc.open_by_key(sheet_key).worksheet("promo") # <-- PERBAIKAN ERROR CACHE
        df = pd.DataFrame(sheet.get_all_records())
        # Pastikan kolom penting adalah string
        for col in ['NAMA_PROMO', 'BANK_PARTNER', 'DETAIL_DISKON', 'SYARAT_UTAMA']:
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
        st.stop()

def get_ai_response(prompt: str, df_database: pd.DataFrame):
    """
    Fungsi "Otak AI" utama.
    AI akan menganalisis prompt dan database, lalu menghasilkan jawaban.
    """
    
    # Ubah DataFrame menjadi string Markdown agar ringkas & mudah dibaca AI
    kolom_relevan = ['NAMA_PROMO', 'PROMO_STATUS', 'PERIODE', 'SYARAT_UTAMA', 'DETAIL_DISKON', 'BANK_PARTNER']
    kolom_valid = [kol for kol in kolom_relevan if kol in df_database.columns]
    
    if not kolom_valid:
        st.error("Database tidak memiliki kolom yang diharapkan (NAMA_PROMO, BANK_PARTNER, dll.)")
        return "Maaf, database promo sepertinya sedang kosong."
        
    db_string = df_database[kolom_valid].to_markdown(index=False)
    
    # Ambil riwayat chat terakhir untuk konteks
    history = "\n".join([
        f"{'User' if msg['role'] == 'user' else 'Kozy'}: {msg['content']}" 
        for msg in st.session_state.messages[-4:] # Ambil 4 chat terakhir
    ])

    model = genai.GenerativeModel("models/gemini-flash-latest")
    
    # ==========================================================
    # === MASTER PROMPT V5 (OTAK PINTAR, RESPON AMAN) ===
    # ==========================================================
    gemini_prompt = f"""
    Kamu adalah Kozy, asisten kasir internal AZKO. Nada bicaramu ramah, percaya diri, dan to-the-point (seperti teman kerja, BUKAN customer).

    TUGAS UTAMA:
    Jawab pertanyaan User ({prompt}) berdasarkan **KONTEKS DATABASE PROMO** di bawah. JANGAN berhalusinasi atau menambah info di luar database.

    ---
    KONTEKS DATABASE PROMO (format Markdown):
    {db_string}
    ---
    RIWAYAT CHAT SEBELUMNYA (untuk konteks percakapan):
    {history}
    ---

    ATURAN CARA MENJAWAB (WAJIB IKUTI!):

    1.  **JIKA HANYA SAPAAN/SMALLTALK** (misal: "pagi kozy", "apa kabar", "kamu siapa"):
        * JANGAN cari di database.
        * Balas sapaan itu dengan ramah sebagai rekan kerja.
        * Contoh Balasan: "Pagi juga! Semangat ya. Ada info promo yang dicari?" atau "Aku Kozy, asisten promo kamu. Siap bantu!"

    2.  **JIKA DATA DITEMUKAN DI DATABASE** (misal: "cicilan bca", "potong poin", "tenor berapa lama"):
        * AI HARUS CERDAS: Pahami bahwa "tenor" ada di kolom `DETAIL_DISKON`. Pahami "potong poin" ada di `NAMA_PROMO`.
        * Cari baris yang paling relevan di database, lalu rangkum infonya.
        * Mulai dengan sapaan (Contoh: "Oke, nemu nih! Untuk cicilan BCA...").
        * Contoh Pertanyaan "cicilan tenor berapa lama?": AI harus melihat `DETAIL_DISKON` dan merangkum "Tersedia tenor 3bln, 6bln, dan 12bln."

    3.  **JIKA DATA TIDAK DITEMUKAN DI DATABASE** (misal: "voucher MAP", "cicilan bank danamon", "promo paylater"):
        * **PENTING!** Kamu harus meniru format 3-langkah yang kaku dan aman ini untuk melindungi kasir dari kesalahan.
        * **JANGAN** memberi jawaban singkat (seperti "voucher MAP belum bisa").
        * **WAJIB IKUTI FORMAT INI:**
        
            "Oke, aku bantu cek ya untuk **{prompt}**:

            1.  Aku sudah cek di database Kozy, tapi **ketentuan untuk '{prompt}' di AZKO belum terdaftar** nih.

            2.  Setelah aku klarifikasi lebih lanjut, [TULIS HASIL KLARIFIKASI PENGETAHUAN UMUM AI DI SINI. Contoh: 'Voucher MAP (Mitra Adiperkasa) adalah voucher hadiah spesifik (closed-loop) yang umumnya hanya dapat ditukarkan di jaringan toko di bawah naungan Grup Mitra Adiperkasa (seperti Sogo, Zara, dll).']

            3.  Untuk kepastian lebih lanjut, silakan **cek email dari Partnership/PNA** atau **bertanya ke Finrep Area kamu** ya. Selalu pastikan info promo sebelum transaksi. 👍"
        
    ---
    PERTANYAAN USER SAAT INI: "{prompt}"

    Jawaban Kozy:
    """
    # ==========================================================
    # === AKHIR MASTER PROMPT ===
    # ==========================================================

    try:
        response = model.generate_content(gemini_prompt)
        return response.text.strip()
    except Exception as e:
        # Menangani error jika ada safety setting atau API error
        st.error(f"Error dari API Gemini: {e}")
        return "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."

# ==========================================================
# === APLIKASI CHATBOT UTAMA (DIREKONSTRUKSI) ===
# ==========================================================
def run_chatbot_app():
    """
    Ini adalah kode aplikasi chatbot Anda yang sudah direkonstruksi.
    """

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

    # --- AMBIL DATA DARI G-SHEET (MENGGUNAKAN CACHE) ---
    df_original = get_database_df(gc, SHEET_KEY)

    # --- KONFIGURASI HALAMAN ---
    st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

    # ==========================================================
    # === CSS KUSTOM (TIDAK BERUBAH) ===
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

    # --- HEADER APLIKASI (TIDAK BERUBAH) ---
    st.markdown(
        f"""
        <div style='text-align: center; margin-bottom: 0.5rem;'>
            <img src="https://raw.githubusercontent.com/fajarachmad15/Azko-Promo-Bot/main/azko-logo-white-on-red.png" alt="AZKO Logo" style="width: 50px; margin-bottom: 0.5rem;">
            <h1 style='margin-bottom: 0.2rem; font-size: 2.2rem;'>Kozy – Asisten Kasir AZKO</h1>
            <p style='color: gray; font-size: 1.0rem;'>supported by <b>Gemini AI</b></p>
            <p style='color: #d9534f; font-size: 1.0rem;'>⚠️ Kozy dapat membuat kesalahan. Selalu konfirmasi info penting.</p>
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
    # Hapus state lama yang tidak perlu
    if "context" in st.session_state:
        del st.session_state["context"]
    if "last_intent" in st.session_state:
        del st.session_state["last_intent"]


    # --- UI CHAT ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- INPUT CHAT (LOGIKA BARU YANG JAUH LEBIH SIMPEL) ---
    if prompt := st.chat_input("Ketik info promo yang dicari..."):
        # 1. Tampilkan pertanyaan user
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 2. Panggil "Otak AI"
        try:
            with st.spinner("Kozy lagi mikir..."):
                # Ini adalah satu-satunya panggilan logika
                answer = get_ai_response(prompt, df_original) 
        
        except Exception as e:
            st.error(f"Duh, ada error: {e}")
            answer = "Maaf, lagi ada gangguan. Coba lagi ya."

        # 3. Tampilkan jawaban AI
        with st.chat_message("assistant"):
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})


# ==========================================================
# === TITIK MASUK APLIKASI (TIDAK BERUBAH) ===
# ==========================================================

# Panggil fungsi login_form() sebagai hal pertama.
# Fungsi ini akan memutuskan apakah akan menampilkan form login
# atau menjalankan run_chatbot_app().
login_form()