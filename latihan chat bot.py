import re
import os
import streamlit as st
import gspread
import pandas as pd
import google.generativeai as genai

# --- KONFIGURASI API DAN SHEETS ---
API_KEY = (
    st.secrets.get("GEMINI_API_KEY")
    or st.secrets.get("GOOGLE_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
)
if not API_KEY:
    st.error("❌ API key Gemini tidak ditemukan. Tambahkan secret 'GEMINI_API_KEY' di Streamlit Secrets.")
    st.stop()

genai.configure(api_key=API_KEY)

if "gcp_service_account" not in st.secrets:
    st.error("❌ Service account Google Sheets tidak ditemukan di Streamlit Secrets.")
    st.stop()

try:
    gcp = dict(st.secrets["gcp_service_account"])
    gc = gspread.service_account_from_dict(gcp)
except Exception as e:
    st.error(f"❌ Gagal memuat kredensial GCP: {e}")
    st.stop()

SHEET_KEY = st.secrets.get("SHEET_KEY")
if not SHEET_KEY:
    st.error("Tambahkan 'SHEET_KEY' di Streamlit Secrets.")
    st.stop()

try:
    sheet = gc.open_by_key(SHEET_KEY).worksheet("promo")
    df = pd.DataFrame(sheet.get_all_records())
except Exception as e:
    st.error(f"❌ Gagal memuat data Sheets. Error: {e}")
    st.stop()

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="Kozy - Asisten Kasir AZKO", page_icon="🛍️", layout="centered")

# --- HEADER UTAMA ---
st.markdown(
    """
    <div style='text-align: center; margin-bottom: 1rem;'>
        <h1 style='margin-bottom: 0;'>🛍️ Kozy – Asisten Kasir AZKO</h1>
        <p style='color: gray; font-size: 0.9rem;'>supported by <b>Gemini AI</b></p>
        <p style='color: #d9534f; font-size: 0.8rem;'>⚠️ Kozy dapat membuat kesalahan. Selalu konfirmasi info penting.</p>
    </div>
    """,
    unsafe_allow_html=True
)

# --- STATE INISIALISASI ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Halo! Aku Kozy, asisten promo internal AZKO. Ada info promo apa yang kamu butuh? 🧐"}
    ]
if "context" not in st.session_state:
    st.session_state.context = ""
if "last_intent" not in st.session_state:
    st.session_state.last_intent = "greeting"

# --- FUNGSI PENDUKUNG ---

# ✨ FUNGSI BARU: Deteksi intent menggunakan AI (Gemini)
@st.cache_data(ttl=3600) # Cache hasil agar tidak boros API
def detect_intent_ai(text: str) -> str:
    text = text.lower().strip()
    
    # 1. Handle sapaan umum non-AI agar cepat
    simple_greetings = re.search(r"\b(halo|hai|hi|hello|hey|selamat (pagi|siang|sore|malam))\b", text)
    simple_thanks = re.search(r"\b(terima kasih|makasih|thanks|tq)\b", text)
    simple_goodbye = re.search(r"\b(dah|bye|sampai jumpa|exit)\b", text)
    
    if simple_greetings: return "greeting"
    if simple_thanks: return "thanks"
    if simple_goodbye: return "goodbye"

    # 2. Gunakan AI untuk membedakan "promo" dari "other" (basa-basi/di luar topik)
    try:
        # === PERBAIKAN ===
        model = genai.GenerativeModel("models/gemini-flash-latest")
        # === PERBAIKAN SELESAI ===
        
        prompt = f"""
        Klasifikasikan maksud (intent) dari user (seorang kasir) berikut.
        Pilih HANYA SATU dari kategori ini: [promo, smalltalk, other]
        
        - "promo": Semua pertanyaan tentang diskon, voucher, bank, metode pembayaran, cashback, dll. (TERMASUK TYPO seperti 'vucher', 'voucer', 'discon', dll).
        - "smalltalk": Basa-basi (apa kabar, lagi apa, kamu siapa).
        - "other": Pertanyaan di luar topik promo.
        
        User: "{text}"
        Intent:
        """
        response = model.generate_content(prompt).text.strip().lower()
        
        # Membersihkan respons AI
        if "promo" in response: return "promo"
        if "smalltalk" in response: return "smalltalk"
        if "other" in response: return "other"
        
        # Fallback jika AI menjawab aneh, anggap saja "promo"
        return "promo"
    except Exception:
        # Failsafe jika API call gagal, anggap "promo"
        return "promo"

def find_smart_matches(df: pd.DataFrame, query: str) -> pd.DataFrame:
    # === PERBAIKAN ===
    model = genai.GenerativeModel("models/gemini-flash-latest")
    # === PERBAIKAN SELESAI ===
    
    # Prompt ini sudah bagus, akan menangani typo "vucher" menjadi "voucher"
    prompt = f"Tentukan 3 kata kunci utama dari pertanyaan berikut untuk mencari promo: '{query}'. Balas hanya kata kunci dipisahkan koma."
    try:
        keywords = model.generate_content(prompt).text.lower().split(",")
        keywords = [k.strip() for k in keywords if k.strip()]
    except Exception:
        keywords = [query.lower()]

    mask = pd.Series([False] * len(df))
    for kw in keywords:
        for c in df.columns:
            # Pastikan kolom adalah string sebelum menggunakan .str
            if pd.api.types.is_string_dtype(df[c]):
                mask |= df[c].str.lower().str.contains(kw, na=False)
            else:
                mask |= df[c].astype(str).str.lower().str.contains(kw, na=False)
    return df[mask]

# --- UI CHAT ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- INPUT CHAT ---
if prompt := st.chat_input("Ketik info promo yang dicari..."):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    # ✨ LOGIKA BARU: Panggil fungsi AI untuk deteksi intent
    intent = detect_intent_ai(prompt)
    topic_changed = (intent != st.session_state.last_intent)
    
    if topic_changed:
        st.session_state.context = ""
    
    answer = ""
    
    # --- JAWABAN TEMPLATE (MODIFIKASI DI SINI) ---
    # Jawaban default jika terjadi error
    default_fallback_answer = "Duh, maaf, Kozy lagi agak error nih. Coba tanya lagi ya."
    
    # Template final (Langkah 3) untuk arahan ke Finrep
    finrep_template_answer = (
        "Untuk kepastian lebih lanjut, silakan **cek email dari Partnership/PNA** "
        "atau **bertanya ke Finrep Area kamu** ya. Selalu pastikan info promo sebelum transaksi. 👍"
    )
    
    # Jawaban jika tidak ketemu & BUKAN voucher (langkah 1 + 3)
    not_found_non_voucher_answer = (
        f"Hmm, aku cek di database Kozy, info soal itu **belum ter-update** nih. "
        f"{finrep_template_answer}"
    )
    # --- AKHIR MODIFIKASI TEMPLATE ---

    if intent == "greeting":
        greet = "Halo 👋"
        if "pagi" in prompt: greet = "Selamat pagi 🌞"
        elif "siang" in prompt: greet = "Selamat siang ☀️"
        elif "sore" in prompt: greet = "Selamat sore 🌇"
        elif "malam" in prompt: greet = "Selamat malam 🌙"
        answer = f"{greet}! Aku Kozy, asisten promo internal AZKO. Ada yang bisa dibantu?"

    elif intent == "smalltalk":
        answer = "Aku Kozy, asisten AI kamu. Siap bantu cari info promo. Ada yang ditanyakan soal promo?"

    elif intent == "thanks":
        answer = "Sama-sama! 👍 Lanjut cari info lain?"

    elif intent == "goodbye":
        answer = "Oke, sampai nanti ya! Selamat bekerja. 🛍️"

    elif intent == "promo":
        try:
            matches = find_smart_matches(df, prompt)

            if matches.empty:
                # ==========================================================
                # === BLOK MODIFIKASI BARU (Voucher vs Non-Voucher) ===
                # ==========================================================
                
                is_voucher_query = False
                try:
                    # 1. Cek dulu apakah ini pertanyaan soal "voucher"
                    with st.spinner("Menganalisis pertanyaan..."):
                        # === PERBAIKAN ===
                        check_model = genai.GenerativeModel("models/gemini-flash-latest")
                        # === PERBAIKAN SELESAI ===
                        
                        check_prompt = f"""
                        Apakah pertanyaan user ini spesifik tentang 'voucher' (termasuk typo 'vucher', 'voucer', 'vocer')?
                        User: "{prompt}"
                        Jawab HANYA 'YA' atau 'TIDAK'.
                        """
                        check_response = check_model.generate_content(check_prompt).text.strip().upper()
                        if "YA" in check_response:
                            is_voucher_query = True
                except Exception as e:
                    # Failsafe: Cek manual jika AI gagal
                    st.warning(f"AI voucher check failed: {e}. Menggunakan cek manual.")
                    prompt_lower = prompt.lower()
                    if "voucher" in prompt_lower or "vucher" in prompt_lower or "voucer" in prompt_lower or "vocer" in prompt_lower:
                        is_voucher_query = True

                if is_voucher_query:
                    # --- ALUR 3 LANGKAH (KHUSUS VOUCHER) ---
                    try:
                        # Langkah 1: Cek Database (Narasi)
                        step_1_db = f"Aku sudah cek di database Kozy, tapi **ketentuan untuk '{prompt}' di AZKO belum terdaftar** nih."
                        
                        # Langkah 2: Tanya Gemini
                        step_2_gemini = ""
                        with st.spinner(f"Mencari info publik soal '{prompt}' via Google..."):
                            # === PERBAIKAN ===
                            gemini_model = genai.GenerativeModel("models/gemini-flash-latest") # Pakai model cepat
                            # === PERBAIKAN SELESAI ===
                            
                            gemini_prompt = f"""
                            Anda adalah asisten AI. Kasir bertanya tentang '{prompt}' yang tidak ada di database internal.
                            Berdasarkan pengetahuan publik Anda, berikan klarifikasi singkat dan netral tentang '{prompt}' tersebut. 
                            Fokus pada apakah ini voucher umum atau spesifik untuk toko/grup tertentu.
                            
                            Mulai jawaban Anda dengan "Setelah aku klarifikasi lebih lanjut...".
                            
                            Contoh jika user bertanya 'voucher MAP':
                            "Setelah aku klarifikasi lebih lanjut, voucher MAP itu setahuku untuk toko-toko di bawah grup Mitra Adiperkasa (seperti Sogo, Zara, dll), dan AZKO sepertinya belum termasuk."
                            
                            Contoh jika user bertanya 'voucher Ultra Jaya':
                            "Setelah aku klarifikasi lebih lanjut, voucher produk Ultra Jaya itu biasanya bisa dipakai di banyak supermarket yang bekerja sama."
                            """
                            gemini_response = gemini_model.generate_content(gemini_prompt)
                            step_2_gemini = gemini_response.text.strip()

                        # Langkah 3: Template Respon (Sudah ada di `finrep_template_answer`)
                        
                        # Gabungkan semua (Gunakan format Markdown list)
                        answer = (
                            f"Oke, aku bantu cek ya untuk **{prompt}**:\n\n"
                            f"1. {step_1_db}\n\n"
                            f"2. {step_2_gemini}\n\n"
                            f"3. {finrep_template_answer}"
                        )

                    except Exception as e:
                        st.error(f"AI Gemini check (langkah 2) gagal: {e}")
                        # Failsafe jika langkah 2 (Gemini) gagal, berikan langkah 1 + 3
                        answer = (
                            f"Oke, aku bantu cek ya untuk **{prompt}**:\n\n"
                            f"1. Aku sudah cek di database Kozy, tapi **ketentuan untuk '{prompt}' di AZKO belum terdaftar**.\n\n"
                            f"2. {finrep_template_answer}"
                        )
                
                else:
                    # --- ALUR 2 LANGKAH (PROMO NON-VOUCHER) ---
                    # Jika bukan voucher (misal "promo bank BRI"), langsung beri jawaban "belum terdata".
                    answer = not_found_non_voucher_answer
                # ==========================================================
                # === AKHIR BLOK MODIFIKASI BARU ===
                # ==========================================================

            else:
                # ✅ Jika ada promo yang cocok (LOGIKA LAMA ANDA, SUDAH BAGUS)
                promos = []
                for _, r in matches.iterrows():
                    promos.append(
                        f"• **{r.get('NAMA_PROMO','')}** ({r.get('PROMO_STATUS','')})\n"
                        f"📅 Periode: {r.get('PERIODE','')}\n"
                        f"📝 {r.get('SYARAT_UTAMA','')}\n"
                        f"💰 {r.get('DETAIL_DISKON','')}\n"
                        f"🏦 Bank: {r.get('BANK_PARTNER','')}"
                    )
                hasil = "\n\n".join(promos)

                try:
                    # === PERBAIKAN ===
                    model = genai.GenerativeModel("models/gemini-flash-latest")
                    # === PERBAIKAN SELESAI ===
                    
                    # ✨ PROMPT TONE DISESUAIKAN UNTUK KASIR
                    instr = (
                        "Kamu adalah Kozy, asisten internal kasir AZKO. "
                        "Sampaikan hasil promo ini dengan jelas dan ringkas. Pastikan kasir mudah mengerti."
                    )
                    resp = model.generate_content(instr + "\n\n" + hasil + "\n\nUser: " + prompt)
                    answer = getattr(resp, "text", hasil) 
                except Exception:
                    answer = hasil
        
        except Exception as e:
            st.error(f"Error saat proses promo: {e}")
            answer = default_fallback_answer

    else: # Ini adalah intent "other"
        answer = "Hmm, maaf, aku Kozy asisten promo. Untuk pertanyaan di luar info promo, aku belum bisa bantu. Ada info promo yang mau dicari?"

    # --- OUTPUT KE CHAT ---
    with st.chat_message("assistant"):
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.context += f"User: {prompt}\nKozy: {answer}\n"
    st.session_state.last_intent = intent
