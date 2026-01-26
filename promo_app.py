import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# ==========================================================
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
# === "OTAK AI" (DIPERBAIKI: PAKAI FILTERING) ===
# ==========================================================
@st.cache_data(ttl=300) 
def get_database_df(_gc, sheet_key): 
    """Mengambil dan men-cache DataFrame dari Google Sheets."""
    try:
        sheet = _gc.open_by_key(sheet_key).worksheet("promo") 
        df = pd.DataFrame(sheet.get_all_records())
        # Pastikan kolom penting adalah string dan LOWERCASE untuk memudahkan pencarian
        for col in ['NAMA_PROMO', 'BANK_PARTNER', 'DETAIL_DISKON', 'SYARAT_UTAMA']:
            if col in df.columns:
                df[col] = df[col].astype(str)
        return df
    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
        st.stop()

def get_ai_response(prompt: str, df_database: pd.DataFrame):
    """
    Fungsi "Otak AI" UTAMA (YANG DIPERBAIKI).
    Sekarang menggunakan logika filtering Python sebelum kirim ke AI.
    """
    
    # --- LANGKAH 1: FILTERING DI PYTHON (HEMAT TOKEN) ---
    # Kita cari baris yang mengandung kata kunci dari prompt user
    prompt_lower = prompt.lower()
    keywords = prompt_lower.split()
    
    # Buat mask pencarian (default False)
    mask = pd.Series([False] * len(df_database))
    
    # Cek apakah keyword ada di kolom-kolom penting
    # (Menggunakan try-except untuk menghindari error jika kolom tidak ada)
    cols_to_search = ['NAMA_PROMO', 'BANK_PARTNER', 'DETAIL_DISKON']
    valid_search_cols = [c for c in cols_to_search if c in df_database.columns]

    found_keyword = False
    for word in keywords:
        # Abaikan kata pendek (< 3 huruf) biar tidak terlalu umum
        if len(word) >= 3:
            for col in valid_search_cols:
                # Cari kata kunci (case insensitive)
                mask = mask | df_database[col].str.contains(word, case=False, na=False)
                found_keyword = True
    
    # Terapkan filter
    if found_keyword:
        df_filtered = df_database[mask]
    else:
        # Jika prompt terlalu pendek, jangan ambil semua data, kosongkan saja biar AI jawab umum
        df_filtered = pd.DataFrame()

    # Batasi maksimal 5-10 promo saja agar token tidak jebol
    if len(df_filtered) > 8:
        df_filtered = df_filtered.head(8)

    # --- LANGKAH 2: FORMAT DATA KE MARKDOWN ---
    kolom_relevan = ['NAMA_PROMO', 'PROMO_STATUS', 'PERIODE', 'SYARAT_UTAMA', 'DETAIL_DISKON', 'BANK_PARTNER']
    kolom_valid = [kol for kol in kolom_relevan if kol in df_database.columns]
    
    if not df_filtered.empty:
        db_string = df_filtered[kolom_valid].to_markdown(index=False)
        status_msg = "(Data ditemukan di database)"
    else:
        db_string = "TIDAK ADA DATA PROMO YANG COCOK DENGAN KATA KUNCI USER."
        status_msg = "(Data tidak ditemukan)"
    
    # Ambil riwayat chat terakhir
    history = "\n".join([
        f"{'User' if msg['role'] == 'user' else 'Kozy'}: {msg['content']}" 
        for msg in st.session_state.messages[-4:] 
    ])

    # Konfigurasi Model (Menggunakan Flash agar hemat)
    model = genai.GenerativeModel("models/gemini-2.5-flash") # Update ke model terbaru/flash
    
    # --- LANGKAH 3: PROMPT (TIDAK BERUBAH SECARA ESENSI) ---
    gemini_prompt = f"""
    Kamu adalah Kozy, asisten kasir internal AZKO. Nada bicaramu ramah, percaya diri, dan to-the-point.

    TUGAS:
    Jawab pertanyaan User ("{prompt}") berdasarkan DATA TERFILTER berikut.

    ---
    DATA PROMO TERFILTER:
    {db_string}
    ---
    RIWAYAT CHAT:
    {history}
    ---

    ATURAN:
    1. Jika data ada di tabel di atas, jelaskan detailnya (Nama, Bank, Diskon, Syarat).
    2. Jika kolom 'DETAIL_DISKON' berisi Link/URL, WAJIB tampilkan format: `[Klik Detail Disini](URL)`.
    3. Jika data KOSONG/TIDAK ADA di tabel terfilter:
       - Katakan: "Maaf, aku cek database belum nemu info soal '{prompt}'."
       - Sarankan hubungi SPV/Finrep.
       - Jangan mengarang promo yang tidak ada.
    
    Jawaban Kozy:
    """

    try:
        response = model.generate_content(gemini_prompt)
        return response.text.strip()
    except Exception as e:
        st.error(f"Error dari API Gemini: {e}")
        return "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."

# ==========================================================
# === APLIKASI CHATBOT UTAMA (STRUKTUR TETAP) ===
# ==========================================================
def run_chatbot_app():
    """
    Ini adalah kode aplikasi chatbot Anda.
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

    # --- AMBIL DATA DARI G-SHEET ---
    df_original = get_database_df(gc, SHEET_KEY)

    # --- KONFIGURASI HALAMAN ---
    st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

    # ==========================================================
    # === CSS KUSTOM (SESUAI PERMINTAAN: TIDAK BERUBAH) ===
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

    # --- INPUT CHAT ---
    if prompt := st.chat_input("Ketik info promo yang dicari..."):
        # 1. Tampilkan pertanyaan user
        st.chat_message("user").markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        # 2. Panggil "Otak AI"
        try:
            with st.spinner("Kozy lagi mikir..."):
                # PANGGILAN FUNGSI YANG SUDAH KITA PERBAIKI DI ATAS
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
login_form()