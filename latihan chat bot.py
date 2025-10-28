import re
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
gc = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
sheet = gc.open_by_key(st.secrets["SHEET_KEY"]).worksheet("promo")
df = pd.DataFrame(sheet.get_all_records())

st.set_page_config(page_title="Chatbot Promo Bank", page_icon="💬", layout="centered")
st.title("💬 Chatbot Promo Bank")

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hai! Saya asisten promo AZKO 😄 Mau tahu promo bank apa hari ini?"}
    ]

def is_greeting(text: str) -> bool:
    text = text.strip().lower()
    pattern = r"^(hi|halo|hai|hello|hey|selamat pagi|selamat siang|selamat sore|selamat malam)\b"
    return re.match(pattern, text) is not None

def find_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    q = query.lower().strip()
    if not q:
        return df.iloc[0:0]
    cols = df.columns.tolist()
    mask = pd.Series([False] * len(df))
    for c in cols:
        mask = mask | df[c].astype(str).str.lower().str.contains(q, na=False)
    return df[mask]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ketik pertanyaan kamu di sini..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    if is_greeting(prompt):
        lower = prompt.strip().lower()
        if "pagi" in lower:
            greet = "Selamat pagi"
        elif "siang" in lower:
            greet = "Selamat siang"
        elif "sore" in lower:
            greet = "Selamat sore"
        elif "malam" in lower:
            greet = "Selamat malam"
        else:
            greet = "Halo"
        answer = f"{greet}! Saya asisten promo AZKO 😊 Ada yang bisa saya bantu mengenai promo?"
        with st.chat_message("assistant"):
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
    else:
        matches = find_matches(df, prompt)
        if matches.empty:
            answer = "Maaf untuk promo tersebut saya belum terkonfirmasi. Silahkan hubungi finance rep area kamu ya."
            with st.chat_message("assistant"):
                st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        else:
            lines = []
            for _, row in matches.iterrows():
                status = row.get("PROMO_STATUS", "")
                name = row.get("NAMA_PROMO", "")
                period = row.get("PERIODE", "")
                terms = row.get("SYARAT_UTAMA", "")
                discount = row.get("DETAIL_DISKON", "")
                provider = row.get("BANK_PROVIDER", "")
                lines.append(f"- {name} ({provider}) — {status}. Periode: {period}. Syarat: {terms}. Diskon: {discount}")
            context = "Data promo relevan:\n" + "\n".join(lines)
            instruction = (
                "Kamu adalah asisten ramah bernama AZKO. Jawab singkat dan natural. "
                "Gunakan konteks berikut untuk menjawab pertanyaan pengguna."
            )
            prompt_for_model = instruction + "\n\n" + context + "\n\nPertanyaan pengguna: " + prompt
            try:
                model = genai.GenerativeModel("gemini-2.5-flash")
                resp = model.generate_content(prompt_for_model)
                answer = getattr(resp, "text", str(resp))
            except Exception:
                answer = "Berikut promo yang cocok:\n\n" + "\n".join(lines)
            with st.chat_message("assistant"):
                st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
