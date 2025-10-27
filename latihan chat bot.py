import google.generativeai as genai
import streamlit as st
import gspread

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
        # 1. Ambil dictionary Read-Only dari Streamlit
        original_secrets = st.secrets["gcp_service_account"]

        # 2. 🛠️ PERBAIKAN: Gunakan dict() untuk membuat salinan (copy)
        #    Ini menggantikan .copy() yang menyebabkan error
        secrets_dict_copy = dict(original_secrets)

        # 3. Modifikasi SALINAN (bukan aslinya)
        if "private_key" in secrets_dict_copy:
            secrets_dict_copy["private_key"] = secrets_dict_copy["private_key"].replace('\\n', '\n')
        else:
            st.error("❌ Gagal memuat data: 'private_key' tidak ditemukan di Streamlit Secrets.")
            return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."

        # 4. Gunakan SALINAN yang sudah bersih untuk otentikasi
        gc = gspread.service_account_from_dict(secrets_dict_copy)
        
        # GANTI DENGAN URL GOOGLE SHEET PROMO ANDA DI SINI
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

    except KeyError:
        st.error(
            "❌ Gagal memuat data Sheets. Kunci 'gcp_service_account' tidak ditemukan. "
            "Pastikan semua 11 secret 'gcp_service_account.*' sudah benar di Streamlit Cloud."
        )
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
