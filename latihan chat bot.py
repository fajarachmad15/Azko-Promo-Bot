import os
import re
import random
import pandas as pd
import streamlit as st
import gspread
import google.generativeai as genai

# ===============================
# 🔧 KONFIGURASI API DAN GOOGLE SHEETS
# ===============================

# Ambil API Key Gemini dari Streamlit Secrets
API_KEY = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    st.error("❌ API Key Gemini belum diisi. Tambahkan GEMINI_API_KEY di Streamlit Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

# Koneksi ke Google Sheets via service account
if "gcp_service_account" not in st.secrets:
    st.error("❌ Service account Google Sheets belum diatur di secrets.")
    st.stop()

try:
    gcp = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(gcp)
except Exception as e:
    st.error(f"❌ Gagal autentikasi ke Google Sheets: {e}")
    st.stop()

SHEET_KEY = st.secrets.get("SHEET_KEY")
if not SHEET_KEY:
    st.error("❌ Kunci Sheet (SHEET_KEY) belum ada di secrets.")
    st.stop()

try:
    sheet = gc.open_by_key(SHEET_KEY).worksheet("promo")
    df = pd.DataFrame(sheet.get_all_records())
except Exception as e:
    st.error(f"❌ Gagal membaca data promo dari Sheets: {e}")
    st.stop()

# ===============================
# 🧠 MODEL & UTILITAS
# ===============================

# === INTENT DETECTION ===
def detect_intent(text: str) -> str:
    text = text.lower().strip()
    if re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", text): return "greeting"
    if re.search(r"\b(terima kasih|makasih|thanks)\b", text): return "thanks"
    if re.search(r"\b(dah|bye|sampai jumpa)\b", text): return "goodbye"
    return "promo"

# === KOMENTAR RANDOM ===
def random_comment():
    return random.choice([
        "Hehe, info promonya lumayan berguna nih 😄",
        "Catat ya, bisa bantu jelasin juga ke pelanggan nanti!",
        "Mantap, biar nggak salah kasih info di kasir 💪",
        "Oke, semoga transaksi lancar ya!"
    ])

# === HITUNG MATCH ANTARA QUERY DAN DATA ===
def count_keyword_matches(row, tokens):
    all_text = " ".join(str(v).lower() for v in row.to_dict().values())
    return sum(1 for t in tokens if t in all_text)

# === CARI DATA PROMO COCOK SECARA CERDAS ===
def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    model = genai.GenerativeModel("models/gemini-flash-latest")
    prompt = f"Tentukan 3 kata kunci utama dari pertanyaan berikut untuk mencari promo: '{query}'. Balas hanya kata kunci dipisahkan koma."
    try:
        result = model.generate_content(prompt)
        keywords = [k.strip().lower() for k in result.text.split(",")]
    except Exception:
        keywords = query.lower().split()

    df["match_score"] = df.apply(lambda r: count_keyword_matches(r, keywords), axis=1)
    matches = df[df["match_score"] >= 2]
    return matches.sort_values("match_score", ascending=False)

# === FALLBACK JIKA DATA TIDAK ADA ===
def fallback_response(query: str) -> str:
    if re.search(r"voucher|kupon|gift", query.lower()):
        # Tambah logika tanya Gemini untuk klarifikasi voucher
        try:
            model = genai.GenerativeModel("models/gemini-flash-latest")
            prompt = f"""
            Apakah voucher '{query}' bisa digunakan di toko AZKO?
            Jawab dengan kalimat singkat dan jelas seperti menjelaskan ke karyawan kasir.
            Jika tidak yakin, jawab dengan "Voucher tersebut belum bisa digunakan di AZKO."
            """
            clarification = model.generate_content(prompt).text.strip()
        except Exception:
            clarification = "Voucher tersebut belum bisa digunakan di AZKO."

        return (
            f"Saya cek di database, belum ada ketentuan penggunaan {query} di AZKO.\n\n"
            f"Setelah saya klarifikasi lebih lanjut, hasilnya:\n👉 {clarification}\n\n"
            "Untuk kepastian lebih lanjut, silakan cek email dari *Partnership*, *PNA*, "
            "atau tanyakan ke *Finrep Area* kamu ya 😊"
        )
    else:
        return (
            "Untuk promo atau informasi yang kamu maksud, saya belum menemukan datanya. "
            "Silakan cek email dari *Partnership*, *PNA*, atau hubungi *Finrep Area* kamu untuk konfirmasi lebih lanjut ya 😊"
        )

# === FUNGSI UTAMA ===
def handle_query(df: pd.DataFrame, query: str) -> str:
    intent = detect_intent(query)

    if intent == "greeting":
        return "Halo! Kozy di sini siap bantu informasi promo dan voucher AZKO 😊"
    elif intent == "thanks":
        return "Sama-sama! Semoga infonya bermanfaat ya 💪"
    elif intent == "goodbye":
        return "Oke, sampai jumpa! Semoga transaksi kamu lancar hari ini 😊"

    # Kalau intent promo
    matches = find_smart_matches(df, query)

    if matches.empty:
        return fallback_response(query)

    # Ambil match teratas
    row = matches.iloc[0]
    nama = row["NAMA_PROMO"]
    periode = row.get("PERIODE", "-")
    syarat = row.get("SYARAT_UTAMA", "-")
    detail = row.get("DETAIL_DISKON", "-")
    bank = row.get("BANK_PARTNER", "-")

    response = (
        f"Baik, berikut info promo yang sesuai dengan pertanyaan kamu:\n\n"
        f"**Nama Promo:** {nama}\n"
        f"**Periode:** {periode}\n"
        f"**Syarat Utama:** {syarat}\n"
        f"**Detail Diskon:** {detail}\n"
        f"**Bank Partner:** {bank}\n\n"
        f"{random_comment()}"
    )

    return response

# ===============================
# 💬 UI STREAMLIT
# ===============================

st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")
st.title("🛍️ Kozy – Asisten Kasir AZKO")
st.caption("Kozy membantu kasir mencari info promo & voucher secara cepat.")

query = st.text_input("Ketik pertanyaan kamu di sini (misal: voucher MAP bisa dipakai?)")

if query:
    with st.spinner("Kozy lagi cek data... 🔎"):
        answer = handle_query(df, query)
    st.markdown(f"**Kozy:** {answer}")
