import google.generativeai as genai
import streamlit as st
import gspread
import json

# --- KONFIGURASI GEMINI ---
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    st.error("❌ ERROR: Kunci 'GEMINI_API_KEY' tidak ditemukan di st.secrets.")
    st.stop()

def _normalize_private_key(raw_key: str) -> str:
    if raw_key is None:
        return None
    # 1) Jika key berisi escape sequences seperti "\\n", ubah jadi newline nyata
    try:
        raw_key = raw_key.encode("utf-8").decode("unicode_escape")
    except Exception:
        pass
    # 2) Ganti literal "\n" jika ada
    raw_key = raw_key.replace("\\n", "\n")
    # 3) Trim spasi berlebih
    raw_key = raw_key.strip()
    # 4) Pastikan header/footer ada — jika tidak, kembalikan apa adanya (gspread akan error dan kita tangani)
    if not raw_key.startswith("-----BEGIN PRIVATE KEY-----"):
        # coba tambahkan header/footer jika terlihat base64 panjang
        # tapi jangan coba decode di sini; hanya tambahkan header/footer jika tidak ada sama sekali
        raw_key = "-----BEGIN PRIVATE KEY-----\n" + raw_key + "\n-----END PRIVATE KEY-----"
    return raw_key

@st.cache_data(ttl=600)
def get_promo_data_from_sheet():
    try:
        # Ambil dict credentials dari secrets
        creds = dict(st.secrets["gcp_service_account"])
        # Normalisasi private_key agar tidak menyebabkan error "Incorrect padding" / invalid base64
        if "private_key" in creds and creds["private_key"]:
            creds["private_key"] = _normalize_private_key(creds["private_key"])
        else:
            st.error("❌ ERROR: field 'private_key' kosong di st.secrets['gcp_service_account'].")
            return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."

        # Buat client gspread dari dict (gspread akan melakukan parsing private_key)
        gc = gspread.service_account_from_dict(creds)

        SHEET_URL = "https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing"
        sh = gc.open_by_url(SHEET_URL)
        worksheet = sh.sheet1
        data = worksheet.get_all_values()

        promo_text = "DATA PROMO AKTIF:\n"
        for row in data[1:]:
            if len(row) >= 6 and row[0].strip().upper() == "AKTIF":
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, Syarat: {row[3]}, "
                    f"Diskon: {row[4]}, Provider: {row[5]}\n"
                )
        return promo_text or "Tidak ada promo aktif."

    except gspread.exceptions.APIError as e:
        st.error(f"❌ Gagal autentikasi Google Sheets: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
    except Exception as e:
        # Jika error base64/incorrect padding tetap terjadi, berikan pesan diagnostik supaya user perbaiki secrets
        msg = str(e)
        if "Incorrect padding" in msg or "base64" in msg or "invalid" in msg.lower():
            st.error(
                "❌ Gagal memuat data Sheets. Terjadi error terkait format private_key (Incorrect padding / base64). "
                "Pastikan st.secrets `.streamlit/secrets.toml` menyimpan `private_key` sebagai single-line string "
                "dengan literal '\\n' untuk newline (atau benar-benar multiline), contoh:\n\n"
                'private_key = "-----BEGIN PRIVATE KEY-----\\nMIIE...\\n-----END PRIVATE KEY-----\\n"\n\n'
                "Atau simpan multiline dengan header/footer dan newline nyata. Periksa juga tidak ada spasi/quote tambahan."
            )
        else:
            st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."


# ---------------- APLIKASI STREAMLIT ----------------

promo_terbaru = get_promo_data_from_sheet()

instruksi_penuh = (
    "Anda adalah Asisten Promo AZKO. Jawab HANYA berdasarkan data promo berikut:\n\n"
    + promo_terbaru
    + "\n\nAturan respon: Gunakan bahasa sopan, singkat, dan jelas. "
      "Jika pertanyaan di luar promo, balas: 'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

try:
    model = genai.GenerativeModel(
        model_name="models/gemini-flash-latest",
        system_instruction=instruksi_penuh
    )

    st.title("🤖 Asisten Promo Kasir AZKO")
    st.caption("Didukung oleh Gemini AI & Google Sheets")

    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[])

    for message in st.session_state.chat.history:
        role = "user" if message.role == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(message.parts[0].text)

    pertanyaan = st.chat_input("Ketik pertanyaan Anda di sini...")

    if pertanyaan:
        with st.chat_message("user"):
            st.markdown(pertanyaan)
        response = st.session_state.chat.send_message(pertanyaan)
        with st.chat_message("assistant"):
            st.markdown(response.text)

except Exception as e:
    st.error(f"❌ Error AI: {e}")
