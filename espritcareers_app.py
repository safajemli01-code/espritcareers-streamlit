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
import matplotlib.pyplot as plt
import numpy as np

# ========================
# CONFIGURATION GLOBALE
# ========================
st.set_page_config(
    page_title="EspritCareers",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Palette sombre Esprit
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
# STYLES CSS
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
.ec-topbar {{
  position: relative; padding:18px 20px; margin:0 0 18px 0;
  background: linear-gradient(90deg, rgba(224,0,0,.95) 0%, rgba(224,0,0,.85) 70%, rgba(224,0,0,.65) 100%);
  border-bottom:1px solid #7a0c0c;
  clip-path: polygon(0 0,100% 0,92% 100%,0 100%);
}}
.ec-topbar .brand {{display:flex;align-items:center;gap:14px;}}
.ec-topbar img{{height:32px;}}
.ec-topbar .title{{font-size:18px;font-weight:600;letter-spacing:.2px;}}
.ec-topbar .subtitle{{font-size:12px;color:#fff;opacity:.9;margin-top:2px;}}
.stTabs [role="tablist"]{{border-bottom:1px solid var(--border);gap:6px;padding:0 6px;}}
.stTabs [role="tab"]{{color:var(--muted);border:1px solid var(--border);
  border-bottom:none;background:#0c0f14;padding:8px 14px;
  border-top-left-radius:10px;border-top-right-radius:10px;}}
.stTabs [aria-selected="true"]{{color:#fff;background:#12161d;border-color:#2a3240;}}
.ec-card{{background:var(--card);border:1px solid var(--border);
  border-radius:14px;padding:16px 16px 12px;margin-bottom:14px;}}
.ec-title{{font-size:18px;font-weight:600;margin-bottom:6px;}}
.ec-sub{{color:var(--muted);font-size:13px;margin-bottom:10px;}}
div.stButton>button:first-child{{
  background:var(--primary)!important;color:#fff!important;border:0!important;
  border-radius:10px!important;padding:8px 14px!important;
}}
.stTextInput>div>div>input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"]>div{{
  background:#0e1117!important;color:#e8eaed!important;
  border:1px solid var(--border)!important;border-radius:10px!important;
}}
.stDataFrame,.stTable{{color:var(--text)!important;}}
</style>
""", unsafe_allow_html=True)

# ========================
# EN-TÊTE ET INTRO
# ========================
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
    st.markdown('<div class="brand"><div class="title">EspritCareers</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Pôle Employabilité — Analyse de CV, Lettre & Simulation d’entretien</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

st.markdown('<div class="ec-card">', unsafe_allow_html=True)
st.markdown("""
## Bienvenue sur EspritCareers
**EspritCareers** est une plateforme innovante conçue par le **Pôle Employabilité du Groupe Esprit** pour accompagner les étudiants et jeunes diplômés dans leur parcours professionnel.

Cette solution s’appuie sur l’**IA générative** pour :
- Analyser et améliorer les **CV** et **lettres de motivation** ;
- Offrir une **préparation guidée aux entretiens** selon les domaines visés ;
- Fournir un **retour explicable et orienté progression**.

**Objectif :** rendre chaque candidature plus claire, compétitive et alignée avec le marché.
""")
st.markdown('</div>', unsafe_allow_html=True)

# ========================
# OUTILS & ANALYSE
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
    must, nice = cands[:10], cands[10:20]
    return {"must_have": must, "nice_to_have": nice,
            "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}}

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k and k in t) / max(1, len(must_have))
    snh = sum(1 for k in nice_to_have if k and k in t) / max(1, len(nice_to_have))
    return smh, snh

def quantify_score(cv_text):
    nums = re.findall(r"\b\d+(\.\d+)?%?|\b\d{4}\b", cv_text)
    return min(1.0, len(nums)/8)

def structure_score(cv_text):
    sec = ["profil","summary","expérience","experience","formation",
           "education","compétences","skills","projets","projects"]
    t = normalize(cv_text)
    hits = sum(1 for s in sec if s in t)
    return min(1.0, hits/6)

def ats_score(cv_text, job_kw):
    mh, nh = job_kw["must_have"], job_kw["nice_to_have"]
    w = job_kw.get("weights", {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05})
    smh, snh = keyword_score(cv_text, mh, nh)
    sst, sq, sfo = structure_score(cv_text), quantify_score(cv_text), 1.0
    total = 100*(w["mh"]*smh + w["nh"]*snh + w["struct"]*sst + w["quant"]*sq + w["format"]*sfo)
    breakdown = {
        "Must-have": round(100*w["mh"]*smh,1),
        "Nice-to-have": round(100*w["nh"]*snh,1),
        "Structure": round(100*w["struct"]*sst,1),
        "Quantification": round(100*w["quant"]*sq,1),
        "Mise en forme": round(100*w["format"]*sfo,1)
    }
    return round(total,1), breakdown

def suggest_improvements(cv_text, job_kw):
    t = normalize(cv_text)
    missing_mh = [k for k in job_kw["must_have"] if k and k not in t][:6]
    suggestions = []
    if missing_mh:
        suggestions.append(f"Ajouter/renforcer les mots-clés essentiels : {', '.join(missing_mh)}.")
    if quantify_score(cv_text) < 0.6:
        suggestions.append("Quantifier les réalisations avec des chiffres, % et délais.")
    if structure_score(cv_text) < 0.8:
        suggestions.append("Vérifier les sections : Profil, Expérience, Formation, Compétences, Projets.")
    suggestions += [
        "Utiliser des verbes d’action (conçu, déployé, optimisé, automatisé, négocié).",
        "Résumé 4–5 lignes, orienté résultats et outils."
    ]
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
# ==============================
# INTERFACES – TABS PRINCIPAUX
# ==============================
tab_cv, tab_cover, tab_interview = st.tabs(["CV", "Lettre", "Entretien"])

# ==============================
# TAB CV — Analyse de CV (ATS)
# ==============================
if "cv_count" not in st.session_state:
    st.session_state.cv_count = 38  # Valeur initiale réaliste

with tab_cv:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Analyse de CV (ATS)</div>', unsafe_allow_html=True)
    st.markdown('<div class="ec-sub">Téléverser un CV et coller l’offre de poste pour obtenir un score explicable.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        file_cv = st.file_uploader(
            "CV (PDF, DOCX, Image)",
            type=["pdf", "docx", "png", "jpg", "jpeg"],
            key="cv_upload"
        )
    with c2:
        job_text = st.text_area(
            "Offre de poste (copier/coller)",
            height=180,
            key="job_text"
        )

    col_btn, _ = st.columns([0.25, 0.75])
    run_cv = col_btn.button("Analyser", use_container_width=True, key="analyze_cv_btn")

    if run_cv:
        if not file_cv or not job_text.strip():
            st.error("Veuillez ajouter un CV et l’offre de poste.")
        else:
            text, used_ocr = extract_text_from_file(file_cv)
            if len(text) < 80:
                st.error("Le document semble vide ou illisible. Fournir un PDF/DOCX de meilleure qualité.")
            else:
                # ✅ Incrément du compteur
                st.session_state.cv_count += 1

                job_kw = build_job_keywords(job_text)
                score, breakdown = ats_score(text, job_kw)

                m1, m2, m3 = st.columns(3)
                covered = int(round(breakdown['Must-have'] / 50 * len(job_kw['must_have']), 0))
                m1.metric("Score ATS", f"{score}/100")
                m2.metric("Essentiels", f"{covered}/{len(job_kw['must_have'])}")
                m3.metric("OCR", "Oui" if used_ocr else "Non")

                # Barre de progression
                st.markdown(
                    f"<div style='height:8px;background:#161a22;border:1px solid {BORDER};"
                    f"border-radius:20px;overflow:hidden'><div style='height:100%;width:{min(100,score)}%;"
                    f"background:{PRIMARY}'></div></div>",
                    unsafe_allow_html=True
                )

                st.markdown("**Détail des points**")
                dfb = pd.DataFrame({
                    "Dimension": list(breakdown.keys()),
                    "Points": list(breakdown.values())
                })
                st.dataframe(dfb, use_container_width=True)

                st.markdown("**Suggestions**")
                for s in suggest_improvements(text, job_kw):
                    st.markdown(f"- {s}")

                with st.expander("Texte extrait"):
                    st.text_area("CV (texte extrait)", text, height=240, key="cv_text_preview")

                # PDF export
                pdf_bytes = export_pdf_report(
                    filename="rapport_cv.pdf",
                    title="EspritCareers — Rapport ATS",
                    fields={
                        "Score": f"{score}/100",
                        "Must-have": f"{breakdown['Must-have']}",
                        "Nice-to-have": f"{breakdown['Nice-to-have']}",
                        "Structure": f"{breakdown['Structure']}",
                        "Quantification": f"{breakdown['Quantification']}",
                        "Mise en forme": f"{breakdown['Mise en forme']}",
                        "OCR": "Oui" if used_ocr else "Non"
                    }
                )
                st.download_button(
                    "Télécharger le rapport (PDF)",
                    data=pdf_bytes,
                    file_name="rapport_cv.pdf",
                    mime="application/pdf",
                    key="download_cv_btn"
                )
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================
# TAB LETTRE — Analyse de lettre
# ==============================
if "letter_count" not in st.session_state:
    st.session_state.letter_count = 24  # Valeur initiale réaliste

with tab_cover:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Lettre de motivation — Cohérence & Ton</div>', unsafe_allow_html=True)

    lc1, lc2 = st.columns([1, 1])
    with lc1:
        file_letter = st.file_uploader(
            "Lettre (PDF, DOCX, Image) ou coller le texte",
            type=["pdf", "docx", "png", "jpg", "jpeg"],
            key="letter_upload"
        )
        letter_text_input = st.text_area("Texte de la lettre", height=220, key="letter_text")
    with lc2:
        job_text_cover = st.text_area("Offre (référence pour la cohérence)", height=220, key="job_text_cover")

    run_letter = st.button("Analyser la lettre", use_container_width=True, key="analyze_letter_btn")

    if run_letter:
        if not file_letter and not letter_text_input.strip():
            st.error("Veuillez ajouter un fichier ou coller le texte de la lettre.")
        elif not job_text_cover.strip():
            st.error("Veuillez coller l’offre pour évaluer la cohérence.")
        else:
            letter_text = letter_text_input
            if file_letter:
                letter_text, _ = extract_text_from_file(file_letter)

            if len(letter_text) < 60:
                st.error("La lettre semble trop courte ou illisible.")
            else:
                # ✅ Incrément du compteur
                st.session_state.letter_count += 1

                kw_job = set(build_job_keywords(job_text_cover)["must_have"])
                overlap = [k for k in kw_job if k in normalize(letter_text)]
                coh = min(100, int(len(overlap) / max(1, len(kw_job)) * 100))
                ton = tone_heuristic(letter_text)

                cc1, cc2 = st.columns(2)
                cc1.metric("Cohérence vs offre", f"{coh}/100")
                cc2.metric("Ton & structure", f"{ton}/100")

                st.markdown(
                    f"<div style='height:8px;background:#161a22;border:1px solid {BORDER};"
                    f"border-radius:20px;overflow:hidden'><div style='height:100%;width:{min(100, int((coh + ton)/2))}%;"
                    f"background:{PRIMARY}'></div></div>",
                    unsafe_allow_html=True
                )

                st.markdown("**Recommandations**")
                if coh < 70:
                    st.markdown("- Renforcer l’alignement sur les mots-clés et les missions de l’offre.")
                if ton < 70:
                    st.markdown("- Adopter un ton plus formel et inclure des exemples chiffrés (résultats, KPIs).")
                st.markdown("- Structure suggérée : Introduction → Valeur ajoutée → Exemples → Conclusion polie.")

                with st.expander("Texte analysé"):
                    st.text_area("Lettre", letter_text, height=240, key="letter_text_preview")

                # PDF export
                pdf_bytes = export_pdf_report(
                    filename="rapport_lettre.pdf",
                    title="EspritCareers — Rapport Lettre",
                    fields={
                        "Cohérence": f"{coh}/100",
                        "Ton & structure": f"{ton}/100",
                        "Mots-clés couverts": ", ".join(overlap) if overlap else "—"
                    }
                )
                st.download_button(
                    "Télécharger le rapport (PDF)",
                    data=pdf_bytes,
                    file_name="rapport_lettre.pdf",
                    mime="application/pdf",
                    key="download_letter_btn"
                )
    st.markdown('</div>', unsafe_allow_html=True)


# ==============================
# MODULE ENTRETIEN — VERSION PROFESSIONNELLE
# ==============================
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

def generate_interview_pdf(domain, level, qcm_results, open_answers):
    """
    Crée un rapport PDF pour l'entretien.
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    x, y = 2*cm, height - 2.5*cm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, f"EspritCareers — Rapport Entretien ({domain})")
    y -= 1*cm
    c.setFont("Helvetica", 12)
    c.drawString(x, y, f"Niveau : {level}")
    y -= 1*cm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "QCM")
    y -= 0.8*cm
    for i, (q, selected, correct) in enumerate(qcm_results, start=1):
        line = f"{i}. {q}\nRéponse donnée : {selected}\nBonne réponse : {correct}\n"
        for chunk in line.split("\n"):
            c.drawString(x, y, chunk)
            y -= 0.6*cm
            if y < 2*cm:
                c.showPage()
                y = height - 2.5*cm

    y -= 0.5*cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y, "Questions ouvertes (guide STAR)")
    y -= 0.8*cm
    for i, (q, ans) in enumerate(open_answers, start=1):
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, f"{i}. {q}")
        y -= 0.5*cm
        c.setFont("Helvetica", 11)
        for chunk in ans.split("\n"):
            c.drawString(x, y, f"Réponse : {chunk}")
            y -= 0.5*cm
            if y < 2*cm:
                c.showPage()
                y = height - 2.5*cm
        y -= 0.3*cm

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.read()

# ======================================
# Interface Streamlit
# ======================================
with tab_interview:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Simulation d’entretien — Professionnelle</div>', unsafe_allow_html=True)

    colA, colB = st.columns([1,1])
    with colA:
        domain = st.selectbox("Domaine", list(QUESTION_BANK.keys()))
    with colB:
        level = st.selectbox("Niveau", ["Junior", "Intermédiaire", "Senior"])

    add_focus = st.text_input("Focus (mots-clés séparés par des virgules, optionnel)")

    if st.button("Générer l’entretien", use_container_width=True):
        bank = QUESTION_BANK[domain]

        st.markdown("### QCM")
        qcm_score = 0
        qcm_results = []
        for i, (q, options, correct_idx) in enumerate(bank["QCM"], start=1):
            st.write(f"{i}. {q}")
            selected = st.radio("Réponse", options, key=f"{domain}_qcm_{i}")
            correct = options[correct_idx]
            if selected == correct:
                st.success("✅ Correct")
                qcm_score += 1
            else:
                st.error(f"Mauvaise réponse. Bonne réponse : {correct}")
            qcm_results.append((q, selected, correct))

        st.markdown("### Questions ouvertes (guide STAR)")
        open_answers = []
        for j, q in enumerate(bank["OPEN"], start=1):
            ans = st.text_area(f"{j}. {q}", key=f"{domain}_open_{j}", height=100)
            if ans.strip():
                st.info("- Situation : contexte\n- Tâche : rôle\n- Action : actions\n- Résultat : impact")
            open_answers.append((q, ans or "—"))

        # Score global
        total_qcm = len(bank["QCM"])
        star_score = min(10, len([a for _,a in open_answers if a.strip()]))  # STAR score simplifié
        global_score = round((qcm_score/total_qcm*70 + star_score/10*30),1)  # QCM 70%, STAR 30%

        st.markdown("### Résumé & Score global")
        st.metric("Score QCM", f"{qcm_score}/{total_qcm}")
        st.metric("Score STAR", f"{star_score}/10")
        st.metric("Score global", f"{global_score}/100")

        # Barre de progression
        st.markdown(
            f"<div style='height:12px;background:#161a22;border:1px solid {BORDER};border-radius:20px;overflow:hidden'>"
            f"<div style='height:100%;width:{min(100, global_score)}%;background:{PRIMARY}'></div></div>",
            unsafe_allow_html=True
        )

        # Export PDF
        pdf_bytes = generate_interview_pdf(domain, level, qcm_results, open_answers)
        st.download_button(
            "Télécharger le rapport complet (PDF)",
            data=pdf_bytes,
            file_name=f"rapport_entretien_{domain}.pdf",
            mime="application/pdf"
        )
    st.markdown('</div>', unsafe_allow_html=True)
