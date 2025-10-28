import streamlit as st
import google.generativeai as genai
import gspread
import pandas as pd

st.set_page_config(page_title="Chatbot Google Sheets", page_icon="🤖")
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

gcp = dict(st.secrets["gcp_service_account"])
gc = gspread.service_account_from_dict(gcp)
sh = gc.open_by_url(st.secrets["SHEET_URL"])
worksheet = sh.sheet1
rows = worksheet.get_all_records()
df = pd.DataFrame(rows)

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

user_input = st.chat_input("Tanyakan sesuatu...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    context = "\n".join([f"Q: {r.get('Pertanyaan','')}\nA: {r.get('Jawaban','')}" for _, r in df.iterrows()])
    prompt = f"Gunakan konteks berikut untuk menjawab pertanyaan user.\n\n{context}\n\nPertanyaan user: {user_input}"

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    answer = getattr(response, "text", str(response))

    st.session_state.messages.append({"role": "assistant", "content": answer})
    with st.chat_message("assistant"):
        st.markdown(answer)
