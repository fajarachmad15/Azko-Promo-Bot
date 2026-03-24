import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# ==========================================================
# === FUNGSI LOGIN (TIDAK BERUBAH) ===
# ==========================================================
def login_form():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        run_chatbot_app()
    else:
        st.set_page_config(page_title="Login - Kozy", page_icon="🔒", layout="centered")
        st.title("🔒 Silakan Login")
        st.write("Masukkan kredensial untuk mengakses Kozy Asisten Kasir.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Username Anda")
            password = st.text_input("Password", type="password", placeholder="Password Anda")
            submitted = st.form_submit_button("Login")

            if submitted:
                try:
                    correct_user = st.secrets["app_credentials"]["APP_USER"]
                    correct_pass = st.secrets["app_credentials"]["APP_PASS"]
                except KeyError:
                    st.error("Kredensial aplikasi belum di-setting di secrets.toml")
                    return
                except Exception as e:
                    st.error(f"Error saat membaca secrets: {e}")
                    return

                if username == correct_user and password == correct_pass:
                    st.session_state.authenticated = True
                    st.success("Login berhasil! Memuat aplikasi...")
                    st.rerun()
                else:
                    st.error("Username atau Password salah.")

# ==========================================================
# === "OTAK AI" (DIPERBAIKI: ATURAN MUTLAK CICILAN) ===
# ==========================================================
@st.cache_data(ttl=300) 
def get_database_df(_gc, sheet_key, worksheet_name): 
    """Mengambil dan men-cache DataFrame dari Google Sheets berdasarkan nama worksheet."""
    try:
        sheet = _gc.open_by_key(sheet_key).worksheet(worksheet_name) 
        df = pd.DataFrame(sheet.get_all_records())
        return df
    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets '{worksheet_name}'. Error: {e}")
        st.stop()

def get_ai_response(prompt: str, df_database: pd.DataFrame, kategori_pilihan: str):
    """
    Fungsi Otak AI (Versi Hybrid Promo & MOP)
    """
    # 1. Pilih kolom 
    if kategori_pilihan == "Tanya Promo":
        kolom_tampil = ['NAMA_PROMO', 'PROMO_STATUS', 'PERIODE', 'SYARAT_UTAMA', 'DETAIL_DISKON', 'BANK_PARTNER']
        valid_cols = [k for k in kolom_tampil if k in df_database.columns]
        db_string = df_database[valid_cols].to_csv(index=False)
    else: 
        db_string = df_database.to_csv(index=False)

    # 3. Siapkan riwayat chat 
    history = "\n".join([
        f"{'User' if msg['role'] == 'user' else 'Kozy'}: {msg['content']}" 
        for msg in st.session_state.messages[-3:] 
    ])

    # 4. Inisialisasi Model
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    
    # 5. Prompt Super Pintar 
    if kategori_pilihan == "Tanya Promo":
        instruksi_khusus = """
    2. Cari kecocokannya di DATABASE PROMO di atas.
    3. Jika promo DITEMUKAN: Jelaskan Nama Promo, Detail Diskon, dan Syarat Utama dengan format bullet points yang rapi dan bahasa yang santai tapi jelas.
    4. Jika promo TIDAK DITEMUKAN di database: Katakan mohon maaf dengan sopan bahwa promo untuk bank/item tersebut belum tersedia saat ini.
    5. ATURAN WAJIB: Di akhir SETIAP jawabanmu mengenai promo (baik promo itu ada maupun tidak ada), kamu WAJIB menambahkan kalimat persis seperti ini: "Untuk informasi lebih lanjut silahkan bertanya ke Finrep Area kamu ya 😊"
        """
    else:
        instruksi_khusus = """
    2. ATURAN MUTLAK SOAL CICILAN (OVERRIDE): Jika pertanyaan user mengandung kata "cicil" atau "cicilan", BATALKAN semua pencarian instruksi dari database. JANGAN berikan nama EDC atau MOP pengganti sama sekali karena ini sangat berisiko untuk customer. Langsung berikan jawaban yang ramah bahwa untuk kendala mesin terkait transaksi cicilan atau pengajuan cicilan manual, kasir harus melapor ke atasan, lalu AKHIRI DENGAN KALIMAT PERSIS INI: "Untuk informasi lebih lanjut silahkan bertanya ke Finrep Area kamu ya 😊"
    3. TUGAS UTAMA (PERTANYAAN NORMAL BUKAN CICILAN): 
       - Jika user menyebutkan nama bank tapi TIDAK MENYEBUTKAN jenis transaksinya (Debit/Kredit/QR), JANGAN ASUMSI HANYA SATU JENIS. 
       - Carilah SEMUA baris (Debit, Kredit, QR) yang berkaitan dengan bank tersebut (jika tidak ada spesifik, cek kategori 'BANK LAIN').
       - Rangkum jawabannya dengan menyebutkan "EDC Yang digunakan" dan "Pilihan MOP Sesuai Type" untuk MASING-MASING jenis transaksi (Debit dan Kredit) agar kasir tahu semua opsinya.
       - Jika user SUDAH menyebutkan jenis transaksinya secara spesifik (misal: "debit bca"), barulah jawab untuk jenis itu saja.
    4. SKENARIO ERROR/GANGGUAN (BUKAN CICILAN):
       - Jika user bertanya tentang solusi saat EDC gangguan/error untuk suatu bank, JANGAN HANYA MENCARI SATU BARIS.
       - Carilah SEMUA baris di database (seperti Kartu Debit, Kartu Kredit, atau QR) yang berkaitan dengan bank tersebut.
       - BACA instruksi pengganti yang ada di kolom yang berisi kata 'NOTE' pada masing-masing baris tersebut.
       - Rangkum jawabannya dengan gaya bahasa yang luwes dan interaktif seperti asisten sungguhan.
    5. Jika di kolom 'NOTE' berisi teks "Tidak ada alternatif pengganti EDC", beritahu kasir secara sopan bahwa memang tidak ada mesin penggantinya.
        """

    gemini_prompt = f"""
    Kamu adalah Kozy, asisten kasir internal AZKO yang ramah, asyik, dan selalu siap membantu.
    Konteks saat ini: Kasir sedang bertanya seputar {kategori_pilihan}.
    
    DATABASE SAAT INI:
    {db_string}

    RIWAYAT CHAT:
    {history}

    PERTANYAAN BARU USER: "{prompt}"
    
    INSTRUKSI KERJA (WAJIB DIIKUTI):
    1. Jika user HANYA menyapa (misal: "halo", "pagi", "woy", "test"), balaslah sapaan tersebut dengan ramah ala sesama rekan kerja, lalu tawarkan bantuan sesuai kategori yang dipilih.
    {instruksi_khusus}
    6. DILARANG KERAS mengarang/menghalusinasi data yang tidak ada di dalam database.
    """

    try:
        response = model.generate_content(gemini_prompt)
        return response.text.strip()
    except Exception as e:
        return "Duh, sinyal Kozy lagi putus-putus nih. Tanya lagi dong."

# ==========================================================
# === APLIKASI CHATBOT UTAMA ===
# ==========================================================
def run_chatbot_app():
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

    # --- KONFIGURASI HALAMAN ---
    st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

    # ==========================================================
    # === CSS KUSTOM (SESUAI PERMINTAAN: TIDAK BERUBAH) ===
    # ==========================================================
    st.markdown(
        """
        <style>
        .css-1d391kg {
            max-width: 700px; 
            padding-left: 1rem;
            padding-right: 1rem;
        }
        :root {
            --primary-color: #BF1E2D; 
        }
        h1, h2, h3, h4, .stApp {
            font-family: 'Poppins', sans-serif; 
        }
        .stButton > button, .stTextInput > div > div > button {
            background-color: var(--primary-color) !important;
            color: white !important;
            border: none;
        }
        .stAlert.stWarning {
            background-color: #FFA50040; 
            border-left: 5px solid #FFC300; 
            color: #FFC300;
        }
        .stAlert.stWarning p {
            color: white; 
        }
        .stTextInput {
            border-radius: 0.75rem;
        }
        .stTextInput > div > div > input {
            border-radius: 0.75rem;
            border: 1px solid #BF1E2D; 
        }
        hr {
            border-top: 1px solid #BF1E2D40; 
        }
        div.row-widget.stRadio > div {
            flex-direction: row;
            justify-content: center;
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
    # === FITUR BARU: WAJIB PILIH KATEGORI (INDEX=NONE) ===
    # ==========================================================
    kategori_pilihan = st.radio(
        "Pilih kategori bantuan yang dibutuhkan:",
        ("Tanya Promo", "Tanya Panduan MOP & EDC"),
        horizontal=True,
        index=None 
    )

    # ==========================================================
    # === LOGIKA TAMPILAN BERSYARAT (KOLOM CHAT DIUMPETIN) ===
    # ==========================================================
    if kategori_pilihan is None:
        # Tampilkan pesan statis jika belum memilih
        st.info("👆 Silakan pilih kategori bantuan di atas terlebih dahulu untuk memulai obrolan dengan Kozy.")
    else:
        # Jika sudah milih, baru jalankan semua logika chat
        
        # --- AMBIL DATA DARI G-SHEET BERDASARKAN KATEGORI ---
        if kategori_pilihan == "Tanya Promo":
            df_active = get_database_df(gc, SHEET_KEY, "promo")
            placeholder_text = "Ketik info promo yang dicari..."
        else:
            df_active = get_database_df(gc, SHEET_KEY, "MOP") 
            placeholder_text = "Tanya soal mesin EDC atau MOP di sini..."

        # --- STATE INISIALISASI ---
        if "messages" not in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "Halo! Aku Kozy. Silakan ketik pertanyaanmu di bawah ya! 🧐"}
            ]
        
        if "context" in st.session_state:
            del st.session_state["context"]
        if "last_intent" in st.session_state:
            del st.session_state["last_intent"]

        # --- UI CHAT ---
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # --- INPUT CHAT ---
        if prompt := st.chat_input(placeholder_text):
            # 1. Tampilkan pertanyaan user
            st.chat_message("user").markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            # 2. Panggil "Otak AI" dengan menyertakan Kategori
            try:
                with st.spinner("Kozy lagi mikir..."):
                    answer = get_ai_response(prompt, df_active, kategori_pilihan) 
            
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