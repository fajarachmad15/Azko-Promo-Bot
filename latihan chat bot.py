import streamlit as st
import gspread
import google.generativeai as genai

st.set_page_config(page_title="Asisten Promo Kasir AZKO", page_icon="🛍️")

# --- KONFIGURASI GEMINI ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# --- FUNGSI AMBIL DATA SHEETS ---
@st.cache_data(ttl=600)
def get_promo_data():
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1Pxc3NKB31NFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing")
        ws = sh.sheet1
        rows = ws.get_all_values()

        promo = "DATA PROMO AKTIF:\n"
        for r in rows[1:]:
            if len(r) >= 6 and r[0].upper() == "AKTIF":
                promo += f"Nama: {r[1]}, Periode: {r[2]}, Syarat: {r[3]}, Diskon: {r[4]}, Provider: {r[5]}\n"
        return promo
    except Exception as e:
        st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."

promo_text = get_promo_data()

# --- MODEL GEMINI ---
instruksi = (
    "Anda adalah Asisten Promo AZKO. Jawab HANYA berdasarkan data promo berikut:\n\n"
    + promo_text +
    "\nGunakan bahasa sopan, singkat, dan informatif.\n"
    "Jika di luar topik promo, balas: 'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

model = genai.GenerativeModel("models/gemini-1.5-flash-latest", system_instruction=instruksi)

# --- STREAMLIT CHAT ---
st.title("🛒 Asisten Promo Kasir AZKO")
st.caption("Didukung oleh Gemini AI & Google Sheets")

if "chat" not in st.session_state:
    st.session_state.chat = model.start_chat(history=[])

for m in st.session_state.chat.history:
    with st.chat_message("assistant" if m.role == "model" else "user"):
        st.markdown(m.parts[0].text)

q = st.chat_input("Ketik pertanyaan Anda di sini...")
if q:
    with st.chat_message("user"):
        st.markdown(q)
    r = st.session_state.chat.send_message(q)
    with st.chat_message("assistant"):
        st.markdown(r.text)
