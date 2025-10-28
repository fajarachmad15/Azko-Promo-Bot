import streamlit as st
import gspread
import google.generativeai as genai
import pandas as pd

genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])

gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
sheet = gc.open("promo").sheet1
data = sheet.get_all_records()
df = pd.DataFrame(data)

st.title("Chatbot Promo Bank")
st.dataframe(df)

user_input = st.text_input("Ketik pertanyaan kamu:")

if user_input:
    context = "Berikut data promo yang tersedia:\n" + df.to_string(index=False)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content([context, user_input])
    st.markdown("**Chatbot:** " + response.text)
