import streamlit as st
import fitz  # PyMuPDF
from docx import Document
from PIL import Image
import pytesseract
import io, re, json, time
import pandas as pd

# ----------------------------
# CONFIG
# ----------------------------
st.set_page_config(
    page_title="EspritCareers",
    layout="wide",
    initial_sidebar_state="expanded"
)

PRIMARY = "#E00000"   # Esprit Red
BG_CARD = "#0f1115"
BORDER = "#1f2937"
TEXT_MUTED = "#9ca3af"

st.markdown(f"""
<style>
:root {{
  --primary: {PRIMARY};
  --bg-card: {BG_CARD};
  --border: {BORDER};
}}
html, body, [class*="css"] {{
  font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
}}
.ec-card {{
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 16px 14px;
  background: var(--bg-card);
}}
.ec-title {{
  font-size: 22px; font-weight: 600; margin-bottom: 8px;
}}
.ec-subtitle {{
  color: {TEXT_MUTED}; font-size: 13px; margin-bottom: 8px;
}}
.ec-btn-primary > button {{
  background-color: var(--primary) !important;
  color: #fff !important; border: none !important; border-radius: 10px !important;
}}
.ec-badge {{
  display:inline-block; padding:2px 8px; border-radius:999px; border:1px solid #2a2f3a;
  color:#e5e7eb; font-size:12px; margin-right:6px; background:#131722;
}}
</style>
""", unsafe_allow_html=True)

# ----------------------------
# SIDEBAR
# ----------------------------
with st.sidebar:
    try:
        st.image("assets/esprit_logo.png", use_container_width=True)
    except Exception:
        st.write("EspritCareers")
    st.markdown('<div class="ec-card"><div class="ec-title">Guide</div><div class="ec-subtitle">CV, Lettre, Entretien. Formats acceptés : PDF, DOCX, Image (OCR).</div></div>', unsafe_allow_html=True)

# ----------------------------
# HELPERS: Extraction & Scoring
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
le la les un une des et à de du pour par ou au aux en avec sur sous dans d' l' the a an to of in on at for from by with as is are
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

def build_job_keywords(job_text):
    cands = keyword_candidates(job_text, top=30)
    must = cands[:10]
    nice = cands[10:20]
    return {
        "must_have": must,
        "nice_to_have": nice,
        "weights": {"mh":0.5,"nh":0.2,"struct":0.15,"quant":0.1,"format":0.05}
    }

def keyword_score(cv_text, must_have, nice_to_have):
    t = normalize(cv_text)
    smh = sum(1 for k in must_have if k.lower() in t) / max(1, len(must_have))
    snh = sum(1 for k in nice_to_have if k.lower() in t) / max(1, len(nice_to_have))
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
    sst = structure_score(cv_text)
    sq  = quantify_score(cv_text)
    sfo = 1.0  # placeholder mise en forme
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
        suggestions.append(f"Ajouter/renforcer les mots-clés essentiels : {', '.join(missing_mh)}.")
    if quantify_score(cv_text) < 0.6:
        suggestions.append("Quantifier les réalisations avec des chiffres, pourcentages et délais.")
    if structure_score(cv_text) < 0.8:
        suggestions.append("Vérifier les sections standard : Profil, Expérience, Formation, Compétences, Projets.")
    suggestions += [
        "Employer des verbes d’action (conçu, déployé, optimisé, automatisé, négocié).",
        "Condens­er le résumé en 4–5 lignes orientées résultats et outils."
    ]
    return suggestions[:5]

def tone_heuristic(letter_text):
    t = letter_text.lower()
    score_formel = int(any(x in t for x in ["madame","monsieur","candidature","motivation","cordialement"])) * 50
    score_concret = min(50, len(re.findall(r"\b\d+%?|\b(kpi|roi|budget|projet|deadline)\b", t))*5)
    return min(100, score_formel + score_concret)

# ----------------------------
# LAYOUT
# ----------------------------
st.title("EspritCareers")
st.caption("Plateforme d’employabilité — Analyse de CV, Lettre de motivation, Simulation d’entretien.")

tab_cv, tab_cover, tab_interview = st.tabs(["CV", "Lettre", "Entretien"])

# ----------------------------
# TAB: CV
# ----------------------------
with tab_cv:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Analyse de CV (ATS)</div>', unsafe_allow_html=True)
    st.markdown('<div class="ec-subtitle">Téléverser un CV et coller l’offre de poste pour obtenir un score ATS avec explications.</div>', unsafe_allow_html=True)

    colA, colB = st.columns([1,1])
    with colA:
        uploaded_cv = st.file_uploader("Fichier CV (PDF, DOCX, Image)", type=["pdf","docx","png","jpg","jpeg"], key="cv")
    with colB:
        job_text = st.text_area("Offre de poste (copier-coller)", height=180)

    run = st.container()
    with run:
        col_run, _ = st.columns([0.25, 0.75])
        with col_run:
            run_btn = st.button("Analyser", type="primary", use_container_width=True)

    if run_btn:
        if not uploaded_cv or not job_text.strip():
            st.error("Veuillez ajouter un CV et l’offre de poste.")
        else:
            text, used_ocr = extract_text_from_file(uploaded_cv)
            if len(text) < 80:
                st.error("Le document semble vide ou illisible. Fournir un PDF/DOCX de meilleure qualité.")
            else:
                job_kw = build_job_keywords(job_text)
                score, breakdown = ats_score(text, job_kw)

                col1, col2, col3 = st.columns(3)
                col1.metric("Score ATS", f"{score}/100")
                col2.metric("Mots-clés essentiels couverts", f"{int(round(breakdown['Must-have']/50*len(job_kw['must_have']),0))}/{len(job_kw['must_have'])}")
                col3.metric("OCR utilisé", "Oui" if used_ocr else "Non")

                st.progress(min(1.0, score/100))

                st.markdown("Détail des points")
                dfb = pd.DataFrame({"Dimension": list(breakdown.keys()), "Points": list(breakdown.values())})
                st.bar_chart(dfb.set_index("Dimension"))

                st.markdown("Suggestions")
                for s in suggest_improvements(text, job_kw):
                    st.markdown(f"- {s}")

                with st.expander("Texte extrait"):
                    st.text_area("Contenu", text, height=220)

                report = {
                    "score": score,
                    "breakdown": breakdown,
                    "must_have": job_kw["must_have"],
                    "nice_to_have": job_kw["nice_to_have"],
                    "ocr_used": used_ocr,
                    "ts": int(time.time())
                }
                st.download_button(
                    "Télécharger le rapport (JSON)",
                    data=json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
                    file_name="rapport_ats.json",
                    mime="application/json"
                )
    st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------
# TAB: LETTRE
# ----------------------------
with tab_cover:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Lettre de motivation — Cohérence et ton</div>', unsafe_allow_html=True)

    lc1, lc2 = st.columns([1,1])
    with lc1:
        uploaded_letter = st.file_uploader("Fichier lettre (PDF, DOCX, Image) ou coller le texte ci-dessous", type=["pdf","docx","png","jpg","jpeg"], key="cover")
        letter_text_input = st.text_area("Texte de la lettre", height=220)
    with lc2:
        job_text_cover = st.text_area("Offre de poste (référence pour la cohérence)", height=220, key="job_cover")
        analyze_cover = st.button("Analyser la lettre", type="primary", use_container_width=True)

    if analyze_cover:
        if not uploaded_letter and not letter_text_input.strip():
            st.error("Veuillez ajouter un fichier ou coller le texte de la lettre.")
        elif not job_text_cover.strip():
            st.error("Veuillez coller l’offre de poste pour évaluer la cohérence.")
        else:
            if uploaded_letter:
                text_letter, _ = extract_text_from_file(uploaded_letter)
            else:
                text_letter = letter_text_input

            if len(text_letter) < 60:
                st.error("La lettre semble trop courte ou illisible.")
            else:
                kw_job = set(build_job_keywords(job_text_cover)["must_have"])
                overlap = [k for k in kw_job if k in normalize(text_letter)]
                coh = min(100, int(len(overlap)/max(1,len(kw_job))*100))
                ton = tone_heuristic(text_letter)

                cc1, cc2 = st.columns(2)
                cc1.metric("Cohérence vs offre", f"{coh}/100")
                cc2.metric("Ton et structure", f"{ton}/100")
                st.progress(min(1.0, (coh+ton)/200))

                st.markdown("Recommandations")
                if coh < 70:
                    st.markdown("- Renforcer l’alignement sur les mots-clés et missions de l’offre.")
                if ton < 70:
                    st.markdown("- Renforcer le ton formel et ajouter des éléments concrets (résultats, KPIs).")
                st.markdown("- Structure suggérée : Introduction, Valeur ajoutée, Exemples, Conclusion polie.")

                with st.expander("Texte analysé"):
                    st.text_area("Lettre", text_letter, height=220)
    st.markdown('</div>', unsafe_allow_html=True)

# ----------------------------
# TAB: ENTRETIEN (banque élargie)
# ----------------------------
QUESTION_BANK = {
    # Domaines supplémentaires: Finance, Supply Chain, RH, Marketing, Data, Dév, PM/PMO
    "Business Analyst": {
        "QCM": [
            ("Quel livrable décrit les besoins fonctionnels d’un projet ?", ["SLA", "BRD", "SOW"], 1),
            ("Quel diagramme modélise les interactions utilisateur-système ?", ["UML Use Case", "Gantt", "PERT"], 0),
            ("Quel artefact capture l’acceptation d’une fonctionnalité ?", ["Definition of Ready", "User Story + critères d’acceptation", "Definition of Done"], 1),
        ],
        "OPEN": [
            "Décrivez une situation où vous avez clarifié un besoin ambigu et l’impact sur le projet.",
            "Donnez un exemple où vous avez arbitré des priorités conflictuelles.",
            "Expliquez une recommandation que vous avez formulée à partir de données et son résultat."
        ]
    },
    "Data Analyst": {
        "QCM": [
            ("Quelle mesure évalue la dispersion autour de la moyenne ?", ["Variance", "Médiane", "Mode"], 0),
            ("Quel join SQL renvoie seulement les correspondances ?", ["LEFT JOIN", "INNER JOIN", "FULL OUTER JOIN"], 1),
            ("Quel graphique privilégier pour une série temporelle ?", ["Histogramme", "Linéaire", "Secteurs"], 1),
        ],
        "OPEN": [
            "Décrivez un tableau de bord que vous avez conçu et ses indicateurs clés.",
            "Expliquez une analyse ayant conduit à une décision mesurable.",
            "Comment gérez-vous des données manquantes ou aberrantes ?"
        ]
    },
    "PMO": {
        "QCM": [
            ("Dans un PMO, quel est l’objectif principal ?", ["Vente", "Gouvernance et standardisation", "Support juridique"], 1),
            ("Quel indicateur suit l’avancement coût/délai/portée ?", ["RACI", "EVM", "SIPOC"], 1),
            ("Qui est responsable du backlog produit ?", ["Scrum Master", "Product Owner", "Sponsor"], 1),
        ],
        "OPEN": [
            "Expliquez un plan de rattrapage que vous avez orchestré sur un projet en dérive.",
            "Comment standardiseriez-vous les reportings d’un portefeuille projets ?",
            "Décrivez votre approche de gestion des risques prioritaires."
        ]
    },
    "Marketing": {
        "QCM": [
            ("Quel cadre structure une proposition de valeur ?", ["SWOT", "4P/7P", "JTBD"], 2),
            ("Quel canal mesure le mieux l’intention active ?", ["SEO/SEA", "Affichage", "RP"], 0),
            ("Quel KPI évalue la fidélité ?", ["CAC", "CLV", "CPA"], 1),
        ],
        "OPEN": [
            "Décrivez une campagne que vous avez pilotée et ses résultats.",
            "Expliquez votre méthode de test A/B et de mesure d’impact.",
            "Comment priorisez-vous les segments et messages ?"
        ]
    },
    "Finance": {
        "QCM": [
            ("Quel état présente les flux de trésorerie ?", ["Bilan", "Compte de résultat", "Tableau des flux de trésorerie"], 2),
            ("Que signifie EBITDA ?", ["Résultat brut d’exploitation", "Résultat net", "Chiffre d’affaires"], 0),
            ("Quel indicateur mesure la rentabilité d’un investissement ?", ["IRR/TRI", "WACC", "VAR"], 0),
        ],
        "OPEN": [
            "Décrivez une analyse de rentabilité et vos recommandations.",
            "Comment gérez-vous un budget sous contrainte forte ?",
            "Donnez un exemple de réduction de coûts mesurable."
        ]
    },
    "Supply Chain": {
        "QCM": [
            ("Quel indicateur suit la fiabilité des stocks ?", ["OTIF", "Fill Rate", "Lead Time"], 1),
            ("Quel modèle vise à réduire les gaspillages ?", ["Lean", "Six Sigma", "PERT"], 0),
            ("Quel est l’objectif du S&OP ?", ["Alignement demande/offre", "Reporting RH", "Audit qualité"], 0),
        ],
        "OPEN": [
            "Expliquez une optimisation de flux logistique et son impact.",
            "Comment gérez-vous des ruptures fournisseurs critiques ?",
            "Décrivez un projet S&OP ou une prévision améliorée."
        ]
    },
    "Ressources Humaines": {
        "QCM": [
            ("Quel indicateur mesure la rétention ?", ["Turnover", "Absenteisme", "NPS"], 0),
            ("Quel document formalise un objectif trimestriel ?", ["OKR", "SLA", "MoU"], 0),
            ("Quel risque majeur du recrutement sans ATS ?", ["Time-to-hire élevé", "CLV bas", "Churn client"], 0),
        ],
        "OPEN": [
            "Décrivez un processus d’onboarding standardisé.",
            "Comment améliorer la qualité des recrutements ?",
            "Expliquez une initiative RH à impact mesurable."
        ]
    },
    "Développeur Python": {
        "QCM": [
            ("Quel type stocke des paires clé/valeur ?", ["list", "dict", "tuple"], 1),
            ("Quelle structure pour gérer des files FIFO ?", ["list", "deque", "set"], 1),
            ("Quel outil pour l’isolation des dépendances ?", ["virtualenv/venv", "cron", "make"], 0),
        ],
        "OPEN": [
            "Décrivez un script automatisant une tâche et ses gains.",
            "Comment assurez-vous la qualité (tests, linting) ?",
            "Expliquez une optimisation de performance réalisée."
        ]
    }
}

with tab_interview:
    st.markdown('<div class="ec-card">', unsafe_allow_html=True)
    st.markdown('<div class="ec-title">Simulation d’entretien</div>', unsafe_allow_html=True)

    domain = st.selectbox(
        "Domaine",
        list(QUESTION_BANK.keys())
    )
    level = st.selectbox("Niveau", ["Junior", "Intermédiaire"])
    add_focus = st.text_input("Focus (mots-clés séparés par des virgules, optionnel)")

    gen_btn = st.button("Générer les questions", type="primary", use_container_width=True)

    if gen_btn:
        bank = QUESTION_BANK[domain]
        # QCM
        st.markdown("QCM")
        qcm_df_rows = []
        for i, (q, options, correct_idx) in enumerate(bank["QCM"], start=1):
            st.write(f"{i}. {q}")
            choice = st.radio("Réponse", options, key=f"{domain}_qcm_{i}")
            if st.button(f"Vérifier {i}", key=f"check_{domain}_{i}"):
                if options.index(choice) == correct_idx:
                    st.success("Correct")
                else:
                    st.error(f"Mauvaise réponse. Bonne réponse : {options[correct_idx]}")
            qcm_df_rows.append({"Question": q, "Options": " | ".join(options), "Bonne réponse": options[correct_idx]})
        if qcm_df_rows:
            st.dataframe(pd.DataFrame(qcm_df_rows))

        # Ouvertes
        st.markdown("Questions ouvertes (guide)")
        for j, q in enumerate(bank["OPEN"], start=1):
            st.markdown(f"- {q}")

        st.info("Conseil : répondre selon STAR (Situation, Tâche, Action, Résultat) et quantifier l’impact lorsque c’est possible.")
    st.markdown('</div>', unsafe_allow_html=True)
