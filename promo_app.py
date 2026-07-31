import os
import time
import streamlit as st
import gspread
import pandas as pd
from google import genai

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def cleanup_old_files():
    """Hapus file di folder uploads yang umurnya lebih dari 12 jam"""
    now = time.time()
    for filename in os.listdir(UPLOAD_DIR):
        filepath = os.path.join(UPLOAD_DIR, filename)
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > 12 * 3600:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
# ==========================================================
# === KONFIGURASI UTAMA HALAMAN (WAJIB PERTAMA KALI) ===
# ==========================================================
st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

# ==========================================================
# === 1. FUNGSI LOGIN & AUTENTIKASI ===
# ==========================================================
def login_form():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        run_chatbot_app()
    else:
        st.title("🔒 Silakan Login")
        st.write("Masukkan kredensial untuk mengakses Kozy Asisten Kasir.")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="Username Anda")
            password = st.text_input("Password", type="password", placeholder="Password Anda")
            submitted = st.form_submit_button("Login")

            if submitted:
                # Validasi pembacaan secrets yang aman
                app_creds = st.secrets.get("app_credentials", {})
                correct_user = app_creds.get("APP_USER")
                correct_pass = app_creds.get("APP_PASS")

                if not correct_user or not correct_pass:
                    st.error("❌ Kredensial aplikasi (APP_USER / APP_PASS) belum di-setting atau kosong di secrets.toml")
                    return

                if username.strip() == str(correct_user).strip() and password == str(correct_pass):
                    st.session_state.authenticated = True
                    st.success("Login berhasil! Memuat aplikasi...")
                    st.rerun()
                else:
                    st.error("Username atau Password salah.")

# ==========================================================
# === 2. DATABASE & OTAK AI ENGINE ===
# ==========================================================
@st.cache_data(ttl=300)
def get_database_df(_gc, sheet_key, worksheet_name):
    """Mengambil dan men-cache DataFrame dari Google Sheets berdasarkan nama worksheet."""
    try:
        sheet = _gc.open_by_key(sheet_key).worksheet(worksheet_name)
        records = sheet.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # Pembersihan header kolom dan nilai NaN
        df.columns = [str(col).strip() for col in df.columns]
        df = df.fillna("")
        return df
    except Exception as e:
        raise RuntimeError(f"Gagal mengambil data dari worksheet '{worksheet_name}': {e}")

def get_ai_response(prompt: str, df_database: pd.DataFrame, kategori_pilihan: str, chat_messages: list, api_key: str, media_paths: list = None):
    """
    Fungsi Otak AI KOZY (Menggunakan SDK Google GenAI Resmi Terbaru)
    """
    if df_database.empty:
        return "Maaf, data database untuk kategori ini sedang kosong atau tidak dapat diakses."

    # 1. Penyiapan Filter Kolom Database
    if kategori_pilihan == "Tanya Promo dan Pembayaran":
        kolom_tampil = ['NAMA_PROMO', 'PROMO_STATUS', 'PERIODE', 'SYARAT_UTAMA', 'DETAIL_DISKON', 'BANK_PARTNER']
        valid_cols = [k for k in kolom_tampil if k in df_database.columns]
        if valid_cols:
            db_string = df_database[valid_cols].to_csv(index=False)
        else:
            db_string = df_database.to_csv(index=False)
    else:
        db_string = df_database.to_csv(index=False)

    # 2. Siapkan Riwayat Chat Terakhir (Eksklusi prompt baru agar tidak duplikasi)
    past_messages = chat_messages[:-1] if chat_messages else []
    history = "\n".join([
        f"{'User' if msg['role'] == 'user' else 'Kozy'}: {msg['content']}"
        for msg in past_messages[-3:]
    ]) if past_messages else "Belum ada riwayat sebelumnya."

    # 3. Prompt Khusus per Kategori
    if kategori_pilihan == "Tanya Promo dan Pembayaran":
        instruksi_khusus = (
            "2. Cari kecocokannya di DATABASE PROMO di atas.\n"
            "3. Jika promo DITEMUKAN: Jelaskan Nama Promo, Detail Diskon, dan Syarat Utama dengan format bullet points yang rapi dan bahasa yang santai tapi jelas.\n"
            "4. Jika promo TIDAK DITEMUKAN di database: Katakan mohon maaf dengan sopan bahwa promo untuk bank/item tersebut belum tersedia saat ini.\n"
            "5. ATURAN WAJIB: Di akhir SETIAP jawabanmu mengenai promo (baik promo itu ada maupun tidak ada), kamu WAJIB menambahkan kalimat persis seperti ini: \"Untuk informasi lebih lanjut silahkan bertanya ke Finrep Area kamu ya 😊\""
        )
    else:
        instruksi_khusus = (
            "2. ATURAN MUTLAK SOAL CICILAN (OVERRIDE): Jika pertanyaan user mengandung kata \"cicil\" atau \"cicilan\", BATALKAN semua pencarian instruksi dari database. JANGAN berikan nama EDC atau MOP pengganti sama sekali karena ini sangat berisiko untuk customer. Langsung berikan jawaban yang ramah bahwa untuk kendala mesin terkait transaksi cicilan atau pengajuan cicilan manual, kasir harus melapor ke atasan, lalu AKHIRI DENGAN KALIMAT PERSIS INI: \"Untuk informasi lebih lanjut silahkan bertanya ke Finrep Area kamu ya 😊\"\n"
            "3. TUGAS UTAMA (PERTANYAAN NORMAL BUKAN CICILAN):\n"
            "   - Jika user menyebutkan nama bank tapi TIDAK MENYEBUTKAN jenis transaksinya (Debit/Kredit/QR), JANGAN ASUMSI HANYA SATU JENIS.\n"
            "   - Carilah SEMUA baris (Debit, Kredit, QR) yang berkaitan dengan bank tersebut (jika tidak ada spesifik, cek kategori 'BANK LAIN').\n"
            "   - Rangkum jawabannya dengan menyebutkan \"EDC Yang digunakan\" dan \"Pilihan MOP Sesuai Type\" untuk MASING-MASING jenis transaksi (Debit dan Kredit) agar kasir tahu semua opsinya.\n"
            "   - Jika user SUDAH menyebutkan jenis transaksinya secara spesifik (misal: \"debit bca\"), barulah jawab untuk jenis itu saja.\n"
            "4. SKENARIO ERROR/GANGGUAN (BUKAN CICILAN):\n"
            "   - Jika user bertanya tentang solusi saat EDC gangguan/error untuk suatu bank, JANGAN HANYA MENCARI SATU BARIS.\n"
            "   - Carilah SEMUA baris di database (seperti Kartu Debit, Kartu Kredit, atau QR) yang berkaitan dengan bank tersebut.\n"
            "   - BACA instruksi pengganti yang ada di kolom yang berisi kata 'NOTE' pada masing-masing baris tersebut.\n"
            "   - Rangkum jawabannya dengan gaya bahasa yang luwes dan interaktif seperti asisten sungguhan.\n"
            "5. Jika di kolom 'NOTE' berisi teks \"Tidak ada alternatif pengganti EDC\", beritahu kasir secara sopan bahwa memang tidak ada mesin penggantinya."
        )

    instruksi_audio = ""
    if media_paths:
        instruksi_audio = "\n\n[CATATAN PENTING: User bertanya menggunakan PESAN SUARA (Audio). Abaikan teks '*(Mengirim Voice Note)*'. Dengarkan audionya dan langsung jawab sesuai suara tersebut. DILARANG KERAS mengatakan 'kamu belum mengetik pertanyaan' atau menyuruh user mengetik, karena mereka sedang menggunakan fitur suara!]"

    gemini_prompt = f"""Kamu adalah Kozy, asisten kasir internal AZKO yang ramah, asyik, dan selalu siap membantu.
Konteks saat ini: Kasir sedang bertanya seputar {kategori_pilihan}.

DATABASE SAAT INI:
{db_string}

RIWAYAT CHAT SEBELUMNYA:
{history}

PERTANYAAN BARU USER: "{prompt.strip()}"{instruksi_audio}

INSTRUKSI KERJA (WAJIB DIIKUTI):
1. Jika user HANYA menyapa (misal: "halo", "pagi", "woy", "test"), balaslah sapaan tersebut dengan ramah ala sesama rekan kerja, lalu tawarkan bantuan sesuai kategori yang dipilih.
{instruksi_khusus}
6. DILARANG KERAS mengarang/menghalusinasi data yang tidak ada di dalam database."""

    try:
        client = genai.Client(api_key=api_key)
        
        contents_to_send = [gemini_prompt]
        if media_paths:
            for path in media_paths:
                gemini_file = client.files.upload(file=path)
                contents_to_send.append(gemini_file)
                
        # Menggunakan nama model standar resmi Gemini SDK (gemini-3.5-flash-lite)
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=contents_to_send
        )
        return response.text.strip()
    except Exception as e:
        return f"Duh, sinyal Kozy lagi putus-putus nih ({e}). Tanya lagi dong."

# ==========================================================
# === 3. APLIKASI CHATBOT UTAMA ===
# ==========================================================
def run_chatbot_app():
    # Jalankan pembersihan file usang setiap kali app dimuat
    cleanup_old_files()
    
    # --- SIDEBAR & LOGOUT ---
    with st.sidebar:
        st.write("👤 **Status:** Terautentikasi")
        if st.button("🚪 Logout", key="logout_button"):
            st.session_state.authenticated = False
            st.rerun()

    # --- KONFIGURASI API DAN SHEETS ---
    API_KEY = (
        st.secrets.get("GEMINI_API_KEY")
        or st.secrets.get("GOOGLE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    if not API_KEY:
        st.error("❌ API key Gemini tidak ditemukan. Tambahkan secret 'GEMINI_API_KEY' di Streamlit Secrets.")
        st.stop()

    if "gcp_service_account" not in st.secrets:
        st.error("❌ Service account Google Sheets ('gcp_service_account') tidak ditemukan di Streamlit Secrets.")
        st.stop()

    try:
        gcp = dict(st.secrets["gcp_service_account"])
        # Format penanganan newline pada private key jika disimpan sebagai string literal '\\n'
        if "private_key" in gcp and isinstance(gcp["private_key"], str):
            gcp["private_key"] = gcp["private_key"].replace("\\n", "\n")
        gc = gspread.service_account_from_dict(gcp)
    except Exception as e:
        st.error(f"❌ Gagal memuat kredensial GCP Service Account: {e}")
        st.stop()

    SHEET_KEY = st.secrets.get("SHEET_KEY")
    if not SHEET_KEY:
        st.error("❌ 'SHEET_KEY' tidak ditemukan di Streamlit Secrets.")
        st.stop()

    # --- CSS KUSTOM ---
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
        
        /* Responsif untuk layar kecil/HP */
        @media (max-width: 768px) {
            .css-1d391kg {
                padding-left: 0.5rem;
                padding-right: 0.5rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # --- HEADER APLIKASI ---
    st.markdown(
        """
        <div style='text-align: center; margin-bottom: 0.5rem;'>
            <img src="https://raw.githubusercontent.com/fajarachmad15/Azko-Promo-Bot/main/azko-logo-white-on-red.png" alt="AZKO Logo" style="width: 50px; margin-bottom: 0.5rem;">
            <h1 style='margin-bottom: 0.2rem; font-size: 2.2rem;'>Kozy – Asisten Kasir AZKO</h1>
            <p style='color: gray; font-size: 1.0rem;'>supported by <b>Gemini AI</b></p>
            <p style='color: #d9534f; font-size: 1.0rem;'>⚠️ Kozy dapat membuat kesalahan. Selalu konfirmasi info penting.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("---") 

    # --- FITUR WAJIB PILIH KATEGORI ---
    kategori_pilihan = st.radio(
        "Pilih kategori bantuan yang dibutuhkan:",
        ("Tanya Promo dan Pembayaran", "Kategori MOP & EDC"),
        horizontal=True,
        index=None 
    )

    # Management State Pergantian Kategori
    if "current_kategori" not in st.session_state:
        st.session_state.current_kategori = kategori_pilihan
    elif st.session_state.current_kategori != kategori_pilihan:
        st.session_state.current_kategori = kategori_pilihan
        # Reset chat history saat kategori berubah agar context AI tidak tercemar
        if kategori_pilihan is not None:
            st.session_state.messages = [
                {"role": "assistant", "content": f"Kategori diubah ke **{kategori_pilihan}**. Silakan ketik pertanyaanmu! 🧐"}
            ]

    # --- LOGIKA TAMPILAN BERSYARAT ---
    if kategori_pilihan is None:
        st.info("👆 Silakan pilih kategori bantuan di atas terlebih dahulu untuk memulai obrolan dengan Kozy.")
    else:
        try:
            if kategori_pilihan == "Tanya Promo dan Pembayaran":
                df_active = get_database_df(gc, SHEET_KEY, "promo")
                placeholder_text = "Ketik info promo yang dicari..."
            else:
                df_active = get_database_df(gc, SHEET_KEY, "MOP") 
                placeholder_text = "Tanya soal mesin EDC atau MOP di sini..."
        except Exception as err:
            st.error(f"❌ {err}")
            st.stop()

        # --- STATE INISIALISASI CHAT ---
        if "messages" not in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "Halo! Aku Kozy. Silakan ketik pertanyaanmu di bawah ya! 🧐"}
            ]

        # --- UI CHAT ---
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # --- VOICE NOTE ---
        # Mic diletakkan persis di atas chat input
        with st.popover("🎙️ Voice Note"):
            with st.form("audio_form", clear_on_submit=True):
                st.caption("💡 Setelah selesai merekam, pastikan Anda menekan tombol kirim di bawah ini.")
                recorded_audio = st.audio_input("Rekam Suara")
                submit_audio = st.form_submit_button("Kirim Voice Note 🚀")

        # --- INPUT CHAT (Tanpa lampiran gambar) ---
        chat_val = st.chat_input(placeholder_text)
        
        # Mengecek apakah ada trigger dari chat_input ATAU tombol kirim audio
        if chat_val or submit_audio:
            media_paths = []
            display_prompt = ""

            # Jika trigger dari st.chat_input
            if chat_val:
                display_prompt = chat_val
            
            # Jika trigger dari st.audio_input
            if submit_audio and recorded_audio:
                display_prompt = "*(Mengirim Voice Note)*"
                audio_path = os.path.join(UPLOAD_DIR, f"audio_{int(time.time())}.wav")
                with open(audio_path, "wb") as f:
                    f.write(recorded_audio.read())
                media_paths.append(audio_path)

            st.chat_message("user").markdown(display_prompt)
            st.session_state.messages.append({"role": "user", "content": display_prompt})

            try:
                with st.spinner("Kozy lagi mikir..."):
                    answer = get_ai_response(
                        prompt=display_prompt, 
                        df_database=df_active, 
                        kategori_pilihan=kategori_pilihan,
                        chat_messages=st.session_state.messages,
                        api_key=API_KEY,
                        media_paths=media_paths
                    ) 
            except Exception as e:
                st.error(f"Duh, ada error: {e}")
                answer = "Maaf, lagi ada gangguan. Coba lagi ya."

            with st.chat_message("assistant"):
                st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})

# ==========================================================
# === TITIK MASUK APLIKASI ===
# ==========================================================
if __name__ == "__main__":
    login_form()