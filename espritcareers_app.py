import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
import re, io, json, time, math
import pandas as pd
import numpy as np

# ----------------------------
# CONFIG & BRANDING
# ----------------------------
st.set_page_config(
    page_title="EspritCareers",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

PRIMARY = "#E00000"   # Esprit Red
DARK = "#111111"
MUTED = "#6B7280"
BG = "#0B0C10"

st.markdown(f"""
<style>
/* Global */
html, body, [class*="css"]  {{
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji","Segoe UI Symbol";
}}
/* Header title */
h1, h2, h3, h4 {{
  letter-spacing: .3px;
}}
/* Cards */
.ec-card {{
  border: 1px solid #1f2937;
  border-radius: 16px;
  padding: 18px 18px 14px;
  background: #0f1115;
}}
/* Primary button */
div.stButton > button:first-child {{
  background-color: {PRIMARY};
  color: #fff; border-radius: 12px; border: none; padding: 8px 14px;
}}
/* Tags */
.badge {{
  display:inline-block; padding:4px 10px; border-radius:999px; background:#111827; color:#e5e7eb; font-size:12px; border:1px solid #1f2937;
}}
.metric-ok {{color:#16a34a}}
.metric-warn {{color:#f59e0b}}
.metric-bad {{color:#ef4444}}
</style>
""", unsafe_allow_html=True)

# ----------------------------
# SIDEBAR (LOGO + NAV)
# ----------------------------
with st.sidebar:
    try:
        st.image("assets/esprit_logo.png", use_container_width=True, caption="EspritCareers • v2")
    except Exception:
        st.write("🎓 EspritCareers")

# ----------------------------
# HELPERS: extraction & NLP light
# ----------------------------
def extract_text_from_file(file):
    name = file.name.lower()
    byts = file.read()
    if name.endswith(".pdf"):
        doc = fitz.open(stream=byts, filetype="pdf")
        text, used_ocr = "", False
        for page in doc:
            t = page.get_text().strip()
            if not t:
                # OCR fallback
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes()))
                t = pytesseract.image_to_string(img, lang="fra+eng")
                used_ocr = True
            text += "\n" + t
        return text.strip(), used_ocr
    elif name.endswith(".docx"):
        docx = Document(io.BytesIO(byts))
        return "\n".join(p.text for p in docx.paragraphs), False
    elif name.endswith((".png",".jpg",".jpeg")):
        img = Image.open(io.BytesIO(byts))
        t = pytesseract.image_to_string(img, lang="fra+eng")
        return t.strip(), True
    else:
        return "", False

STOPWORDS = set("""
le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l' un(e) le/la
a et/ou que qui quoi dont où alors ainsi donc or ni car the a an to of in on at for from by with as is are
""".split())

def keyword_candidates(text, top=20):
    # super simple keywording
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9\+\#\.]{2,}", text.lower())
    tokens = [t for t in tokens if t not in STOPWORDS and not t.isdigit()]
    freq = pd.Series(tokens).value_counts().head(top)
    return list(freq.index)

def build_job_keywords(job_text):
    cands = keyword_candidates(job_text, top=30)
    # heuristique: must-have = top 10, nice-to-have = suivants
    must = cands[:10]
    nice = cands[10:20]
    return {
        "must_have": must,
        "nice_to_have": nice,
        "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}
    }

def normalize(t):
    return re.sub(r"[^a-zA-ZÀ-ÿ0-9\s\-]", " ", t.lower())

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k.lower() in t)
    snh = sum(1 for k in nice_to_have if k.lower() in t)
    return (smh/ max(1,len(must_have))), (snh/ max(1,len(nice_to_have)))

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
    sst = structure_score(cv_text)
    sq  = quantify_score(cv_text)
    sfo = 1.0  # placeholder (lisibilité/mise en forme)
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
    missing_mh = [k for k in job_kw["must_have"] if k.lower() not in t][:6]
    suggestions = []
    if missing_mh:
        suggestions.append(f"Ajoute/renforce ces mots-clés indispensables : **{', '.join(missing_mh)}**.")
    if quantify_score(cv_text) < 0.6:
        suggestions.append("Ajoute des **chiffres** (%, €, délais, volumes) pour quantifier tes réalisations.")
    if structure_score(cv_text) < 0.8:
        suggestions.append("Vérifie les **sections** standards : Profil, Expérience, Formation, Compétences, Projets.")
    suggestions += [
        "Utilise des **verbes d’action** : conçu, déployé, optimisé, automatisé, négocié.",
        "Raccourcis le résumé en 4–5 lignes, orienté **résultats** et **outils**."
    ]
    return suggestions[:5]

def tone_heuristic(letter_text):
    t = letter_text.lower()
    score_formel = int(any(x in t for x in ["madame","monsieur","candidature","motivation","cordialement"])) * 50
    score_concret = min(50, len(re.findall(r"\b\d+%?|\b(kpi|roi|budget|projet|deadline)\b", t))*5)
    return min(100, score_formel + score_concret)

# Session state to collect analyses for dashboard
if "history" not in st.session_state:
    st.session_state["history"] = []

st.title("🎓 EspritCareers")
st.caption("Plateforme d’employabilité – **Analyse de CV**, **Lettre de motivation**, **Simulation d’entretien**, **Dashboard**.")

# ----------------------------
# TABS
# ----------------------------
tab_cv, tab_cover, tab_interview, tab_dash = st.tabs(["📄 CV", "✉️ Lettre", "🗣️ Entretien", "📊 Dashboard"])

# ----------------------------
# TAB: CV
# ----------------------------
with tab_cv:
    st.subheader("Analyse de CV (ATS)")
    colA, colB = st.columns([1,1])
    with colA:
        uploaded_cv = st.file_uploader("Téléverse ton CV (PDF, DOCX ou Image)", type=["pdf","docx","png","jpg","jpeg"], key="cv")
        job_text = st.text_area("Colle ici l’offre de poste / mission", placeholder="Colle l'offre (missions, compétences, mots-clés, logiciels…)", height=180)
        run = st.button("🔎 Analyser le CV")
    with colB:
        st.markdown('<div class="ec-card">', unsafe_allow_html=True)
        st.markdown("**Conseil**")
        st.caption("Plus l’offre est détaillée, plus le score ATS est pertinent (mots-clés must-have / nice-to-have).")
        st.markdown('</div>', unsafe_allow_html=True)

    if run:
        if not uploaded_cv or not job_text.strip():
            st.error("Ajoute un CV **et** colle l’offre de poste, puis relance.")
        else:
            with st.spinner("Extraction du texte…"):
                text, used_ocr = extract_text_from_file(uploaded_cv)

            if len(text) < 80:
                st.error("Le document semble vide ou illisible. Essaie un PDF/DOCX de meilleure qualité.")
            else:
                job_kw = build_job_keywords(job_text)
                score, breakdown = ats_score(text, job_kw)

                c1, c2, c3 = st.columns(3)
                c1.metric("🎯 Score ATS", f"{score}/100")
                c2.metric("📌 Must-have couverts", f"{int(round(breakdown['Must-have']/50*len(job_kw['must_have']),0))}/{len(job_kw['must_have'])}")
                c3.metric("🖼️ OCR utilisé", "Oui" if used_ocr else "Non")

                st.progress(min(1.0, score/100))
                st.markdown("#### Détails du score")
                dfb = pd.DataFrame({"Dimension": list(breakdown.keys()), "Points": list(breakdown.values())})
                st.bar_chart(dfb.set_index("Dimension"))

                st.markdown("#### Suggestions")
                for s in suggest_improvements(text, job_kw):
                    st.markdown(f"- {s}")

                with st.expander("Voir le texte extrait"):
                    st.text_area("Texte extrait", text, height=220)

                # Save to history for dashboard
                st.session_state["history"].append({
                    "ts": time.time(),
                    "type": "cv",
                    "score": score,
                    "breakdown": breakdown
                })

                # Export JSON report
                report = {
                    "score": score,
                    "breakdown": breakdown,
                    "must_have": job_kw["must_have"],
                    "nice_to_have": job_kw["nice_to_have"],
                    "ocr_used": used_ocr
                }
                st.download_button(
                    "📥 Télécharger le rapport (JSON)",
                    data=json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name="rapport_ats.json",
                    mime="application/json"
                )

# ----------------------------
# TAB: Lettre
# ----------------------------
with tab_cover:
    st.subheader("Lettre de motivation – Cohérence & Ton")
    lc1, lc2 = st.columns([1,1])
    with lc1:
        uploaded_letter = st.file_uploader("Téléverse ta lettre (PDF, DOCX ou Image)", type=["pdf","docx","png","jpg","jpeg"], key="cover")
        letter_text_input = st.text_area("…ou colle le texte ici", height=220)
    with lc2:
        job_text_cover = st.text_area("Colle l’offre de poste (référence pour la cohérence)", height=220, key="job_cover")
        analyze_cover = st.button("🧠 Analyser la lettre")

    if analyze_cover:
        if not uploaded_letter and not letter_text_input.strip():
            st.error("Ajoute un fichier **ou** colle le texte de la lettre.")
        elif not job_text_cover.strip():
            st.error("Colle l’offre pour évaluer la cohérence.")
        else:
            if uploaded_letter:
                text_letter, _ = extract_text_from_file(uploaded_letter)
            else:
                text_letter = letter_text_input

            if len(text_letter) < 60:
                st.error("La lettre semble trop courte / illisible.")
            else:
                kw_job = set(build_job_keywords(job_text_cover)["must_have"])
                overlap = [k for k in kw_job if k in normalize(text_letter)]
                coh = min(100, int(len(overlap)/max(1,len(kw_job))*100))
                ton = tone_heuristic(text_letter)

                mc1, mc2 = st.columns(2)
                mc1.metric("🔗 Cohérence vs offre", f"{coh}/100")
                mc2.metric("🗒️ Ton & structure", f"{ton}/100")
                st.progress(min(1.0, (coh+ton)/200))

                st.markdown("#### Recommandations")
                if coh < 70:
                    st.markdown("- Aligne mieux ta lettre sur les **mots-clés** et missions de l’offre.")
                if ton < 70:
                    st.markdown("- Renforce le **ton formel** et ajoute des **exemples chiffrés** (résultats, KPIs).")
                st.markdown("- Utilise la structure : *Intro* → *Motivation/valeur ajoutée* → *Exemples* → *Conclusion polie*.")

                with st.expander("Voir le texte de la lettre"):
                    st.text_area("Lettre", text_letter, height=220)

                st.session_state["history"].append({
                    "ts": time.time(),
                    "type": "letter",
                    "coherence": coh,
                    "tone": ton
                })

# ----------------------------
# TAB: Entretien
# ----------------------------
with tab_interview:
    st.subheader("Simulation d’entretien")
    role = st.selectbox("Rôle ciblé", ["Business Analyst", "Data Analyst", "PMO Junior", "Marketing Analyst", "Développeur Python"])
    level = st.selectbox("Niveau", ["Junior", "Intermédiaire"])
    focus = st.multiselect("Focus", ["SQL", "Python", "Excel/BI", "Gestion de projet", "Communication", "Produit"])
    gen = st.button("🎤 Générer des questions")

    if gen:
        qcm = []
        openq = []
        # QCM simple en fonction du focus
        if "SQL" in focus:
            qcm.append({"q":"Quelle requête renvoie les 10 dernières lignes d'une table `orders` ?", 
                        "opts":["SELECT * FROM orders LIMIT 10;",
                                "SELECT * FROM orders ORDER BY created_at DESC LIMIT 10;",
                                "SELECT TOP 10 * FROM orders;"],
                        "correct":1})
        if "Python" in focus:
            qcm.append({"q":"Quel objet stocke des paires clé/valeur en Python ?", 
                        "opts":["list","tuple","dict"], "correct":2})
        if "Gestion de projet" in focus:
            qcm.append({"q":"Dans SCRUM, qui priorise le backlog ?", 
                        "opts":["Scrum Master","Product Owner","Développeur"], "correct":1})

        openq += [
            {"q": "Donne un exemple **STAR** où tu as amélioré un KPI clé."},
            {"q": "Comment gères-tu un stakeholder **difficile** ?"},
            {"q": "Décris une **analyse** dont l’impact a été mesuré (temps, coûts, qualité)."}
        ]

        st.markdown("#### QCM")
        score_qcm = 0
        for i, item in enumerate(qcm):
            st.write(f"**Q{i+1}.** {item['q']}")
            ans = st.radio("Réponse :", item["opts"], key=f"qcm{i}")
            if st.button(f"Vérifier Q{i+1}", key=f"chk{i}"):
                idx = item["opts"].index(ans)
                if idx == item["correct"]:
                    st.success("✔️ Correct")
                    score_qcm += 1
                else:
                    st.error(f"❌ Mauvaise réponse. Bonne réponse : **{item['opts'][item['correct']]}**")

        st.markdown("#### Questions ouvertes (guide)")
        for j, q in enumerate(openq):
            st.write(f"- {q['q']}")

        st.info("Astuce : Réponds en **STAR** (Situation, Tâche, Action, Résultat) et **quantifie** ton impact.")

# ----------------------------
# TAB: Dashboard
# ----------------------------
with tab_dash:
    st.subheader("Dashboard – Démo")
    hist = st.session_state.get("history", [])
    if not hist:
        st.caption("Les résultats de tes analyses s’afficheront ici.")
    else:
        df = pd.DataFrame(hist)
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Analyses réalisées", len(df))
        with c2:
            if "score" in df.columns:
                st.metric("Score ATS moyen", f"{round(df['score'].dropna().mean(),1)} / 100")
        st.markdown("#### Historique (table)")
        st.dataframe(df.fillna("-"))
        st.markdown("#### Répartition par type")
        counts = df["type"].value_counts()
        st.bar_chart(counts)

# ----------------------------
# END
# ----------------------------
