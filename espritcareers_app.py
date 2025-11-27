# app.py
import streamlit as st
import os, io, re
import pandas as pd
from PIL import Image
import pytesseract
import fitz  # PyMuPDF
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

# ========================
# CONFIGURATION GLOBALE
# ========================
st.set_page_config(
    page_title="EspritCareers",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Couleurs et CSS
PRIMARY = "#E00000"
BG = "#0B0C10"
CARD = "#0F1115"
BORDER = "#1F2937"
TEXT = "#E8EAED"
MUTED = "#A1A7B0"

st.markdown(f"""
<style>
:root {{
  --primary:{PRIMARY}; --bg:{BG}; --card:{CARD}; --border:{BORDER}; --text:{TEXT}; --muted:{MUTED};
}}
html, body, [class*="css"] {{ background: var(--bg); color: var(--text); font-family: Inter, sans-serif; }}
.ec-card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:16px;margin-bottom:14px;}}
.ec-title{{font-size:18px;font-weight:600;margin-bottom:6px;}}
.ec-sub{{color:var(--muted);font-size:13px;margin-bottom:10px;}}
div.stButton>button{{background:var(--primary);color:#fff;border-radius:10px;padding:8px 14px;}}
</style>
""", unsafe_allow_html=True)

# ========================
# OUTILS UTILITAIRES
# ========================
STOPWORDS = set("le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l' the a an to of in on at for from by with as is are".split())

def normalize(text: str) -> str:
    return re.sub(r"[^a-zA-ZÀ-ÿ0-9\s\-]", " ", text.lower())

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
        text_total, used_ocr = "", False
        for page in doc:
            t = page.get_text().strip()
            if not t:
                try:
                    pix = page.get_pixmap(dpi=300)
                    t = safe_ocr(pix.tobytes())
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
        return t.strip(), bool(t)
    return "", False

def keyword_candidates(text, top=30):
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", text.lower())
    tokens = [t for t in tokens if t not in STOPWORDS and not t.isdigit()]
    freq = pd.Series(tokens).value_counts().head(top)
    return list(freq.index)

def build_job_keywords(job_text: str):
    cands = keyword_candidates(job_text, top=30)
    return {"must_have": cands[:10], "nice_to_have": cands[10:20],
            "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}}

def quantify_score(cv_text):
    nums = re.findall(r"\b\d+(\.\d+)?%?|\b\d{4}\b", cv_text)
    return min(1.0, len(nums)/8)

def structure_score(cv_text):
    sec = ["profil","summary","expérience","experience","formation","education","compétences","skills","projets","projects"]
    t = normalize(cv_text)
    hits = sum(1 for s in sec if s in t)
    return min(1.0, hits/6)

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k and k in t)/max(1,len(must_have))
    snh = sum(1 for k in nice_to_have if k and k in t)/max(1,len(nice_to_have))
    return smh, snh

def ats_score(cv_text, job_kw):
    smh, snh = keyword_score(cv_text, job_kw["must_have"], job_kw["nice_to_have"])
    sst, sq, sfo = structure_score(cv_text), quantify_score(cv_text), 1.0
    w = job_kw.get("weights")
    total = 100*(w["mh"]*smh + w["nh"]*snh + w["struct"]*sst + w["quant"]*sq + w["format"]*sfo)
    breakdown = {"Must-have": round(100*w["mh"]*smh,1), "Nice-to-have": round(100*w["nh"]*snh,1),
                 "Structure": round(100*w["struct"]*sst,1), "Quantification": round(100*w["quant"]*sq,1),
                 "Mise en forme": round(100*w["format"]*sfo,1)}
    return round(total,1), breakdown

def tone_heuristic(letter_text):
    t = letter_text.lower()
    score_formel = int(any(x in t for x in ["madame","monsieur","candidature","motivation","cordialement"])) * 50
    score_concret = min(50,len(re.findall(r"\b\d+%?|\b(kpi|roi|budget|projet|deadline)\b",t))*5)
    return min(100,score_formel+score_concret)
# ==============================
# INTERFACE – TABS PRINCIPAUX
# ==============================
tab_cv, tab_cover, tab_interview = st.tabs(["CV", "Lettre", "Entretien"])

# ==============================
# TAB CV — Analyse de CV (ATS)
# ==============================
if "cv_count" not in st.session_state:
    st.session_state.cv_count = 38  # valeur réaliste

with tab_cv:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Analyse de CV (ATS)</div>', unsafe_allow_html=True)
    st.markdown('<div class="ec-sub">Téléversez un CV et collez l’offre de poste pour obtenir un score explicable.</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        file_cv = st.file_uploader("CV (PDF, DOCX, Image)", type=["pdf","docx","png","jpg","jpeg"], key="cv_upload")
    with c2:
        job_text = st.text_area("Offre de poste (copier/coller)", height=180, key="job_text")

    run_cv = st.button("Analyser", use_container_width=True, key="analyze_cv_btn")
    if run_cv:
        if not file_cv or not job_text.strip():
            st.error("Veuillez ajouter un CV et l’offre de poste.")
        else:
            text, used_ocr = extract_text_from_file(file_cv)
            if len(text) < 80:
                st.error("Le document semble vide ou illisible.")
            else:
                st.session_state.cv_count += 1
                job_kw = build_job_keywords(job_text)
                score, breakdown = ats_score(text, job_kw)

                m1, m2, m3 = st.columns(3)
                covered = int(round(breakdown['Must-have']/50*len(job_kw['must_have']),0))
                m1.metric("Score ATS", f"{score}/100")
                m2.metric("Essentiels", f"{covered}/{len(job_kw['must_have'])}")
                m3.metric("OCR", "Oui" if used_ocr else "Non")

                st.markdown(
                    f"<div style='height:8px;background:#161a22;border:1px solid {BORDER};"
                    f"border-radius:20px;overflow:hidden'><div style='height:100%;width:{min(100,score)}%;"
                    f"background:{PRIMARY}'></div></div>",
                    unsafe_allow_html=True
                )

                st.markdown("**Détail des points**")
                dfb = pd.DataFrame({"Dimension":list(breakdown.keys()),"Points":list(breakdown.values())})
                st.dataframe(dfb, use_container_width=True)

                st.markdown("**Suggestions**")
                missing_mh = [k for k in job_kw["must_have"] if k and k not in normalize(text)][:6]
                suggestions = []
                if missing_mh:
                    suggestions.append(f"Ajouter/renforcer les mots-clés essentiels : {', '.join(missing_mh)}.")
                if quantify_score(text) < 0.6:
                    suggestions.append("Quantifier les réalisations avec des chiffres, % et délais.")
                if structure_score(text) < 0.8:
                    suggestions.append("Vérifier les sections : Profil, Expérience, Formation, Compétences, Projets.")
                suggestions += ["Utiliser des verbes d’action (conçu, déployé, optimisé, automatisé, négocié).","Résumé 4–5 lignes, orienté résultats et outils."]
                for s in suggestions[:5]:
                    st.markdown(f"- {s}")

                with st.expander("Texte extrait"):
                    st.text_area("CV (texte extrait)", text, height=240, key="cv_text_preview")

                # PDF export
                def export_pdf_report(filename, title, fields):
                    path = f"/tmp/{filename}"
                    c = canvas.Canvas(path, pagesize=A4)
                    width, height = A4
                    x, y = 2*cm, height-2.5*cm
                    c.setTitle(title)
                    c.setFont("Helvetica-Bold",16)
                    c.drawString(x,y,title)
                    y -= 1*cm
                    c.setFont("Helvetica",11)
                    for k,v in fields.items():
                        line = f"{k}: {v}"
                        for chunk in [line[i:i+95] for i in range(0,len(line),95)]:
                            c.drawString(x,y,chunk)
                            y -= 0.7*cm
                            if y<2*cm:
                                c.showPage()
                                y = height-2.5*cm
                                c.setFont("Helvetica",11)
                    c.showPage()
                    c.save()
                    with open(path,"rb") as f:
                        return f.read()

                pdf_bytes = export_pdf_report(
                    filename="rapport_cv.pdf",
                    title="EspritCareers — Rapport ATS",
                    fields={k:str(v) for k,v in breakdown.items()}
                )
                st.download_button("Télécharger le rapport (PDF)", data=pdf_bytes, file_name="rapport_cv.pdf", mime="application/pdf", key="download_cv_btn")
    st.markdown('</div>', unsafe_allow_html=True)

# ==============================
# TAB LETTRE — Analyse de lettre
# ==============================
if "letter_count" not in st.session_state:
    st.session_state.letter_count = 24

with tab_cover:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Lettre de motivation — Cohérence & Ton</div>', unsafe_allow_html=True)

    lc1, lc2 = st.columns([1,1])
    with lc1:
        file_letter = st.file_uploader("Lettre (PDF, DOCX, Image) ou coller le texte", type=["pdf","docx","png","jpg","jpeg"], key="letter_upload")
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
                st.session_state.letter_count += 1
                kw_job = set(build_job_keywords(job_text_cover)["must_have"])
                overlap = [k for k in kw_job if k in normalize(letter_text)]
                coh = min(100, int(len(overlap)/max(1,len(kw_job))*100))
                ton = tone_heuristic(letter_text)

                cc1, cc2 = st.columns(2)
                cc1.metric("Cohérence vs offre", f"{coh}/100")
                cc2.metric("Ton & structure", f"{ton}/100")

                st.markdown(
                    f"<div style='height:8px;background:#161a22;border:1px solid {BORDER};border-radius:20px;overflow:hidden'>"
                    f"<div style='height:100%;width:{min(100,int((coh+ton)/2))}%;background:{PRIMARY}'></div></div>",
                    unsafe_allow_html=True
                )

                st.markdown("**Recommandations**")
                if coh<70: st.markdown("- Renforcer l’alignement sur les mots-clés et missions.")
                if ton<70: st.markdown("- Adopter un ton plus formel et inclure des exemples chiffrés.")
                st.markdown("- Structure suggérée : Introduction → Valeur ajoutée → Exemples → Conclusion polie.")

                with st.expander("Texte analysé"):
                    st.text_area("Lettre", letter_text, height=240, key="letter_text_preview")

                pdf_bytes = export_pdf_report(
                    filename="rapport_lettre.pdf",
                    title="EspritCareers — Rapport Lettre",
                    fields={"Cohérence":f"{coh}/100","Ton & structure":f"{ton}/100","Mots-clés couverts":", ".join(overlap) if overlap else "—"}
                )
                st.download_button("Télécharger le rapport (PDF)", data=pdf_bytes, file_name="rapport_lettre.pdf", mime="application/pdf", key="download_letter_btn")
    st.markdown('</div>', unsafe_allow_html=True)
# ==============================
# TAB ENTRETIEN — Simulation optimisée
# ==============================
if "qcm_score" not in st.session_state:
    st.session_state.qcm_score = 0
if "open_answers" not in st.session_state:
    st.session_state.open_answers = {}

with tab_interview:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Simulation d’entretien — Optimisé</div>', unsafe_allow_html=True)

    # Sélection domaine et niveau
    colA, colB = st.columns([1,1])
    with colA:
        domain = st.selectbox("Domaine", list(QUESTION_BANK.keys()))
    with colB:
        level = st.selectbox("Niveau", ["Junior","Intermédiaire","Senior"])

    bank = QUESTION_BANK[domain]

    # --- QCM ---
    st.markdown("### QCM")
    for i, (q, options, correct_idx) in enumerate(bank["QCM"], start=1):
        st.write(f"{i}. {q}")
        key_radio = f"{domain}_qcm_{i}"
        choice = st.radio(
            "Réponse",
            options,
            index=0 if key_radio not in st.session_state or st.session_state[key_radio] is None
                  else options.index(st.session_state[key_radio]),
            key=key_radio
        )
        st.session_state[key_radio] = choice
        key_btn = f"chk_{domain}_{i}"
        if st.button(f"Vérifier {i}", key=key_btn):
            if options.index(choice) == correct_idx:
                st.success("✅ Correct")
                st.session_state.qcm_score += 1
            else:
                st.error(f"Mauvaise réponse. Bonne réponse : {options[correct_idx]}")

    # --- Questions ouvertes (guide STAR) ---
    st.markdown("### Questions ouvertes (guide STAR)")
    for j, q in enumerate(bank["OPEN"], start=1):
        key_open = f"{domain}_open_{j}"
        if key_open not in st.session_state.open_answers:
            st.session_state.open_answers[key_open] = ""
        ans = st.text_area(
            f"{j}. {q}",
            value=st.session_state.open_answers.get(key_open,""),
            key=key_open,
            height=100
        )
        st.session_state.open_answers[key_open] = ans
        if ans.strip():
            st.info(
                f"Conseil STAR :\n- Situation : contexte\n- Tâche : rôle\n- Action : actions\n- Résultat : impact"
            )

    # --- Résumé & Dashboard ---
    st.markdown("### Résumé & Dashboard")
    total_qcm = len(bank["QCM"])
    total_open = len(bank["OPEN"])
    answered_open = sum(1 for ans in st.session_state.open_answers.values() if ans.strip())

    col_d1, col_d2, col_d3 = st.columns(3)
    col_d1.metric("Score QCM", f"{st.session_state.qcm_score}/{total_qcm}")
    col_d2.metric("Réponses ouvertes", f"{answered_open}/{total_open}")
    col_d3.metric("Progression globale", f"{int((st.session_state.qcm_score/total_qcm*0.5 + answered_open/total_open*0.5)*100)}%")

    # --- Visualisation simple ---
    scores = [st.session_state.qcm_score, answered_open]
    labels = ["QCM", "Ouvertes"]
    colors = ["#E00000","#FF6347"]
    fig, ax = plt.subplots()
    ax.bar(labels, scores, color=colors)
    ax.set_ylim(0, max(total_qcm,total_open))
    ax.set_ylabel("Réponses correctes / complétées")
    st.pyplot(fig)

    # --- Export PDF Entretien ---
    fields = {
        "Score QCM": f"{st.session_state.qcm_score}/{total_qcm}",
        "Réponses ouvertes": f"{answered_open}/{total_open}",
        "Domaine": domain,
        "Niveau": level
    }
    pdf_bytes = export_pdf_report(
        filename="rapport_entretien.pdf",
        title="EspritCareers — Rapport Entretien",
        fields=fields
    )
    st.download_button("Télécharger le rapport (PDF)", data=pdf_bytes, file_name="rapport_entretien.pdf", mime="application/pdf", key="download_interview_btn")
    st.markdown('</div>', unsafe_allow_html=True)
