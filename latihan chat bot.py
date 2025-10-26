import google.generativeai as genai
import streamlit as st
import gspread 

# --- BAGIAN 1: PENYIAPAN & KONEKSI ---

# 1. Masukkan API Key Anda (dari Streamlit Secrets)
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# 2. Fungsi untuk mendapatkan data dari Google Sheets
# @st.cache_data memastikan fungsi ini hanya berjalan sekali per 10 menit
@st.cache_data(ttl=600) 
def get_promo_data_from_sheet():
    try:
        # Menggunakan kunci rahasia yang tersimpan di Streamlit Secrets
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        
        # GANTI DENGAN URL GOOGLE SHEET PROMO ANDA DI SINI
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing")
        
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        
        # Kumpulkan data menjadi teks yang rapi (format yang dimengerti AI)
        promo_text = "DATA PROMO AKTIF:\n"
        
        # Memproses data (mengabaikan header [0] dan promo NONAKTIF)
        for row in data[1:]: 
            # Pastikan baris memiliki 6 kolom dan statusnya AKTIF
            if len(row) >= 6 and row[0].upper() == 'AKTIF':
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, Syarat: {row[3]}, "
                    f"Diskon: {row[4]}, Provider: {row[5]}\n"
                )
        
        return promo_text

    except Exception as e:
        # Jika ada error koneksi Sheet, gunakan instruksi cadangan
        st.error(f"Gagal memuat data Sheets. Memuat instruksi cadangan. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
        
# --- BAGIAN 2: APLIKASI WEB STREAMLIT ---

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
        model_name='models/gemini-flash-latest',
        system_instruction=instruksi_penuh
    )

    st.title("🤖 Asisten Promo Kasir AZKO")
    st.caption("Didukung oleh Gemini AI & Google Sheets")

    # 4. Siapkan "memori" dan tampilkan riwayat chat
    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[])

    for message in st.session_state.chat.history:
        role = "Anda" if message.role == "user" else "Bot"
        with st.chat_message(role):
            st.markdown(message.parts[0].text)

    # 5. Kotak input teks
    pertanyaan_kasir = st.chat_input("Ketik pertanyaan Anda di sini...")

    if pertanyaan_kasir:
        with st.chat_message("Anda"):
            st.markdown(pertanyaan_kasir)

        response = st.session_state.chat.send_message(pertanyaan_kasir)

        with st.chat_message("Bot"):
            st.markdown(response.text)

except Exception as e:
        st.error(f"Error AI: Terjadi kesalahan saat mengirim pesan. Coba lagi.")
