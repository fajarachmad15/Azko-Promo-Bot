import google.generativeai as genai
import streamlit as st
import gspread
import base64 # Import library base64

# --- BAGIAN 1: KONFIGURASI DAN FUNGSI DATA ---

# 1. Konfigurasi Model Gemini
try:
    # Ganti nilai di bawah ini jika kunci API Anda berbeda
    # Pastikan secret GEMINI_API_KEY ada di Streamlit Cloud
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("❌ ERROR: Kunci 'GEMINI_API_KEY' tidak ditemukan. Mohon periksa Streamlit Cloud Secrets Anda.")
    st.stop() 

# 2. Fungsi untuk mendapatkan data dari Google Sheets
@st.cache_data(ttl=600)
def get_promo_data_from_sheet():
    """Mengambil data promo dari Google Sheets menggunakan Service Account."""
    
    try:
        # ----------------------------------------------------
        # PERBAIKAN ANTI-GAGAL: Membangun Kunci PEM secara manual
        # ----------------------------------------------------
        
        # 1. Data inti kunci (Base64 satu baris) LANGSUNG di kode
        #    Ini adalah data kunci Anda yang sudah dibersihkan dari \n
        private_key_base64_data = "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCXeN1BC4KFaPqJIAdNZLqpencjr3O0+rBnF/LQ1p1RTDTwFVPP3Xk05bJPRpdrVeRMgZ9gfdx+L8ZGjhBoQ6R7ZBXjyY4m8UYcDRo/sCvi3HZyHc9FumlEkg5RuZ/DV4Xkx/xoihJsLi45wRNJlWLW9KeZePQQV0188VsI+ynlP3ezNzXU65ulybXXXTFW71Ux3/izPFPHDG7hSuq8ivpUqRqn0iwWQm9X1yvsJdhnhz5NOPfIH8X1rZ4/QqJRuGeL/81fBVFtH627eJRI5AP5CCV9UZho4RRDJf9TN2eWit9nSrR7xPsrDzhwG1KpE8EcH3mfHG+iPlpR75Sh097VAgMBAAECggEAQ4PUfucd9NAfh9p2VslUqDEVhJryRJNO6IzUpsBaW7/PgsnG00qg+XJ+oXZSDL46pd1LCEvhaX9q7czpxEeOO4+XcDJJQdNeUCeI8SVZ0mM5ClF+L1LRFAbUChpmez/6RsjbGU+duYl2AjksmypSZYSkZbRzeQso102PKbgl6u/I2k4i/gKuRKQRCX+qP0QpCHxNuqpyjEMGP9i1+c/8lcdUgx5WyNnmEInjspE6EleIMdU4+eZ9hVKoufSDHmuCCpvrij56R+klHBrEfm8HLGoVJemQiJPYuRUIS0iGqUSIBdm0Db3IO3xmcepxoTM+2Ls+B2gjk4cjy9VhB9aUOwKBgQDQfzDNykNK6oYpBPeXEztW9vG2lUzzLuCmxvtuZlubfa3ErCfrdOQZDKqHtjEMVfSxY2xgUckHsvJLHpIOCmjutBQmTPofjQQYz7cHyqTuW3wwjiTLivM+b4mSsFE3UeXfVnMxsvgy2pJrTpHJj6m/d6A/wVDXArkrMY3OL9rSwKBgQC5+6TfdoBwLna6dmYCCSQDGN4j1rYOgNZM+owCWJzndE7WhTHU6hVd+t1PhN6P/1j1q8eHJcmwLvfUJB5fzWJ+cmBN9uOromzflLHF+OlN/zutNmG4Ou/g5aImMcVGxlzhpa7l4VPTJP8iI8+GpwylUPANzkumY+CWYdDLyFpqXwKBgBhY0fUmCmekLVh66QKuTz6fhahhlOPM9JTlJZVFxKrKqVEPHXZEZyJ5tSw13VJoczOHva8dvdD1V4/oGPwkwQ4m3zd9w7ONfw36q4/wXQQskLsGzlAHPTwpacgE8L6+7E5HaAYerM4qUtYZsXV/hM9xU9tSbGXqSKddeaQXL1szAoGBAJXfH4GkMOQ1zR99gb5qN0b3pysiPxt43zixPlo1plst8soUE5AMAqP1IJqP6/oGP13Zy7Qw01LSxouBf6icDZ7v9INfTSBmh220mX17lCZyY1i11hFsDRoicoRs3xiliPudVE+TQMWJrr+INBfCTgJ6MrgtYfD302fb8zIEhjfpAoGBALEc49VKVyLdA1+7QlDDHnCbKez+K97j0UUzpT43/pIgwBO08mBofpg+icJGIiC2iNf7eYIbJ3pJO3a4QJ6ltShCMW69KoCmWPHznD55q2hmm+oDLSOeBYhlLqhJTMsJU+hWXfeMtH1BYplA2a/dVyHaz0JZBTowI6XaM2pIt7fs"
                                   
        # 2. Tentukan Header dan Footer Kunci
        PEM_HEADER = "-----BEGIN PRIVATE KEY-----"
        PEM_FOOTER = "-----END PRIVATE KEY-----"
        
        # 3. Gabungkan menjadi format PEM yang sempurna
        #    Library cryptography bisa membaca Base64 langsung jika formatnya benar
        full_key = PEM_HEADER + "\n" + private_key_base64_data + "\n" + PEM_FOOTER

        # 4. Bangun dictionary kita (mengambil 10 secret lain + kunci yang baru dibangun)
        secrets_dict_built = {
            "type": st.secrets["GCP_TYPE"],
            "project_id": st.secrets["GCP_PROJECT_ID"],
            "private_key_id": st.secrets["GCP_PRIVATE_KEY_ID"],
            "private_key": full_key, # <--- Menggunakan kunci yang baru kita bangun
            "client_email": st.secrets["GCP_CLIENT_EMAIL"],
            "client_id": st.secrets["GCP_CLIENT_ID"],
            "auth_uri": st.secrets["GCP_AUTH_URI"],
            "token_uri": st.secrets["GCP_TOKEN_URI"],
            "auth_provider_x509_cert_url": st.secrets["GCP_AUTH_PROVIDER_X509_CERT_URL"],
            "client_x509_cert_url": st.secrets["GCP_CLIENT_X509_CERT_URL"],
            "universe_domain": st.secrets["GCP_UNIVERSE_DOMAIN"]
        }

        # 5. Gunakan dictionary untuk otentikasi
        gc = gspread.service_account_from_dict(secrets_dict_built)
        
        SHEET_URL = "https://docs.google.com/spreadsheets/d/1Pxc3NK83INFoLxJGfoGQ3bnDVlj5BzV5Fq5r_rHNXp4/edit?usp=sharing"
        sh = gc.open_by_url(SHEET_URL)
        
        worksheet = sh.sheet1
        data = worksheet.get_all_values()
        
        promo_text = "DATA PROMO AKTIF:\n"
        
        for row in data[1:]: 
            if len(row) >= 6 and row[0].upper() == 'AKTIF':
                promo_text += (
                    f"- Nama: {row[1]}, Periode: {row[2]}, Syarat: {row[3]}, "
                    f"Diskon: {row[4]}, Provider: {row[5]}\n"
                )
        
        return promo_text

    except KeyError as e:
        st.error(f"❌ Gagal memuat data Sheets. Secret '{e.args[0]}' tidak ditemukan. "
                 "Pastikan semua 11 secret (GCP_TYPE, GCP_PROJECT_ID, dll) sudah benar.")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
    
    except base64.binascii.Error as e:
        st.error(f"❌ Gagal memuat data Sheets. Data Base64 Kunci Privat SALAH: {e}. "
                 "Pastikan Anda menyalin data Base64 dengan benar dari file JSON dan menghapus semua '\\n'.")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."

    except Exception as e:
        # Error InvalidPadding atau InvalidByte akan muncul di sini jika masih salah
        st.error(f"❌ Gagal memuat data Sheets. Memuat instruksi cadangan. Error: {e}")
        return "DATA TIDAK DITEMUKAN. Sampaikan ke kasir untuk cek manual."
        

# --- BAGIAN 2: APLIKASI WEB STREAMLIT UTAMA ---
# (Bagian ini tidak berubah)

promo_terbaru = get_promo_data_from_sheet() 

instruksi_penuh = (
    "Anda adalah Asisten Promo AZKO. Tugasmu menjawab HANYA berdasarkan data promo yang diberikan.\n\n" + 
    promo_terbaru + 
    "\n\nATURAN RESPON: " + 
    "Selalu gunakan bahasa sopan, singkat dan jelas. " + 
    "JANGAN jawab di luar topik promo. Jika di luar topik, balas 'Maaf, saya hanya bisa memberikan informasi promo saat ini.'"
)

try:
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash', 
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

    pertanyaan_kasir = st.chat_input("Ketik pertanyaan Anda di sini...")

    if pertanyaan_kasir:
        with st.chat_message("user"):
            st.markdown(pertanyaan_kasir)

        response = st.session_state.chat.send_message(pertanyaan_kasir)

        with st.chat_message("assistant"):
            st.markdown(response.text)

except Exception as e:
    st.error(f"❌ Error AI: Terjadi kesalahan pada konfigurasi atau saat mengirim pesan ke Gemini. Error: {e}")
