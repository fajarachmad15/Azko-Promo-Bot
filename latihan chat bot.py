# app.py
import os
import streamlit as st
import gspread
import google.generativeai as genai
import pandas as pd

API_KEY = st.secrets.get("GOOGLE_API_KEY") or st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    st.error("Tambahkan GEMINI/GOOGLE API key di Streamlit Secrets dengan key 'GEMINI_API_KEY' atau 'GOOGLE_API_KEY'.")
    st.stop()

genai.configure(api_key=API_KEY)

gcp = dict(st.secrets["gcp_service_account"])
gc = gspread.service_account_from_dict(gcp)
sheet = gc.open_by_key(st.secrets["SHEET_KEY"]).worksheet("promo")
data = sheet.get_all_records()
df = pd.DataFrame(data)

st.title("Chatbot Promo Bank")
st.dataframe(df)

user_input = st.text_input("Ketik pertanyaan kamu:")

if user_input:
    context = "Berikut data promo yang tersedia:\n" + df.to_string(index=False)
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content([context, user_input])
    st.markdown("**Chatbot:** " + getattr(response, "text", str(response)))
