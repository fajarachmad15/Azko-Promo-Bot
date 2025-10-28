import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# --- KUNCI API ---
genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

# --- KONEKSI GOOGLE SHEETS ---
gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
sheet = gc.open("promo").sheet1
df = pd.DataFrame(sheet.get_all_records())

# --- SETUP HALAMAN ---
st.set_page_config(page_title="AZKO Promo Chatbot", layout="centered")
st.title("💬 Asisten Promo AZKO")

# --- SIMPAN RIWAYAT CHAT ---
if "history" not in st.session_state:
    st.session_state.history = []

# --- FUNGSI RESPON BOT ---
def get_bot_response(user_input, df):
    user_input_lower = user_input.lower()

    # Deteksi sapaan
    greetings = ["hai", "halo", "hi", "selamat pagi", "selamat siang", "selamat sore", "selamat malam"]
    if any(g in user_input_lower for g in greetings):
        return "Halo! Saya AZKO, asisten promo kamu 😊 Ada yang bisa saya bantu seputar promo bank hari ini?"

    # Cek apakah ada konteks percakapan sebelumnya
    last_context = None
    if st.session_state.history:
        for msg in reversed(st.session_state.history):
            if "promo" in msg["content"].lower():
                last_context = msg["content"].lower()
                break

    # Coba cari di data
    for i, row in df.iterrows():
        nama_promo = str(row["NAMA_PROMO"]).lower()
        if nama_promo in user_input_lower or (last_context and nama_promo in last_context):
            if str(row["PROMO_STATUS"]).lower() == "aktif":
                return (
                    f"✨ Promo **{row['NAMA_PROMO']}** masih *aktif!* 🎉\n\n"
                    f"📅 **Periode:** {row['PERIODE']}\n"
                    f"📋 **Syarat utama:** {row['SYARAT_UTAMA']}\n"
                    f"💰 **Detail diskon:** {row['DETAIL_DISKON']}\n"
                    f"🏦 **Bank/Provider:** {row['BANK_PROVIDER']}"
                )
            else:
                return f"Promo **{row['NAMA_PROMO']}** sudah tidak aktif ya. Mau saya bantu carikan promo lain dari {row['BANK_PROVIDER']}?"

    # Kalau tidak ditemukan di sheet
    return "Hmm... untuk promo itu saya belum punya konfirmasinya 😅. Kamu bisa hubungi finance rep area kamu ya biar info-nya lebih pasti."

# --- TAMPILAN CHAT BUBBLE ---
for chat in st.session_state.history:
    if chat["role"] == "user":
        st.markdown(f"<div style='text-align: right; background-color: #DCF8C6; padding:10px; border-radius: 12px; margin:4px 0;'>{chat['content']}</div>", unsafe_allow_html=True)
    else:
        st.markdown(f"<div style='text-align: left; background-color: #F1F0F0; padding:10px; border-radius: 12px; margin:4px 0;'>{chat['content']}</div>", unsafe_allow_html=True)

# --- INPUT USER ---
user_input = st.chat_input("Ketik pesan kamu di sini...")

if user_input:
    st.session_state.history.append({"role": "user", "content": user_input})
    response = get_bot_response(user_input, df)
    st.session_state.history.append({"role": "bot", "content": response})
    st.rerun()
