import google.generativeai as genai
import streamlit as st
import gspread
import json # Diperlukan untuk memproses string JSON dari secrets

# --- BAGIAN 1: KONFIGURASI DAN FUNGSI DATA ---

# 1. Konfigurasi Model Gemini
try:
    # Mengambil Kunci API dari secrets
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("❌ ERROR: Kunci 'GEMINI_API_KEY' tidak ditemukan. Mohon periksa file .streamlit/secrets.toml Anda.")
    st.stop() # Hentikan aplikasi jika API Key tidak ada


# 2. Fungsi untuk mendapatkan data dari Google Sheets
@st.cache_data(ttl=600) # Data akan di-cache selama 10 menit
def get_promo_data_from_sheet():
    """Mengambil data promo dari Google Sheets menggunakan Service Account."""
    
    try:
        # 1. Ambil string JSON Service Account dari st.secrets
        sa_json_string = st.secrets["gcp_service_account"]
        
        # 2. Ubah string JSON menjadi dictionary Python
        secrets_dict = json.loads(sa_json_string)

        # 3. PERBAIKAN PENTING: Membersihkan private_key dari \n ganda
        # Ini mengatasi masalah format kunci privat saat parsing JSON
        if "private_key" in secrets_dict:
            secrets_dict["private_key"] = secrets_dict["private_key"].replace('\\n', '\n')

        # 4. Buat Service Account client
        gc = gspread.service_account_from_dict(secrets_dict)
        
        # GANTI DENGAN URL GOOGLE SHEET PROMO ANDA DI SINI
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing"
        sh = gc.open_by_url(SHEET_URL)
        
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        
        # Kumpulkan data menjadi teks yang rapi untuk prompt AI
        promo_text = "DATA PROMO AKTIF:\n"
        
        # Memproses data (mengabaikan header [0] dan promo NONAKTIF)
        for row in data[1:]: 
            # Pastikan baris memiliki 6 kolom dan statusnya AKTIF (Kolom A)
            if len(row) >= 6 and row[0].upper() == 'AKTIF':
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, Syarat: {row[3]}, "
                    f"Diskon: {row[4]}, Provider: {row[5]}\n"
                )
        
        return promo_text

    except KeyError:
        st.error(
            "❌ Gagal memuat data Sheets. Kunci 'gcp_service_account' tidak ditemukan. "
            "Pastikan secrets.toml sudah diatur dengan benar."
        )
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."

    except Exception as e:
        # Menangkap error umum (termasuk error parsing JSON 'Invalid control character')
        st.error(f"❌ Gagal memuat data Sheets. Memuat instruksi cadangan. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
        

# --- BAGIAN 2: APLIKASI WEB STREAMLIT UTAMA ---

# 1. Dapatkan data terbaru dari Sheets
promo_terbaru = get_promo_data_from_sheet() 

# 2. Gabungkan instruksi tetap dengan data terbaru dari Sheets
instruksi_penuh = (
    "Anda adalah Asisten Promo AZKO. Tugasmu menjawab HANYA berdasarkan data promo yang diberikan.\n\n" + 
    promo_terbaru + 
    "\n\nATURAN RESPON: " + 
    "Selalu gunakan bahasa sopan, singkat dan jelas. " + 
    "JANGAN jawab di luar topik promo. Jika di luar topik, balas 'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

try:
    # 3. Buat modelnya DENGAN instruksi gabungan
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash', 
        system_instruction=instruksi_penuh
    )

    st.title("🤖 Asisten Promo Kasir AZKO")
    st.caption("Didukung oleh Gemini AI & Google Sheets")

    # 4. Siapkan "memori" (session_state chat)
    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[])

    # Tampilkan riwayat chat
    for message in st.session_state.chat.history:
        role = "user" if message.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(message.parts[0].text)

    # 5. Kotak input teks
    pertanyaan_kasir = st.chat_input("Ketik pertanyaan Anda di sini...")

    if pertanyaan_kasir:
        # Tampilkan pesan user
        with st.chat_message("user"):
            st.markdown(pertanyaan_kasir)

        # Kirim pesan ke Gemini dan dapatkan respons
        response = st.session_state.chat.send_message(pertanyaan_kasir)

        # Tampilkan respons bot
        with st.chat_message("assistant"):
            st.markdown(response.text)

except Exception as e:
    st.error(f"❌ Error AI: Terjadi kesalahan pada konfigurasi atau saat mengirim pesan ke Gemini. Error: {e}")
