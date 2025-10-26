import google.generativeai as genai
import streamlit as st  # Kita import streamlit

# --- BAGIAN 1: PENYIAPAN (Sama seperti sebelumnya) ---

# 1. Masukkan API Key Anda (pakai tanda kutip!)
# CARA LEBIH AMAN: Gunakan st.secrets
# Untuk sekarang, kita tulis langsung (tapi jangan bagikan file ini)
genai.configure(api_key=api_key=st.secrets["GEMINI_API_KEY"])

# 2. Instruksi Promo (Sama seperti sebelumnya)
instruksi_promo = """
User
Anda adalah "Asisten Promo AZKO", petugas informasi yang ramah, ringkas, dan sangat akurat. Tugas utama Anda adalah menjawab semua pertanyaan pengguna HANYA berdasarkan data promosi BNI Wondr - Azko yang Anda miliki.

DATA PROMO:

1. Nama Promo: Potongan Rp 70.000 dengan minimal transaksi Rp 700.000 menggunakan Aplikasi BNI Wondr.
2. Periode Promo: HANYA 1 hari, yaitu 4 September 2025.
3. Metode Pembayaran (MOP): DISC 70 RB WONDR HARPELNAS - BNI QR.
4. Wajib menggunakan EDC BNI.
5. Berlaku di: Seluruh Store AZKO JABODETABEK.
6. Mekanisme Diskon:
    o Berlaku 1 kali per pengguna/user.
    o Tidak berlaku kelipatan dan pemisahan struk transaksi.
    o Hanya berlaku untuk pembelian menggunakan BNI QR dari Aplikasi BNI Wondr.
    o TIDAK berlaku untuk pembelian menggunakan BNI Mobile Banking.
7. Kuotasi: Kuota dibatasi 7 orang per store. Store wajib membuat tracking manual.

ATURAN RESPON:

    o Selalu gunakan bahasa yang sopan dan profesional.
    o Jika pengguna bertanya di luar topik promo ini (misalnya, tentang produk, jam buka toko, atau promo bank lain), JANGAN menjawab. Balas dengan: "Maaf, saya hanya dapat memberikan informasi detail mengenai Promo Potongan BNI Wondr - Azko pada tanggal 4 September 2025."
    o Pastikan semua detail angka (potongan, minimal transaksi, tanggal, kuota) benar-benar akurat sesuai data di atas.
"""

# 3. Buat modelnya DENGAN instruksi itu
model = genai.GenerativeModel(
    model_name='models/gemini-flash-latest',
    system_instruction=instruksi_promo
)


# --- BAGIAN 2: APLIKASI WEB STREAMLIT ---

# 1. Beri judul pada halaman web
st.title("🤖 Asisten Promo Kasir AZKO")
st.caption("Didukung oleh Gemini AI")

# 2. Siapkan "memori" untuk menyimpan riwayat chat
# Ini penting agar bot ingat obrolan sebelumnya
if "chat" not in st.session_state:
    # Mulai sesi obrolan baru
    st.session_state.chat = model.start_chat(history=[])

# 3. Tampilkan riwayat chat yang sudah ada
for message in st.session_state.chat.history:
    # Tampilkan pesan berdasarkan peran (user atau model)
    role = "Anda" if message.role == "user" else "Bot"
    with st.chat_message(role):
        st.markdown(message.parts[0].text)

# 4. Buat kotak input teks di bagian bawah layar
pertanyaan_kasir = st.chat_input("Ketik pertanyaan Anda di sini...")

if pertanyaan_kasir:
    # 5. Tampilkan pertanyaan kasir di layar
    with st.chat_message("Anda"):
        st.markdown(pertanyaan_kasir)

    # 6. Kirim pertanyaan ke AI dan dapatkan jawaban
    response = st.session_state.chat.send_message(pertanyaan_kasir)

    # 7. Tampilkan jawaban AI di layar
    with st.chat_message("Bot"):
        st.markdown(response.text)
