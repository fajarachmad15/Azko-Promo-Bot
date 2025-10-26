import google.generativeai as genai
import streamlit as st
import gspread

# --- KONFIGURASI GEMINI ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("❌ ERROR: Kunci 'GEMINI_API_KEY' tidak ditemukan di st.secrets.")
    st.stop()

# --- KONEKSI GOOGLE SHEETS ---
@st.cache_data(ttl=600)
def get_promo_data_from_sheet():
    try:
        creds = dict(st.secrets["gcp_service_account"])

        # --- Fix private_key newline ---
        creds["private_key"] = creds["private_key"].replace("\\n", "\n").strip()

        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing")
        ws = sh.sheet1
        data = ws.get_all_values()

        promo_text = "DATA PROMO AKTIF:\n"
        for row in data[1:]:
            if len(row) >= 6 and row[0].strip().upper() == "AKTIF":
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, "
                    f"Syarat: {row[3]}, Diskon: {row[4]}, Provider: {row[5]}\n"
                )

        return promo_text or "Tidak ada promo aktif."
    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."


# --- ANTARMUKA STREAMLIT ---
promo_terbaru = get_promo_data_from_sheet()
instruksi_penuh = (
    "Anda adalah Asisten Promo AZKO. Jawab HANYA berdasarkan data promo berikut:\n\n"
    + promo_terbaru
    + "\n\nAturan respon: Gunakan bahasa sopan, singkat, dan jelas. "
      "Jika pertanyaan di luar promo, balas: 'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

try:
    model = genai.GenerativeModel(
        model_name="models/gemini-flash-latest",
        system_instruction=instruksi_penuh
    )

    st.title("🤖 Asisten Promo Kasir AZKO")
    st.caption("Didukung oleh Gemini AI & Google Sheets")

    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[])

    for msg in st.session_state.chat.history:
        role = "user" if msg.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg.parts[0].text)

    q = st.chat_input("Ketik pertanyaan Anda di sini...")
    if q:
        with st.chat_message("user"):
            st.markdown(q)
        r = st.session_state.chat.send_message(q)
        with st.chat_message("assistant"):
            st.markdown(r.text)

except Exception as e:
    st.error(f"❌ Error AI: {e}")
