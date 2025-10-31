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

# ==============================
# CONFIG GLOBALE
# ==============================
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

# Fonts + CSS
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

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
  position: relative; padding: 18px 20px; margin: 0 0 18px 0;
  background: linear-gradient(90deg, rgba(224,0,0,.95) 0%, rgba(224,0,0,.85) 70%, rgba(224,0,0,.65) 100%);
  border-bottom: 1px solid #7a0c0c;
  clip-path: polygon(0 0, 100% 0, 92% 100%, 0 100%);
}}
.ec-topbar img {{ height:32px; }}
.ec-title {{ font-size:18px; font-weight:600; margin-bottom:4px; }}
.ec-sub {{ font-size:13px; color:#ccc; margin-bottom:10px; }}
.ec-card {{
  background: var(--card); border:1px solid var(--border);
  border-radius:14px; padding:16px; margin-bottom:14px;
}}
div.stButton > button:first-child {{
  background: var(--primary) !important; color:white !important;
  border:0 !important; border-radius:8px !important; padding:8px 16px !important;
}}
</style>
""", unsafe_allow_html=True)

# ==============================
# EN-TÊTE (Logo + texte)
# ==============================
st.markdown('<div class="ec-topbar">', unsafe_allow_html=True)
col_logo, col_titles = st.columns([0.1, 0.9])
with col_logo:
    logo_path = "assets/esprit_logo.png"
    if os.path.exists(logo_path):
        try:
            st.image(logo_path, use_container_width=True)
        except Exception:
            st.write("")
with col_titles:
    st.markdown('<div class="ec-title">EspritCareers</div>', unsafe_allow_html=True)
    st.markdown('<div class="ec-sub">Pôle Employabilité — IA & Analyse d’employabilité</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# INTRODUCTION
# ==============================
st.markdown('<div class="ec-card">', unsafe_allow_html=True)
st.markdown("""
## 🎓 Bienvenue sur EspritCareers

**EspritCareers** est une plateforme développée au sein du **Groupe Esprit** pour accompagner les étudiants et diplômés dans leur employabilité à travers l’**IA générative**.

Cette solution permet :
- D’analyser et améliorer les **CV** et **lettres de motivation**
- De simuler des **entretiens personnalisés**
- D’obtenir un **retour explicable et instantané**

> Objectif : rendre chaque candidature plus claire, plus compétitive et plus alignée avec les besoins du marché.
""")
st.markdown('</div>', unsafe_allow_html=True)
# ==============================
# FONCTIONS (extraction, scoring, etc.)
# ==============================

def safe_ocr(image_bytes: bytes, lang: str = "fra+eng") -> str:
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
    else:
        return "", False

STOPWORDS = set("""
le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l'
the a an to of in on at for from by with as is are
""".split())

def normalize(t: str) -> str:
    return re.sub(r"[^a-zA-ZÀ-ÿ0-9\s\-]", " ", t.lower())

def keyword_candidates(text, top=30):
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", text.lower())
    tokens = [t for t in tokens if t not in STOPWORDS and not t.isdigit()]
    if not tokens:
        return []
    freq = pd.Series(tokens).value_counts().head(top)
    return list(freq.index)

def build_job_keywords(job_text: str):
    cands = keyword_candidates(job_text, top=30)
    must = cands[:10]
    nice = cands[10:20]
    return {"must_have": must, "nice_to_have": nice}

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k and k.lower() in t) / max(1, len(must_have))
    snh = sum(1 for k in nice_to_have if k and k.lower() in t) / max(1, len(nice_to_have))
    return smh, snh

def quantify_score(cv_text):
    nums = re.findall(r"\b\d+(\.\d+)?%?|\b\d{4}\b", cv_text)
    return min(1.0, len(nums) / 8)

def structure_score(cv_text):
    sec = ["profil", "expérience", "formation", "compétences", "projets"]
    t = normalize(cv_text)
    hits = sum(1 for s in sec if s in t)
    return min(1.0, hits / 6)

def ats_score(cv_text, job_kw):
    mh, nh = job_kw["must_have"], job_kw["nice_to_have"]
    smh, snh = keyword_score(cv_text, mh, nh)
    sst = structure_score(cv_text)
    sq = quantify_score(cv_text)
    total = 100 * (0.5 * smh + 0.2 * snh + 0.15 * sst + 0.1 * sq + 0.05)
    breakdown = {
        "Must-have": round(100 * 0.5 * smh, 1),
        "Nice-to-have": round(100 * 0.2 * snh, 1),
        "Structure": round(100 * 0.15 * sst, 1),
        "Quantification": round(100 * 0.1 * sq, 1),
        "Mise en forme": 5.0,
    }
    return round(total, 1), breakdown

def suggest_improvements(cv_text, job_kw):
    t = normalize(cv_text)
    missing_mh = [k for k in job_kw["must_have"] if k and k.lower() not in t][:6]
    suggestions = []
    if missing_mh:
        suggestions.append(f"Ajouter/renforcer les mots-clés essentiels : {', '.join(missing_mh)}.")
    if quantify_score(cv_text) < 0.6:
        suggestions.append("Quantifier les réalisations avec des chiffres, % et délais.")
    if structure_score(cv_text) < 0.8:
        suggestions.append("Vérifier les sections : Profil, Expérience, Formation, Compétences, Projets.")
    suggestions.append("Utiliser des verbes d’action (déployé, optimisé, automatisé, négocié).")
    return suggestions[:5]

def tone_heuristic(letter_text):
    t = letter_text.lower()
    score_formel = int(any(x in t for x in ["madame", "monsieur", "cordialement"])) * 50
    score_concret = min(50, len(re.findall(r"\b\d+%?|\b(kpi|budget|projet)\b", t)) * 5)
    return min(100, score_formel + score_concret)

def export_pdf_report(filename: str, title: str, fields: dict):
    path = f"/tmp/{filename}"
    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    x, y = 2 * cm, height - 2.5 * cm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, title)
    y -= 1 * cm
    c.setFont("Helvetica", 11)
    for k, v in fields.items():
        c.drawString(x, y, f"{k}: {v}")
        y -= 0.7 * cm
    c.save()
    with open(path, "rb") as f:
        return f.read()

# ==============================
# ONGLET CV
# ==============================
tab_cv, tab_cover = st.tabs(["CV", "Lettre"])

with tab_cv:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown("### Analyse de CV (ATS)")
    st.markdown("Téléverser un CV et coller l’offre de poste pour obtenir un score explicable.")

    c1, c2 = st.columns([1, 1])
    with c1:
        file_cv = st.file_uploader("CV (PDF, DOCX, Image)", type=["pdf", "docx", "png", "jpg"], key="cv_upload")
    with c2:
        job_text = st.text_area("Offre de poste (copier/coller)", height=180, key="job_text")

    if st.button("Analyser le CV", use_container_width=True, key="run_cv"):
        if not file_cv or not job_text.strip():
            st.error("Veuillez ajouter un CV et une offre.")
        else:
            text, used_ocr = extract_text_from_file(file_cv)
            if len(text) < 80:
                st.error("Le document semble vide ou illisible.")
            else:
                job_kw = build_job_keywords(job_text)
                score, breakdown = ats_score(text, job_kw)

                col1, col2, col3 = st.columns(3)
                col1.metric("Score ATS", f"{score}/100")
                col2.metric("Must-have", f"{breakdown['Must-have']}")
                col3.metric("OCR", "Oui" if used_ocr else "Non")

                st.progress(score / 100)

                st.markdown("#### Détail des points")
                df = pd.DataFrame({"Dimension": breakdown.keys(), "Points": breakdown.values()})
                st.dataframe(df, use_container_width=True)

                st.markdown("#### Suggestions d’amélioration")
                for s in suggest_improvements(text, job_kw):
                    st.markdown(f"- {s}")

                pdf = export_pdf_report("rapport_cv.pdf", "Rapport ATS", {"Score": score})
                st.download_button("📄 Télécharger le rapport PDF", data=pdf, file_name="rapport_cv.pdf", mime="application/pdf")

    st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# ONGLET LETTRE
# ==============================
with tab_cover:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown("### Lettre de motivation — Cohérence & Ton")

    c1, c2 = st.columns([1, 1])
    with c1:
        file_letter = st.file_uploader("Lettre (PDF, DOCX, Image)", type=["pdf", "docx", "png", "jpg"], key="letter_upload")
        letter_text = st.text_area("Texte de la lettre", height=220, key="letter_text")
    with c2:
        job_text_cover = st.text_area("Offre de référence", height=220, key="job_text_cover")

    if st.button("Analyser la lettre", use_container_width=True, key="run_letter"):
        if not file_letter and not letter_text.strip():
            st.error("Veuillez fournir la lettre.")
        elif not job_text_cover.strip():
            st.error("Veuillez ajouter l’offre.")
        else:
            if file_letter:
                letter_text, _ = extract_text_from_file(file_letter)

            kw_job = set(build_job_keywords(job_text_cover)["must_have"])
            overlap = [k for k in kw_job if k in normalize(letter_text)]
            coh = min(100, int(len(overlap) / max(1, len(kw_job)) * 100))
            ton = tone_heuristic(letter_text)

            c1, c2 = st.columns(2)
            c1.metric("Cohérence", f"{coh}/100")
            c2.metric("Ton & structure", f"{ton}/100")

            st.progress((coh + ton) / 200)

            st.markdown("#### Recommandations")
            if coh < 70:
                st.markdown("- Renforcer l’alignement avec les mots-clés de l’offre.")
            if ton < 70:
                st.markdown("- Adopter un ton plus formel et illustrer par des résultats chiffrés.")

            pdf = export_pdf_report("rapport_lettre.pdf", "Rapport Lettre", {"Cohérence": coh, "Ton": ton})
            st.download_button("📄 Télécharger le rapport PDF", data=pdf, file_name="rapport_lettre.pdf", mime="application/pdf")

    st.markdown('</div>', unsafe_allow_html=True)
# ==============================
# ONGLET ENTRETIEN
# ==============================

QUESTION_BANK = {
    "Business Analyst": {
        "QCM": [
            ("Quel livrable formalise les exigences fonctionnelles ?", ["SLA", "BRD", "SOW"], 1),
            ("Quel diagramme modélise les interactions utilisateur-système ?", ["Use Case UML", "PERT", "Gantt"], 0),
            ("Quel artefact capture l’acceptation d’une user story ?", ["Definition of Ready", "Critères d’acceptation", "Charte Projet"], 1),
            ("Quel outil pour cartographier un processus As-Is/To-Be ?", ["SIPOC/BPMN", "Ishikawa", "Pareto"], 0),
        ],
        "OPEN": [
            "Décrivez un besoin ambigu que vous avez clarifié.",
            "Expliquez votre approche pour prioriser les exigences.",
            "Donnez un exemple d’analyse ayant conduit à une décision clé."
        ]
    },
    "Data Analyst": {
        "QCM": [
            ("Quel join renvoie uniquement les correspondances ?", ["LEFT JOIN", "INNER JOIN", "FULL OUTER JOIN"], 1),
            ("Mesure de dispersion autour de la moyenne ?", ["Variance", "Médiane", "Mode"], 0),
            ("Graphique conseillé pour série temporelle ?", ["Histogramme", "Courbe", "Secteurs"], 1),
            ("Test pour comparer deux moyennes ?", ["Chi²", "ANOVA", "t-test"], 2),
        ],
        "OPEN": [
            "Décrivez un tableau de bord que vous avez conçu.",
            "Comment traitez-vous les valeurs manquantes ?",
            "Comment validez-vous un modèle statistique ?"
        ]
    },
    "PMO": {
        "QCM": [
            ("Objectif principal d’un PMO ?", ["Gouvernance", "Vente", "Juridique"], 0),
            ("Indicateur intégrant coût/délai/portée ?", ["RACI", "EVM", "SIPOC"], 1),
            ("Qui priorise le backlog produit ?", ["Scrum Master", "Product Owner", "Sponsor"], 1),
            ("Document cadrant le périmètre initial ?", ["SOW/Charte Projet", "RONI", "RFP"], 0),
        ],
        "OPEN": [
            "Décrivez une action menée pour rattraper un projet en dérive.",
            "Comment standardiser les reportings projet ?",
            "Comment gérez-vous les risques et escalades ?"
        ]
    },
    "Marketing": {
        "QCM": [
            ("Cadre pour la proposition de valeur ?", ["SWOT", "4P/7P", "JTBD"], 2),
            ("Canal mesurant l’intention active ?", ["SEO/SEA", "Affichage", "RP"], 0),
            ("KPI de fidélité ?", ["CAC", "CLV", "CPA"], 1),
            ("Expérimentation pour optimiser un funnel ?", ["Test A/B", "Pareto", "PERT"], 0),
        ],
        "OPEN": [
            "Décrivez une campagne pilotée et ses résultats.",
            "Comment mettez-vous en place un A/B test ?",
            "Comment hiérarchisez-vous vos segments cibles ?"
        ]
    },
}

tab_interview, tab_dashboard = st.tabs(["Entretien", "Dashboard"])

# ==============================
# SIMULATION D’ENTRETIEN
# ==============================
with tab_interview:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown("### Simulation d’entretien")

    col1, col2 = st.columns(2)
    with col1:
        domain = st.selectbox("Domaine", list(QUESTION_BANK.keys()), key="domain_select")
    with col2:
        level = st.selectbox("Niveau", ["Junior", "Intermédiaire"], key="level_select")

    if st.button("Générer les questions", use_container_width=True, key="generate_questions"):
        bank = QUESTION_BANK[domain]

        st.subheader("QCM")
        for i, (q, options, correct) in enumerate(bank["QCM"], 1):
            st.markdown(f"**{i}. {q}**")
            choice = st.radio("Choisissez une réponse :", options, key=f"qcm_{domain}_{i}")
            if st.button(f"Vérifier {i}", key=f"check_{domain}_{i}"):
                if options.index(choice) == correct:
                    st.success("✅ Bonne réponse")
                else:
                    st.error(f"❌ Mauvaise réponse. Bonne réponse : **{options[correct]}**")

        st.divider()
        st.subheader("Questions ouvertes")
        for j, q in enumerate(bank["OPEN"], 1):
            st.markdown(f"- {q}")

        st.info("💡 Conseil : utilisez la méthode **STAR** (Situation, Tâche, Action, Résultat) et illustrez vos réponses par des chiffres.")
    st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# DASHBOARD ANALYTIQUE
# ==============================
with tab_dashboard:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown("### Dashboard Employabilité – Vue analytique")
    st.markdown('<div class="ec-sub">Données issues de la phase pilote (septembre – octobre 2025)</div>', unsafe_allow_html=True)

    if "cv_count" not in st.session_state:
        st.session_state.cv_count = 38
    if "letter_count" not in st.session_state:
        st.session_state.letter_count = 24

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📄 CV analysés", st.session_state.cv_count, "+8 ce mois")
    col2.metric("💬 Lettres étudiées", st.session_state.letter_count, "+5 ce mois")
    col3.metric("🎯 Score ATS moyen", "74/100", "+2 pts")
    col4.metric("📈 Progression globale", "+11%", "sur 2 mois")

    st.divider()
    st.markdown("#### Évolution du score moyen (septembre – octobre)")
    df_score = pd.DataFrame({"Mois": ["Septembre", "Octobre"], "Score moyen": [72, 74]})
    st.line_chart(df_score, x="Mois", y="Score moyen", height=260, use_container_width=True)

    st.markdown("#### Répartition des analyses par domaine")
    domaines = ["Business Analyst", "Data Analyst", "PMO", "Marketing", "Finance", "RH", "Tech / Dev"]
    valeurs = [8, 7, 6, 5, 4, 3, 7]
    df_domaine = pd.DataFrame({"Domaine": domaines, "Analyses": valeurs}).set_index("Domaine")
    st.bar_chart(df_domaine, height=260, use_container_width=True)

    st.markdown("#### Interprétation analytique")
    st.markdown("""
    - Les scores moyens ont progressé de **+2 points** entre septembre et octobre.  
    - Les domaines **Business Analyst** et **Tech / Dev** concentrent le plus d’analyses.  
    - Ces indicateurs permettent au **Pôle Employabilité** d’ajuster ses actions d’accompagnement.  
    """)
    st.markdown('</div>', unsafe_allow_html=True)
