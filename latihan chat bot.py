import google.generativeai as genai
import streamlit as st
import gspread
import base64 # Import library base64

# --- BAGIAN 1: KONFIGURASI DAN FUNGSI DATA ---

# 1. Konfigurasi Model Gemini
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("❌ ERROR: Kunci 'GEMINI_API_KEY' tidak ditemukan. Mohon periksa Streamlit Cloud Secrets Anda.")
    st.stop() 

# 2. Fungsi untuk mendapatkan data dari Google Sheets
@st.cache_data(ttl=600)
def get_promo_data_from_sheet():
    """Mengambil data promo dari Google Sheets menggunakan Service Account."""
    
    try:
        # ----------------------------------------------------
        # PERBAIKAN ANTI-GAGAL: Membangun Kunci PEM dari Base64 di Kode
        # ----------------------------------------------------
        
        # 1. Simpan data inti kunci (Base64 satu baris) LANGSUNG di kode
        #    GANTI TEKS DI BAWAH INI DENGAN DATA BASE64 ANDA DARI LANGKAH 1
        private_key_base64_data = "SATU_BARIS_BASE64_PANJANG_DARI_LANGKAH_1" 
                                   
        # 2. Tentukan Header dan Footer Kunci
        PEM_HEADER = "-----BEGIN PRIVATE KEY-----"
        PEM_FOOTER = "-----END PRIVATE KEY-----"
        
        # 3. Decode Base64 (ini akan error jika data base64 salah)
        #    Kita tidak perlu decode, library cryptography bisa handle base64 langsung
        #    Kita hanya perlu memastikan formatnya benar
        
        # 4. Gabungkan menjadi format PEM yang sempurna
        full_key = PEM_HEADER + "\n" + private_key_base64_data + "\n" + PEM_FOOTER

        # 5. Bangun dictionary kita (mengambil 10 secret lain + kunci yang baru dibangun)
        secrets_dict_built = {
            "type": st.secrets["GCP_TYPE"],
            "project_id": st.secrets["GCP_PROJECT_ID"],
            "private_key_id": st.secrets["GCP_PRIVATE_KEY_ID"],
            "private_key": full_key, # <--- Menggunakan kunci yang baru kita bangun
            "client_email": st.secrets["GCP_CLIENT_EMAIL"],
            "client_id": st.secrets["GCP_CLIENT_ID"],
            "auth_uri": st.secrets["GCP_AUTH_URI"],
            "token_uri": st.secrets["GCP_TOKEN_URI"],
            "auth_provider_x509_cert_url": st.secrets["GCP_AUTH_PROVIDER_X509_CERT_URL"],
            "client_x509_cert_url": st.secrets["GCP_CLIENT_X509_CERT_URL"],
            "universe_domain": st.secrets["GCP_UNIVERSE_DOMAIN"]
        }

        # 6. Gunakan dictionary untuk otentikasi
        gc = gspread.service_account_from_dict(secrets_dict_built)
        
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing"
        sh = gc.open_by_url(SHEET_URL)
        
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        
        promo_text = "DATA PROMO AKTIF:\n"
        
        for row in data[1:]: 
            if len(row) >= 6 and row[0].upper() == 'AKTIF':
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, Syarat: {row[3]}, "
                    f"Diskon: {row[4]}, Provider: {row[5]}\n"
                )
        
        return promo_text

    except KeyError as e:
        st.error(f"❌ Gagal memuat data Sheets. Secret '{e.args[0]}' tidak ditemukan. "
                 "Pastikan semua 11 secret (GCP_TYPE, GCP_PROJECT_ID, dll KECUALI GCP_PRIVATE_KEY) sudah benar.")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
    
    except base64.binascii.Error as e:
        st.error(f"❌ Gagal memuat data Sheets. Data Base64 Kunci Privat SALAH: {e}. "
                 "Pastikan Anda menyalin data Base64 dengan benar dari file JSON dan menghapus semua '\\n'.")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."

    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Memuat instruksi cadangan. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
        

# --- BAGIAN 2: APLIKASI WEB STREAMLIT UTAMA ---
# (Bagian ini tidak berubah)

promo_terbaru = get_promo_data_from_sheet() 

instruksi_penuh = (
    "Anda adalah Asisten Promo AZKO. Tugasmu menjawab HANYA berdasarkan data promo yang diberikan.\n\n" + 
    promo_terbaru + 
    "\n\nATURAN RESPON: " + 
    "Selalu gunakan bahasa sopan, singkat dan jelas. " + 
    "JANGAN jawab di luar topik promo. Jika di luar topik, balas 'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

try:
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash', 
        system_instruction=instruksi_penuh
    )

    st.title("🤖 Asisten Promo Kasir AZKO")
    st.caption("Didukung oleh Gemini AI & Google Sheets")

    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[])

    for message in st.session_state.chat.history:
        role = "user" if message.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(message.parts[0].text)

    pertanyaan_kasir = st.chat_input("Ketik pertanyaan Anda di sini...")

    if pertanyaan_kasir:
        with st.chat_message("user"):
            st.markdown(pertanyaan_kasir)

        response = st.session_state.chat.send_message(pertanyaan_kasir)

        with st.chat_message("assistant"):
            st.markdown(response.text)

except Exception as e:
    st.error(f"❌ Error AI: Terjadi kesalahan pada konfigurasi atau saat mengirim pesan ke Gemini. Error: {e}")
