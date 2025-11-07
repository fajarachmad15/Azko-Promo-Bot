import re
import random
import pandas as pd
import google.generativeai as genai

# --- MODEL ---
genai.configure(api_key=API_KEY)

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

# === BANTU HITUNG MATCH ===
def count_keyword_matches(row, tokens):
    all_text = " ".join(str(v).lower() for v in row.to_dict().values())
    return sum(1 for t in tokens if t in all_text)

# === TEMUKAN MATCH CERDAS ===
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

# === JAWABAN FALLBACK JIKA DATA TIDAK ADA ===
def fallback_response(query: str) -> str:
    if re.search(r"voucher|kupon|gift", query.lower()):
        return (
            "Hmm, sepertinya info terkait voucher atau promo yang kamu maksud belum ada di data aku nih. "
            "Untuk kepastian lebih lanjut, silakan cek kembali email dari *Partnership*, *PNA*, atau tanyakan ke *Finrep Area* kamu ya 😊"
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
