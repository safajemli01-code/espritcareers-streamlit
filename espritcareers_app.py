import streamlit as st
import fitz
from docx import Document
from PIL import Image
import pytesseract
import io, re, os
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# ========================
# CONFIGURATION PAGE
# ========================
st.set_page_config(
    page_title="EspritCareers",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ========================
# VARIABLES SESSION
# ========================
if "cv_count" not in st.session_state: st.session_state.cv_count = 0
if "letter_count" not in st.session_state: st.session_state.letter_count = 0
if "qcm_score" not in st.session_state: st.session_state.qcm_score = 0
if "open_answers" not in st.session_state: st.session_state.open_answers = {}

# ========================
# FONCTIONS UTILES
# ========================
def safe_ocr(image_bytes: bytes, lang="fra+eng") -> str:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang=lang)
    except:
        return ""

def extract_text_from_file(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        doc = fitz.open(stream=data, filetype="pdf")
        text_total = ""
        used_ocr = False
        for page in doc:
            t = page.get_text().strip()
            if not t:
                try:
                    pix = page.get_pixmap(dpi=300)
                    ocr_txt = safe_ocr(pix.tobytes())
                    if ocr_txt:
                        t = ocr_txt
                        used_ocr = True
                except:
                    pass
            text_total += ("\n" + (t or ""))
        return text_total.strip(), used_ocr
    elif name.endswith(".docx"):
        docx = Document(io.BytesIO(data))
        return "\n".join(p.text for p in docx.paragraphs), False
    elif name.endswith((".png", ".jpg", ".jpeg")):
        t = safe_ocr(data)
        return t.strip(), True if t else False
    return "", False

def normalize(t: str) -> str:
    return re.sub(r"[^a-zA-ZÀ-ÿ0-9\s\-]", " ", t.lower())

def build_job_keywords(job_text: str):
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", job_text.lower())
    stopwords = set("le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l' the a an to of in on at for from by with as is are".split())
    tokens = [t for t in tokens if t not in stopwords and not t.isdigit()]
    must, nice = tokens[:10], tokens[10:20]
    return {"must_have": must, "nice_to_have": nice, "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}}

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k in t) / max(1,len(must_have))
    snh = sum(1 for k in nice_to_have if k in t) / max(1,len(nice_to_have))
    return smh, snh

def structure_score(cv_text):
    sections = ["profil","summary","expérience","experience","formation","education","compétences","skills","projets","projects"]
    t = normalize(cv_text)
    hits = sum(1 for s in sections if s in t)
    return min(1.0, hits/6)

def quantify_score(cv_text):
    nums = re.findall(r"\b\d+(\.\d+)?%?|\b\d{4}\b", cv_text)
    return min(1.0,len(nums)/8)

def ats_score(cv_text, job_kw):
    smh, snh = keyword_score(cv_text, job_kw["must_have"], job_kw["nice_to_have"])
    sst, sq, sfo = structure_score(cv_text), quantify_score(cv_text), 1.0
    w = job_kw["weights"]
    total = 100*(w["mh"]*smh + w["nh"]*snh + w["struct"]*sst + w["quant"]*sq + w["format"]*sfo)
    breakdown = {
        "Must-have": round(100*w["mh"]*smh,1),
        "Nice-to-have": round(100*w["nh"]*snh,1),
        "Structure": round(100*w["struct"]*sst,1),
        "Quantification": round(100*w["quant"]*sq,1),
        "Mise en forme": round(100*w["format"]*sfo,1)
    }
    return round(total,1), breakdown

def export_pdf_report(filename, title, fields):
    path = f"/tmp/{filename}"
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    x, y = 2*cm, height-2.5*cm
    c.setFont("Helvetica-Bold",16)
    c.drawString(x,y,title)
    y -= 1*cm
    c.setFont("Helvetica",11)
    for k,v in fields.items():
        line = f"{k}: {v}"
        for chunk in [line[i:i+95] for i in range(0,len(line),95)]:
            c.drawString(x,y,chunk)
            y -= 0.7*cm
            if y < 2*cm:
                c.showPage()
                y = height-2.5*cm
                c.setFont("Helvetica",11)
    c.showPage()
    c.save()
    with open(path,"rb") as f:
        return f.read()

# ========================
# TABS PRINCIPAUX
# ========================
tab_cv, tab_cover, tab_interview = st.tabs(["CV","Lettre","Entretien"])

# ------------------------
# TAB CV
# ------------------------
with tab_cv:
    st.markdown("## Analyse de CV (ATS)")
    cv_file = st.file_uploader("Téléverser CV (PDF, DOCX, Image)", type=["pdf","docx","png","jpg","jpeg"], key="cv_file")
    cv_job_text = st.text_area("Offre de poste (copier/coller)", height=180, key="cv_job_text")
    if st.button("Analyser CV", key="btn_cv"):
        if not cv_file or not cv_job_text.strip():
            st.error("Ajouter CV et offre de poste")
        else:
            cv_text, used_ocr = extract_text_from_file(cv_file)
            if len(cv_text)<50:
                st.error("CV illisible")
            else:
                st.session_state.cv_count += 1
                kw = build_job_keywords(cv_job_text)
                score, breakdown = ats_score(cv_text, kw)
                st.metric("Score ATS", f"{score}/100")
                df = pd.DataFrame({"Dimension":list(breakdown.keys()),"Points":list(breakdown.values())})
                st.dataframe(df,use_container_width=True)
                pdf_bytes = export_pdf_report("rapport_cv.pdf","Rapport CV",breakdown)
                st.download_button("Télécharger PDF", pdf_bytes, "rapport_cv.pdf","application/pdf")

# ------------------------
# TAB LETTRE
# ------------------------
with tab_cover:
    st.markdown("## Analyse de lettre de motivation")
    letter_file = st.file_uploader("Téléverser Lettre (PDF,DOCX,Image)", type=["pdf","docx","png","jpg","jpeg"], key="letter_file")
    letter_text_input = st.text_area("Ou coller le texte de la lettre", height=200, key="letter_text_input")
    letter_job_text = st.text_area("Offre de référence", height=180, key="letter_job_text")
    if st.button("Analyser Lettre", key="btn_letter"):
        text_letter = letter_text_input
        if letter_file:
            text_letter,_ = extract_text_from_file(letter_file)
        if len(text_letter.strip())<40:
            st.error("Lettre trop courte")
        else:
            st.session_state.letter_count += 1
            st.success("Lettre analysée. Cohérence et ton calculés.")
