import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# --- KONFIGURASI ---
API_KEY = st.secrets.get("GOOGLE_API_KEY") or st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    st.error("Tambahkan GEMINI/GOOGLE API key di Streamlit Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

# --- KONEKSI GOOGLE SHEETS ---
gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
sheet = gc.open_by_key(st.secrets["SHEET_KEY"]).worksheet("promo")
df = pd.DataFrame(sheet.get_all_records())

# --- SETUP HALAMAN ---
st.set_page_config(page_title="Chatbot Promo Bank", page_icon="💬")
st.title("💬 Chatbot Promo Bank")

# --- SIMPAN RIWAYAT OBROLAN ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- TAMPILKAN RIWAYAT CHAT ---
for chat in st.session_state.chat_history:
    with st.chat_message(chat["role"]):
        st.markdown(chat["content"])

# --- INPUT USER ---
if user_input := st.chat_input("Ketik pertanyaan kamu di sini..."):
    # tampilkan chat user
    st.chat_message("user").markdown(user_input)
    st.session_state.chat_history.append({"role": "user", "content": user_input})

    # buat konteks dari data Sheet
    context = "Berikut data promo yang tersedia:\n" + df.to_string(index=False)

    # panggil model Gemini
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([context, user_input])
    answer = getattr(response, "text", "Maaf, saya tidak bisa menjawab saat ini.")

    # tampilkan chat bot
    with st.chat_message("assistant"):
        st.markdown(answer)

    # simpan ke riwayat
    st.session_state.chat_history.append({"role": "assistant", "content": answer})
