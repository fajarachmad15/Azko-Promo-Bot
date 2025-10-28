import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# --- KONFIGURASI ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
sheet = gc.open_by_key(st.secrets["SHEET_KEY"]).worksheet("promo")
df = pd.DataFrame(sheet.get_all_records())

# --- SETUP HALAMAN ---
st.set_page_config(page_title="Chatbot Promo Bank", page_icon="💬", layout="centered")

st.title("💬 Chatbot Promo Bank")

# --- INISIALISASI CHAT HISTORY ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hai! Saya asisten promo AZKO 😄 Mau tahu promo bank apa hari ini?"}
    ]

# --- TAMPILKAN RIWAYAT CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT USER ---
if prompt := st.chat_input("Ketik pertanyaan kamu di sini..."):
    # tampilkan pesan user
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # buat konteks dari data promo (disembunyikan dari user, hanya untuk model)
    context = (
        "Kamu adalah asisten ramah bernama AZKO, yang membantu pengguna mencari informasi promo bank. "
        "Gunakan gaya bahasa santai dan alami seperti percakapan sehari-hari. "
        "Jika pengguna memberi salam, balas dengan salam juga lalu perkenalkan diri kamu sebagai asisten promo AZKO. "
        "Jika mereka bertanya soal promo, jawab berdasarkan data berikut ini.\n\n"
        + df.to_string(index=False)
    )

    # hasilkan jawaban dari Gemini
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content([context, prompt])
    answer = getattr(response, "text", "Maaf, saya belum menemukan info promo yang cocok.")

    # tampilkan balasan bot
    with st.chat_message("assistant"):
        st.markdown(answer)

    # simpan ke riwayat
    st.session_state.messages.append({"role": "assistant", "content": answer})
