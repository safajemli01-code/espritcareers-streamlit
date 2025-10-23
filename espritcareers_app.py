import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
import re
import io

st.set_page_config(page_title="EspritCareers", layout="wide")

st.title("📄 EspritCareers – Analyse de CV & Lettres de Motivation")
st.write("Téléverse ton document (PDF, DOCX ou image) pour obtenir ton score ATS et des recommandations.")

uploaded_file = st.file_uploader("Choisir un fichier", type=["pdf", "docx", "png", "jpg", "jpeg"])

def extract_text_from_file(file):
    name = file.name.lower()
    if name.endswith(".pdf"):
        doc = fitz.open(stream=file.read(), filetype="pdf")
        text = ""
        for page in doc:
            t = page.get_text().strip()
            if not t:
                img = page.get_pixmap()
                img = Image.open(io.BytesIO(img.tobytes()))
                t = pytesseract.image_to_string(img, lang="fra+eng")
            text += "\n" + t
        return text
    elif name.endswith(".docx"):
        docx = Document(io.BytesIO(file.read()))
        return "\n".join(p.text for p in docx.paragraphs)
    elif name.endswith((".png", ".jpg", ".jpeg")):
        img = Image.open(file)
        return pytesseract.image_to_string(img, lang="fra+eng")
    else:
        return ""

def ats_score(cv_text, job_keywords):
    text = re.sub(r"[^a-zA-ZÀ-ÿ0-9\s]", " ", cv_text.lower())
    must_have = job_keywords["must_have"]
    nice_to_have = job_keywords["nice_to_have"]

    must_hits = sum(1 for k in must_have if k.lower() in text)
    nice_hits = sum(1 for k in nice_to_have if k.lower() in text)

    score = round((must_hits/len(must_have))*60 + (nice_hits/len(nice_to_have))*40, 1)
    return min(score, 100)

# Exemple d’offre : tu peux le personnaliser
job_keywords = {
    "must_have": ["python", "sql", "data", "analyse", "reporting", "kpi"],
    "nice_to_have": ["power bi", "tableau", "machine learning", "excel", "visualisation"]
}

if uploaded_file:
    st.success("✅ Fichier importé avec succès.")
    text = extract_text_from_file(uploaded_file)

    if len(text) < 100:
        st.warning("Le fichier semble vide ou scanné de mauvaise qualité.")
    else:
        st.subheader("🧠 Analyse du contenu")
        with st.expander("Afficher le texte extrait"):
            st.text_area("Texte extrait", text, height=300)

        score = ats_score(text, job_keywords)

        st.metric("🎯 Score ATS", f"{score} / 100")

        st.progress(score / 100)

        if score < 60:
            st.error("Le CV a besoin d’améliorations. Pense à ajouter les mots-clés manquants.")
        elif score < 80:
            st.warning("Bon CV, mais peut encore être optimisé.")
        else:
            st.success("Excellent CV ! Il est bien aligné avec l’offre.")

        st.subheader("💡 Suggestions automatiques")
        st.markdown("- Vérifie la présence de chiffres (% ou résultats).")
        st.markdown("- Utilise des verbes d’action : *développé, optimisé, analysé...*")
        st.markdown("- Mets en avant tes projets concrets et tes outils maîtrisés.")
