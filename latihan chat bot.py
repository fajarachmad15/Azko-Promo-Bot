import google.generativeai as genai
import streamlit as st
import gspread

# --- BAGIAN 1: KONFIGURASI DAN FUNGSI DATA ---

# 1. Konfigurasi Model Gemini
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("❌ ERROR: Kunci 'GEMINI_API_KEY' tidak ditemukan di secrets.")
    st.stop()

# 2. Fungsi untuk mengambil data dari Google Sheets
@st.cache_data(ttl=600)
def get_promo_data_from_sheet():
    try:
        # Ambil kredensial GCP dari secrets
        creds = dict(st.secrets["gcp_service_account"])
        # Pastikan private_key diformat benar (hilangkan escape newline)
        creds["private_key"] = creds["private_key"].replace("\\n", "\n")

        # Koneksi ke Google Sheets
        gc = gspread.service_account_from_dict(creds)
        sheet_url = "https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing"
        sh = gc.open_by_url(sheet_url)
        worksheet = sh.sheet1
        data = worksheet.get_all_values()

        # Susun teks promo
        promo_text = "DATA PROMO AKTIF:\n"
        for row in data[1:]:
            if len(row) >= 6 and row[0].upper() == "AKTIF":
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, "
                    f"Syarat: {row[3]}, Diskon: {row[4]}, Provider: {row[5]}\n"
                )

        return promo_text or "Tidak ada promo aktif."

    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Memuat instruksi cadangan. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."


# --- BAGIAN 2: APLIKASI WEB STREAMLIT ---

promo_terbaru = get_promo_data_from_sheet()

instruksi_penuh = (
    "Anda adalah Asisten Promo AZKO. Jawab HANYA berdasarkan data promo berikut:\n\n"
    + promo_terbaru
    + "\n\nAturan respon: Gunakan bahasa sopan, singkat, dan jelas. "
      "Jika pertanyaan di luar promo, balas: "
      "'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

try:
    # Buat model Gemini
    model = genai.GenerativeModel(
        model_name="models/gemini-flash-latest",
        system_instruction=instruksi_penuh
    )

    st.title("🤖 Asisten Promo Kasir AZKO")
    st.caption("Didukung oleh Gemini AI & Google Sheets")

    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[])

    # Tampilkan riwayat chat
    for message in st.session_state.chat.history:
        role = "user" if message.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(message.parts[0].text)

    # Input pertanyaan
    pertanyaan = st.chat_input("Ketik pertanyaan Anda di sini...")

    if pertanyaan:
        with st.chat_message("user"):
            st.markdown(pertanyaan)

        response = st.session_state.chat.send_message(pertanyaan)

        with st.chat_message("assistant"):
            st.markdown(response.text)

except Exception as e:
    st.error(f"❌ Error AI: {e}")
