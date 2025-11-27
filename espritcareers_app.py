import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
import io, re, os
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

# ========================
# CONFIGURATION GLOBALE
# ========================
st.set_page_config(
    page_title="EspritCareers",
    layout="wide",
    initial_sidebar_state="expanded"
)

PRIMARY = "#E00000"
BG = "#0B0C10"
CARD = "#0F1115"
BORDER = "#1F2937"
TEXT = "#E8EAED"
MUTED = "#A1A7B0"

# Fonts Google
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ========================
# CSS
# ========================
st.markdown(f"""
<style>
:root {{
  --primary:{PRIMARY}; --bg:{BG}; --card:{CARD};
  --border:{BORDER}; --text:{TEXT}; --muted:{MUTED};
}}
html, body, [class*="css"] {{
  background: var(--bg) !important;
  color: var(--text);
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}}
.ec-card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px 16px 12px;margin-bottom:14px;}}
.ec-title{{font-size:18px;font-weight:600;margin-bottom:6px;}}
.ec-sub{{color:var(--muted);font-size:13px;margin-bottom:10px;}}
div.stButton>button:first-child{{
  background:var(--primary)!important;color:#fff!important;border:0!important;
  border-radius:10px!important;padding:8px 14px!important;
}}
.stDataFrame,.stTable{{color:var(--text)!important;}}
</style>
""", unsafe_allow_html=True)

# ========================
# UTILITAIRES (OCR, normalisation, ATS)
# ========================
def safe_ocr(image_bytes: bytes, lang="fra+eng") -> str:
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
                try:
                    pix = page.get_pixmap(dpi=300)
                    ocr_txt = safe_ocr(pix.tobytes())
                    if ocr_txt:
                        t = ocr_txt
                        used_ocr = True
                except Exception:
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

STOPWORDS = set("le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l' the a an to of in on at for from by with as is are".split())
def normalize(t: str) -> str:
    return re.sub(r"[^a-zA-ZÀ-ÿ0-9\s\-]", " ", t.lower())

def keyword_candidates(text, top=30):
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", text.lower())
    tokens = [t for t in tokens if t not in STOPWORDS and not t.isdigit()]
    if not tokens: return []
    freq = pd.Series(tokens).value_counts().head(top)
    return list(freq.index)

def build_job_keywords(job_text: str):
    cands = keyword_candidates(job_text, top=30)
    must, nice = cands[:10], cands[10:20]
    return {"must_have": must, "nice_to_have": nice, "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}}

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k and k in t) / max(1, len(must_have))
    snh = sum(1 for k in nice_to_have if k and k in t) / max(1, len(nice_to_have))
    return smh, snh

def quantify_score(cv_text):
    nums = re.findall(r"\b\d+(\.\d+)?%?|\b\d{4}\b", cv_text)
    return min(1.0, len(nums)/8)

def structure_score(cv_text):
    sec = ["profil","summary","expérience","experience","formation","education","compétences","skills","projets","projects"]
    t = normalize(cv_text)
    hits = sum(1 for s in sec if s in t)
    return min(1.0, hits/6)

def ats_score(cv_text, job_kw):
    mh, nh = job_kw["must_have"], job_kw["nice_to_have"]
    w = job_kw.get("weights", {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05})
    smh, snh = keyword_score(cv_text, mh, nh)
    sst, sq, sfo = structure_score(cv_text), quantify_score(cv_text), 1.0
    total = 100*(w["mh"]*smh + w["nh"]*snh + w["struct"]*sst + w["quant"]*sq + w["format"]*sfo)
    breakdown = {k: round(100*w[k.lower().split()[0]]*v,1) for k,v in zip(["Must-have","Nice-to-have","Structure","Quantification","Mise en forme"],[smh,snh,sst,sq,sfo])}
    return round(total,1), breakdown

def suggest_improvements(cv_text, job_kw):
    t = normalize(cv_text)
    missing_mh = [k for k in job_kw["must_have"] if k not in t][:6]
    suggestions = []
    if missing_mh: suggestions.append(f"Ajouter/renforcer les mots-clés essentiels : {', '.join(missing_mh)}.")
    if quantify_score(cv_text) < 0.6: suggestions.append("Quantifier les réalisations avec chiffres et %.")
    if structure_score(cv_text) < 0.8: suggestions.append("Vérifier sections Profil, Expérience, Formation, Compétences, Projets.")
    suggestions += ["Utiliser verbes d’action (conçu, déployé, optimisé).","Résumé 4–5 lignes, orienté résultats et outils."]
    return suggestions[:5]

def tone_heuristic(letter_text):
    t = letter_text.lower()
    score_formel = int(any(x in t for x in ["madame","monsieur","candidature","motivation","cordialement"])) * 50
    score_concret = min(50, len(re.findall(r"\b\d+%?|\b(kpi|roi|budget|projet|deadline)\b", t))*5)
    return min(100, score_formel + score_concret)

def export_pdf_report(filename, title, fields):
    path = f"/tmp/{filename}"
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    x, y = 2*cm, height - 2.5*cm
    c.setTitle(title)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, title)
    y -= 1*cm
    c.setFont("Helvetica", 11)
    for k, v in fields.items():
        line = f"{k}: {v}"
        for chunk in [line[i:i+95] for i in range(0, len(line), 95)]:
            c.drawString(x, y, chunk)
            y -= 0.7*cm
            if y < 2*cm:
                c.showPage()
                y = height - 2.5*cm
                c.setFont("Helvetica", 11)
    c.showPage()
    c.save()
    with open(path, "rb") as f:
        return f.read()

# ========================
# TAB PRINCIPAUX
# ========================
tab_cv, tab_letter, tab_interview, tab_dashboard = st.tabs(["CV", "Lettre", "Entretien", "Dashboard"])

# ---------------- CV ----------------
with tab_cv:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Analyse de CV (ATS)</div>', unsafe_allow_html=True)
    file_cv = st.file_uploader("CV (PDF, DOCX, Image)", type=["pdf","docx","png","jpg","jpeg"])
    job_text = st.text_area("Offre de poste (copier/coller)", height=180)
    if st.button("Analyser CV"):
        if file_cv and job_text.strip():
            text, used_ocr = extract_text_from_file(file_cv)
            job_kw = build_job_keywords(job_text)
            score, breakdown = ats_score(text, job_kw)
            st.metric("Score ATS", f"{score}/100")
            st.dataframe(pd.DataFrame(breakdown.items(), columns=["Dimension","Points"]))
            for s in suggest_improvements(text, job_kw): st.markdown(f"- {s}")
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------- Lettre ----------------
with tab_letter:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Lettre de motivation</div>', unsafe_allow_html=True)
    file_letter = st.file_uploader("Lettre (PDF, DOCX, Image) ou coller le texte", type=["pdf","docx","png","jpg","jpeg"])
    letter_text_input = st.text_area("Texte de la lettre", height=220)
    job_text_cover = st.text_area("Offre (référence)", height=220)
    if st.button("Analyser la lettre"):
        letter_text = letter_text_input
        if file_letter:
            letter_text, _ = extract_text_from_file(file_letter)
        coh = min(100, int(len(set(build_job_keywords(job_text_cover)["must_have"]) & set(normalize(letter_text).split())) / 10 * 100))
        ton = tone_heuristic(letter_text)
        st.metric("Cohérence vs offre", f"{coh}/100")
        st.metric("Ton & structure", f"{ton}/100")
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------- Entretien ----------------
QUESTION_BANK = {
    "IT": {
        "QCM":[("Quel langage back-end utilisez-vous?",["Python","JavaScript","C++"],0)],
        "OPEN":["Décrivez un projet IT et votre rôle."]
    },
    "RH": {
        "QCM":[("Qu’est-ce qu’un KPI RH ?",["Indicateur clé","CV","Budget"],0)],
        "OPEN":["Décrivez une situation de gestion d’équipe."]
    },
    "Management": {"QCM":[],"OPEN":["Décrivez votre gestion de projet."]},
    "Finance": {"QCM":[],"OPEN":["Comment analysez-vous un bilan financier ?"]},
    "Marketing": {"QCM":[],"OPEN":["Exemple d’une campagne marketing réussie."]},
    "Comptabilité": {"QCM":[],"OPEN":["Comment vérifier les comptes ?"]}
}

with tab_interview:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Simulation d’entretien</div>', unsafe_allow_html=True)
    domain = st.selectbox("Domaine", list(QUESTION_BANK.keys()))
    st.button("Générer les questions", key="gen_questions")
    bank = QUESTION_BANK[domain]
    st.markdown("**QCM**")
    for i, (q, opts, ans) in enumerate(bank["QCM"],1):
        st.write(f"{i}. {q}")
        choice = st.radio("Réponse", opts, key=f"{domain}_qcm_{i}")
        if st.button(f"Vérifier {i}", key=f"chk_{domain}_{i}"):
            if opts.index(choice) == ans: st.success("✅ Correct")
            else: st.error(f"Mauvaise réponse. Bonne: {opts[ans]}")
    st.markdown("**Questions ouvertes (guide)**")
    for q in bank["OPEN"]: st.markdown(f"- {q}")
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------- Dashboard ----------------
with tab_dashboard:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Dashboard Employabilité</div>', unsafe_allow_html=True)
    st.markdown("### Répartition par domaine (exemple)")
    domaines = ["IT","RH","Management","Finance","Marketing","Comptabilité"]
    valeurs = [10,8,6,4,5,3]
    st.bar_chart(pd.DataFrame({"Domaines":domaines,"Analyses":valeurs}).set_index("Domaines"))
    st.markdown('</div>', unsafe_allow_html=True)
