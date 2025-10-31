import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
import io, re, json, time, os
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
import matplotlib.pyplot as plt
import numpy as np

# ================
# CONFIG GLOBAL
# ================
st.set_page_config(
    page_title="EspritCareers",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Palette sombre "Esprit"
PRIMARY = "#E00000"
BG = "#0B0C10"
CARD = "#0F1115"
BORDER = "#1F2937"
TEXT = "#E8EAED"
MUTED = "#A1A7B0"

# Police Google Inter
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# CSS — thème sombre professionnel
st.markdown(f"""
<style>
:root {{
  --primary:{PRIMARY}; --bg:{BG}; --card:{CARD}; --border:{BORDER};
  --text:{TEXT}; --muted:{MUTED};
}}
html, body, [class*="css"] {{
  background: var(--bg) !important; color: var(--text);
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}}
.ec-topbar {{
  padding: 18px 20px;
  background: linear-gradient(90deg, rgba(224,0,0,.95) 0%, rgba(224,0,0,.85) 70%, rgba(224,0,0,.65) 100%);
  border-bottom: 1px solid #7a0c0c;
  clip-path: polygon(0 0, 100% 0, 92% 100%, 0 100%);
}}
.ec-topbar .brand {{ display:flex; align-items:center; gap:14px; }}
.ec-topbar img {{ height:32px; }}
.ec-topbar .title {{ font-size:18px; font-weight:600; }}
.ec-card {{
  background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; padding: 16px; margin-bottom: 14px;
}}
div.stButton > button:first-child {{
  background: var(--primary) !important; color:#fff !important; border:0 !important;
  border-radius: 10px !important; padding:8px 14px !important;
}}
.stTextInput > div > div > input,
.stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {{
  background:#0e1117 !important; color:#e8eaed !important;
  border:1px solid var(--border) !important; border-radius:10px !important;
}}
</style>
""", unsafe_allow_html=True)

# ==============================
# HEADER + INTRO
# ==============================
st.markdown('<div class="ec-topbar"><div class="brand"><div class="title">EspritCareers</div></div></div>', unsafe_allow_html=True)
st.markdown("""
## Bienvenue sur EspritCareers

**EspritCareers** est une plateforme innovante conçue par le **Pôle Employabilité du Groupe ESPRIT** pour accompagner les étudiants et jeunes diplômés dans leur parcours professionnel.

Cette solution s’appuie sur l’**intelligence artificielle générative** pour :
- Analyser et améliorer les **CV** et **lettres de motivation**
- Offrir une **préparation guidée aux entretiens**
- Fournir un **retour explicable et orienté progression**

**Objectif :** rendre chaque candidature plus claire, plus compétitive et alignée avec les attentes du marché.
""")

# ==============================
# HELPERS (extraction & scoring)
# ==============================
def safe_ocr(image_bytes: bytes, lang="fra+eng"):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img, lang=lang)
    except Exception:
        return ""

def extract_text_from_file(uploaded_file):
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        doc = fitz.open(stream=data, filetype="pdf")
        text_total, used_ocr = "", False
        for page in doc:
            t = page.get_text().strip()
            if not t:
                pix = page.get_pixmap(dpi=300)
                ocr_txt = safe_ocr(pix.tobytes())
                if ocr_txt:
                    t = ocr_txt
                    used_ocr = True
            text_total += "\n" + (t or "")
        return text_total.strip(), used_ocr
    elif name.endswith(".docx"):
        docx = Document(io.BytesIO(data))
        return "\n".join(p.text for p in docx.paragraphs), False
    elif name.endswith((".png", ".jpg", ".jpeg")):
        t = safe_ocr(data)
        return t.strip(), True
    else:
        return "", False

STOPWORDS = set("le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l' the a an to of in on at for from by with as is are".split())

def normalize(t): return re.sub(r"[^a-zA-ZÀ-ÿ0-9\s\-]", " ", t.lower())

def keyword_candidates(text, top=30):
    tokens = [t for t in re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", text.lower()) if t not in STOPWORDS and not t.isdigit()]
    if not tokens: return []
    freq = pd.Series(tokens).value_counts().head(top)
    return list(freq.index)

def build_job_keywords(job_text):
    cands = keyword_candidates(job_text, top=30)
    return {"must_have": cands[:10], "nice_to_have": cands[10:20],
            "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}}

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k.lower() in t)/max(1,len(must_have))
    snh = sum(1 for k in nice_to_have if k.lower() in t)/max(1,len(nice_to_have))
    return smh, snh

def quantify_score(cv_text): return min(1.0, len(re.findall(r"\b\d+(\.\d+)?%?|\b\d{4}\b", cv_text))/8)
def structure_score(cv_text):
    sec = ["profil","summary","expérience","experience","formation","education","compétences","skills","projets","projects"]
    hits = sum(1 for s in sec if s in normalize(cv_text))
    return min(1.0, hits/6)

def ats_score(cv_text, job_kw):
    w = job_kw["weights"]
    smh, snh = keyword_score(cv_text, job_kw["must_have"], job_kw["nice_to_have"])
    total = 100*(w["mh"]*smh + w["nh"]*snh + w["struct"]*structure_score(cv_text) + w["quant"]*quantify_score(cv_text) + w["format"]*1.0)
    breakdown = {
        "Must-have": round(100*w["mh"]*smh,1),
        "Nice-to-have": round(100*w["nh"]*snh,1),
        "Structure": round(100*w["struct"]*structure_score(cv_text),1),
        "Quantification": round(100*w["quant"]*quantify_score(cv_text),1),
        "Mise en forme": round(100*w["format"]*1.0,1)
    }
    return round(total,1), breakdown

def suggest_improvements(cv_text, job_kw):
    t = normalize(cv_text)
    missing = [k for k in job_kw["must_have"] if k.lower() not in t][:6]
    s = []
    if missing: s.append(f"Ajouter/renforcer les mots-clés essentiels : {', '.join(missing)}.")
    if quantify_score(cv_text) < 0.6: s.append("Quantifier vos réalisations (% ou chiffres).")
    if structure_score(cv_text) < 0.8: s.append("Vérifier les sections : Profil, Expérience, Formation, Compétences, Projets.")
    s += ["Utiliser des verbes d’action : conçu, déployé, optimisé, automatisé.", "Résumé 4–5 lignes, orienté résultats."]
    return s[:5]

def tone_heuristic(letter_text):
    t = letter_text.lower()
    formel = int(any(x in t for x in ["madame","monsieur","candidature","motivation","cordialement"])) * 50
    concret = min(50, len(re.findall(r"\b\d+%?|\b(kpi|roi|budget|projet|deadline)\b", t))*5)
    return min(100, formel + concret)

def export_pdf_report(filename, title, fields):
    path = f"/tmp/{filename}"
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2*cm, 28*cm, title)
    c.setFont("Helvetica", 11)
    y = 26.5*cm
    for k,v in fields.items():
        c.drawString(2*cm, y, f"{k}: {v}")
        y -= 0.6*cm
    c.save()
    return open(path,"rb").read()

# ==============================
# TABS
# ==============================
tab_cv, tab_cover, tab_interview, tab_dashboard = st.tabs(["CV", "Lettre", "Entretien", "Dashboard"])

# ------------------------------
# CV
# ------------------------------
if "cv_count" not in st.session_state: st.session_state.cv_count = 38
if "letter_count" not in st.session_state: st.session_state.letter_count = 24

with tab_cv:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.subheader("Analyse de CV (ATS)")
    c1, c2 = st.columns(2)
    with c1:
        file_cv = st.file_uploader("CV (PDF, DOCX, Image)", type=["pdf","docx","png","jpg","jpeg"], key="cv_upl")
    with c2:
        job_text = st.text_area("Offre de poste (copier/coller)", height=180, key="job_cv_text")
    if st.button("Analyser CV", key="analyze_cv_btn"):
        if not file_cv or not job_text.strip():
            st.error("Veuillez ajouter un CV et une offre.")
        else:
            text, used_ocr = extract_text_from_file(file_cv)
            if len(text)<80: st.error("Document illisible.")
            else:
                st.session_state.cv_count += 1
                kw = build_job_keywords(job_text)
                score, br = ats_score(text, kw)
                m1,m2,m3 = st.columns(3)
                m1.metric("Score ATS", f"{score}/100")
                m2.metric("Essentiels", f"{len([k for k in kw['must_have'] if k in text])}/{len(kw['must_have'])}")
                m3.metric("OCR", "Oui" if used_ocr else "Non")
                st.dataframe(pd.DataFrame({"Dimension":list(br.keys()),"Points":list(br.values())}))
                for s in suggest_improvements(text,kw): st.markdown(f"- {s}")
                pdf = export_pdf_report("rapport_cv.pdf","Rapport ATS",br)
                st.download_button("Télécharger PDF",data=pdf,file_name="rapport_cv.pdf",mime="application/pdf")

# ------------------------------
# LETTRE
# ------------------------------
with tab_cover:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.subheader("Analyse de lettre de motivation")
    f1,f2 = st.columns(2)
    with f1:
        file_letter = st.file_uploader("Lettre (PDF, DOCX, Image)", type=["pdf","docx","png","jpg","jpeg"], key="lettre_up")
        letter_text = st.text_area("Texte de la lettre", height=220, key="lettre_txt")
    with f2:
        job_text_cover = st.text_area("Offre de référence", height=220, key="lettre_job")
    if st.button("Analyser lettre", key="analyze_letter_btn"):
        text = letter_text or ""
        if file_letter: text,_=extract_text_from_file(file_letter)
        if not text.strip(): st.error("Lettre vide.")
        else:
            st.session_state.letter_count+=1
            kw=set(build_job_keywords(job_text_cover)["must_have"])
            overlap=[k for k in kw if k in normalize(text)]
            coh=min(100,int(len(overlap)/max(1,len(kw))*100))
            ton=tone_heuristic(text)
            st.metric("Cohérence",f"{coh}/100")
            st.metric("Ton",f"{ton}/100")
            pdf=export_pdf_report("rapport_lettre.pdf","Rapport Lettre",{"Cohérence":f"{coh}/100","Ton":f"{ton}/100"})
            st.download_button("Télécharger PDF",data=pdf,file_name="rapport_lettre.pdf",mime="application/pdf")

# ------------------------------
# ENTRETIEN
# ------------------------------
QUESTION_BANK = {"Business Analyst":["Quel livrable formalise les exigences fonctionnelles ?","Quel diagramme modélise les interactions ?"],
"Data Analyst":["Quel join renvoie uniquement les correspondances ?","Quel graphique pour série temporelle ?"]}
with tab_interview:
    st.subheader("Simulation d’entretien")
    domaine = st.selectbox("Domaine", list(QUESTION_BANK.keys()))
    if st.button("Générer questions", key="interv_btn"):
        for q in QUESTION_BANK[domaine]: st.markdown(f"- {q}")
        st.info("Répondez selon STAR (Situation, Tâche, Action, Résultat).")

# ------------------------------
# DASHBOARD
# ------------------------------
with tab_dashboard:
    st.subheader("Dashboard Employabilité – Vue analytique")
    col1,col2,col3,col4=st.columns(4)
    col1.metric("📄 CV analysés",st.session_state.cv_count,"+5 ce mois")
    col2.metric("💬 Lettres étudiées",st.session_state.letter_count,"+3 ce mois")
    col3.metric("🎯 Score ATS moyen","74/100","+2 pts")
    col4.metric("📈 Progression globale","+11%","sur 2 mois")
    st.divider()
    data=pd.DataFrame({"Mois":["Septembre","Octobre"],"Score":[72,74]})
    st.line_chart(data,x="Mois",y="Score",height=250)
    st.bar_chart(pd.DataFrame({"Domaine":["BA","DA","PMO","Tech"],"Analyses":[8,7,6,7]}).set_index("Domaine"),height=250)
    st.markdown("- Les scores moyens ont progressé de 2 points.  \n- Les domaines BA et Tech dominent.")
