import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import sys

# Import de votre module d'obligations
from Importation_BAM_BDT import download_bdt

# Configuration Streamlit
st.set_page_config(
    page_title="Gestionnaire d'Obligations BAM",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Styles CSS personnalisés
st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 28px;
        color: #1f77b4;
    }
    .big-font {
        font-size: 24px;
        font-weight: bold;
        color: #2c3e50;
    }
    .medium-font {
        font-size: 18px;
        font-weight: bold;
        color: #34495e;
    }
    .status-success {
        color: #27ae60;
        font-weight: bold;
    }
    .status-error {
        color: #e74c3c;
        font-weight: bold;
    }
    .status-warning {
        color: #f39c12;
        font-weight: bold;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# ============================================
# FONCTIONS UTILITAIRES
# ============================================

def round_excel(x, n):
    """Arrondi au style Excel"""
    q = Decimal(10) ** -n
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def is_bissextile(annee):
    """Vérifie si une année est bissextile"""
    return (annee % 4 == 0 and annee % 100 != 0) or (annee % 400 == 0)


def get_A(annee):
    """Retourne le nombre de jours dans l'année"""
    return 366 if is_bissextile(annee) else 365


def actualise(tr: float, dt_days: int, a: int) -> float:
    """Formule d'actualisation"""
    return (1 + tr * dt_days / 360) ** (a / dt_days) - 1


def monetarise(tr: float, dt_days: int, a: int) -> float:
    """Formule de monétarisation"""
    return ((1 + tr) ** (dt_days / a) - 1) * (360 / dt_days)


def extrapolation(mr: int, tab_mat: list, tab_taux: list) -> float:
    """Extrapolation linéaire des taux"""
    if mr <= tab_mat[0]:
        xa, xb = tab_mat[0], tab_mat[1]
        ya, yb = tab_taux[0], tab_taux[1]
    else:
        xa, xb = tab_mat[-2], tab_mat[-1]
        ya, yb = tab_taux[-2], tab_taux[-1]
    if xb == xa:
        return yb
    return ya + (yb - ya) * (mr - xa) / (xb - xa)


# ============================================
# CLASSE OBLIGATION
# ============================================

class obligation:
    """Classe pour gérer les obligations"""
    Toutes_les_oblig = []
    Data_BAM = None

    def __init__(self, N, r, T_init, T_final, T_eval, freq_coupon):
        self.N = N
        self.r = r
        self.d_init = T_init
        self.d_final = T_final
        self.d_eval = T_eval
        self.T_init = (pd.to_datetime(self.d_final, dayfirst=True) - 
                       pd.to_datetime(self.d_init, dayfirst=True)).days
        self.T_resid = (pd.to_datetime(self.d_final, dayfirst=True) - 
                        pd.to_datetime(self.d_eval, dayfirst=True)).days
        self.freq = freq_coupon
        obligation.Toutes_les_oblig.append(self)
    
    def calc_taux_actu(self):
        """Calcule le taux actuariel"""
        if obligation.Data_BAM is None:
            return None

        Data_BAM = obligation.Data_BAM.copy()
        Data_BAM = Data_BAM.drop(columns=["Transaction"], errors="ignore")
        Data_BAM = Data_BAM.iloc[:-1]
        
        date_actu = pd.to_datetime(Data_BAM["Date de la valeur"], dayfirst=True)
        date_echec = pd.to_datetime(Data_BAM["Date d'échéance"], dayfirst=True)
        Data_BAM["Maturite_resid"] = (date_echec - date_actu).dt.days.astype(float)
        Data_BAM["Taux moyen pondéré"] = round(
            Data_BAM["Taux moyen pondéré"]
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
            .astype(float) / 100, 5
        )
        Data_BAM = Data_BAM.sort_values("Maturite_resid").reset_index(drop=True)
        date_valo = pd.to_datetime(self.d_eval, dayfirst=True)

        mr = self.T_resid
        tab_mat = Data_BAM["Maturite_resid"].values
        tab_taux = Data_BAM["Taux moyen pondéré"].values

        if mr < tab_mat[0] or mr > tab_mat[-1]:
            result = extrapolation(mr, tab_mat, tab_taux)
            return result

        result = None
        for j in range(len(tab_mat) - 1):
            xa, xb = tab_mat[j], tab_mat[j + 1]
            ya, yb = tab_taux[j], tab_taux[j + 1]

            from dateutil.relativedelta import relativedelta
            
            aa = ((date_valo + timedelta(days=xa)) -
                (date_valo + timedelta(days=xa) - relativedelta(years=1))).days
            ab = ((date_valo + timedelta(days=xb)) -
                (date_valo + timedelta(days=xb) - relativedelta(years=1))).days

            if mr >= xa and mr <= xb and xb > 365 and xa <= 365:
                if mr > 365:
                    ya = actualise(ya, xa, aa)
                    result = ya + (mr - xa) * (yb - ya) / (xb - xa)
                else:
                    yb = monetarise(yb, xb, ab)
                    result = ya + (mr - xa) * (yb - ya) / (xb - xa)
                break

            elif mr >= xa and mr < xb and (xb <= 365 or xa > 365):
                result = ya + (mr - xa) * (yb - ya) / (xb - xa)
                break
        return round_excel(result, 5) if result else None
        
    def date_detach(self):
        """Calcule la date de détachement du coupon"""
        date_echeance = pd.to_datetime(self.d_final, dayfirst=True)
        date_emission = pd.to_datetime(self.d_init, dayfirst=True)
        if (date_emission.day, date_emission.month) != (date_echeance.day, date_echeance.month):
            if (pd.Timestamp(date_emission.year + 1, date_echeance.month, date_echeance.day) - 
                date_emission).days > get_A(date_emission.year):
                date_detachement = pd.Timestamp(date_emission.year + 1, 
                                               date_echeance.month, date_echeance.day)
            else:
                date_detachement = pd.Timestamp(date_emission.year + 2, 
                                               date_echeance.month, date_echeance.day)
        else:
            date_detachement = pd.Timestamp(date_emission.year + 1, 
                                           date_echeance.month, date_echeance.day)
        return date_detachement
    
    def coupon_suiv(self):
        """Calcule la date du coupon suivant"""
        date_echeance = pd.to_datetime(self.d_final, dayfirst=True)
        date_evaluation = pd.to_datetime(self.d_eval, dayfirst=True)
        date_detachement = self.date_detach()
        if date_detachement > date_evaluation:
            date_coup_suiv = date_detachement
        else:
            if (pd.Timestamp(date_evaluation.year + 1, date_echeance.month, 
                           date_echeance.day) - date_evaluation).days > get_A(date_evaluation.year):
                date_coup_suiv = pd.Timestamp(date_evaluation.year, 
                                             date_echeance.month, date_echeance.day)
            else:
                date_coup_suiv = pd.Timestamp(date_evaluation.year + 1, 
                                             date_echeance.month, date_echeance.day)
        return date_coup_suiv

    def calc_prix(self):
        """Calcule le prix de l'obligation"""
        t_r = round(self.calc_taux_actu(), 5)
        if t_r is None:
            return None
            
        date_echeance = pd.to_datetime(self.d_final, dayfirst=True)
        date_emission = pd.to_datetime(self.d_init, dayfirst=True)
        date_evaluation = pd.to_datetime(self.d_eval, dayfirst=True)
        date_detachement = self.date_detach()
        date_coupon_suivant = self.coupon_suiv()
        A = get_A(date_evaluation.year)
        
        if self.T_init <= 365:
            Prix = self.N * (1 + self.r * self.T_init/360) / (1 + t_r * self.T_resid/360)
        else:
            if self.T_resid <= 365:
                if (date_emission.day, date_emission.month) != (date_echeance.day, date_echeance.month) and self.T_init < 731:
                    Prix = self.N * (1 + self.r * self.T_init/A) / (1 + t_r * self.T_resid/360)
                else:
                    Prix = self.N * (1 + self.r) / (1 + t_r * self.T_resid/360)
            elif self.T_resid > 365:
                nj = (date_coupon_suivant - date_evaluation).days
                n = date_echeance.year - date_coupon_suivant.year + 1
                if (date_emission.day, date_emission.month) != (date_echeance.day, date_echeance.month):
                    if self.T_init <= 730:
                        Prix = self.N * (1 + self.r * self.T_init/A) / ((1 + t_r)**(nj/A))
                    elif self.T_init > 730 and (date_evaluation - date_detachement).days < 0:
                        coupon = self.N * self.r
                        somme = 0
                        for i in range(2, n):
                            somme += coupon / (1 + t_r)**(i - 1)
                        flux_final = (coupon + self.N) / (1 + t_r)**(n-1)
                        Prix = (1 / (1 + t_r)**(nj/A)) * (coupon * ((date_detachement - date_emission).days)/A + somme + flux_final)
                    else:
                        coupon = self.N * self.r
                        somme = 0
                        for i in range(1, n):
                            somme += coupon / (1 + t_r)**(i-1)
                        flux_final = (coupon + self.N) / (1 + t_r)**(n-1)
                        Prix = (1 / (1 + t_r)**(nj/A)) * (somme + flux_final)
                else:
                    coupon = self.N * self.r
                    somme = 0
                    for i in range(1, n):
                        somme += coupon / (1 + t_r)**(i-1)
                    flux_final = (coupon + self.N) / (1 + t_r)**(n-1)
                    Prix = (1 / (1 + t_r)**(nj/A)) * (somme + flux_final)
            else:
                Prix = None
        return Prix


# ============================================
# GESTION DE L'ÉTAT
# ============================================

if "obligations" not in st.session_state:
    st.session_state.obligations = []
    obligation.Toutes_les_oblig = []

if "bam_data" not in st.session_state:
    st.session_state.bam_data = None

if "bam_loaded" not in st.session_state:
    st.session_state.bam_loaded = False


# ============================================
# SIDEBAR - CONFIGURATION
# ============================================

st.sidebar.markdown("## ⚙️ Configuration")

date_valuation = st.sidebar.date_input(
    "Date de valuation BAM",
    value=datetime(2026, 2, 6)
)

col1, col2 = st.sidebar.columns(2)

with col1:
    if st.button("🔄 Charger données BAM", use_container_width=True, key="btn_load_bam"):
        with st.spinner("Chargement des données BAM..."):
            try:
                date_str = date_valuation.strftime("%d/%m/%Y")
                st.session_state.bam_data = download_bdt(date_str)
                st.session_state.bam_loaded = True
                obligation.Data_BAM = st.session_state.bam_data
                st.sidebar.success("✅ Données BAM chargées")
            except Exception as e:
                st.sidebar.error(f"❌ Erreur: {str(e)}")
                st.session_state.bam_loaded = False

with col2:
    if st.session_state.bam_loaded:
        st.sidebar.markdown('<p class="status-success">✅ BAM Chargée</p>', unsafe_allow_html=True)
    else:
        st.sidebar.markdown('<p class="status-warning">⚠️ BAM non chargée</p>', unsafe_allow_html=True)


# ============================================
# PAGE PRINCIPALE
# ============================================

st.markdown("# 📊 Gestionnaire d'Obligations - BAM")
st.markdown("Application de gestion et valorisation d'obligations avec données BAM")

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Portefeuille", "📈 Courbe BAM", "📥 Import Excel"])


# ============================================
# TAB 1: PORTEFEUILLE D'OBLIGATIONS
# ============================================

with tab1:
    st.markdown("## Gestion du Portefeuille")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("➕ Ajouter obligation", use_container_width=True, key="btn_add_oblig"):
            st.session_state.show_form = True
    
    with col2:
        if st.button("💰 Calculer les prix", use_container_width=True, key="btn_calc_prix"):
            if not st.session_state.bam_loaded:
                st.warning("⚠️ Veuillez d'abord charger les données BAM")
            elif len(st.session_state.obligations) == 0:
                st.warning("⚠️ Aucune obligation à calculer")
            else:
                st.success("✅ Prix calculés")
    
    with col3:
        if st.button("🔄 Rafraîchir", use_container_width=True, key="btn_refresh"):
            st.rerun()
    
    with col4:
        if st.button("🗑️ Effacer tout", use_container_width=True, key="btn_clear"):
            st.session_state.obligations = []
            obligation.Toutes_les_oblig = []
            st.rerun()
    
    # Formulaire d'ajout
    if st.session_state.get("show_form", False):
        st.markdown("### Ajouter une nouvelle obligation")
        with st.form("form_obligation"):
            col1, col2 = st.columns(2)
            
            with col1:
                nominal = st.number_input("Nominal", min_value=0.0, value=100000.0, step=100.0)
                taux_facial = st.number_input("Taux facial (%)", min_value=0.0, value=3.0, step=0.01)
                date_emission = st.date_input(
                    "Date d'émission",
                    value=datetime(2020, 1, 1),
                    min_value=datetime(1900, 1, 1),
                    max_value=datetime(2100, 12, 31)
                )
            
            with col2:
                date_echeance = st.date_input(
                    "Date d'échéance",
                    value=datetime(2030, 1, 1),
                    min_value=datetime(1900, 1, 1),
                    max_value=datetime(2100, 12, 31)
                )
                
                date_eval = st.date_input(
                    "Date d'évaluation",
                    value=datetime(2026, 2, 6),
                    min_value=datetime(1900, 1, 1),
                    max_value=datetime(2100, 12, 31)
                )
                freq = st.selectbox("Fréquence des coupons", 
                                   ["Annuel", "Semestriel", "Trimestriel", "Mensuel"],
                                   index=0)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("✅ Ajouter", use_container_width=True):
                    try:
                        freq_map = {"Annuel": 1, "Semestriel": 2, "Trimestriel": 3, "Mensuel": 4}
                        oblig = obligation(
                            N=nominal,
                            r=taux_facial / 100,
                            T_init=date_emission.strftime("%d/%m/%Y"),
                            T_final=date_echeance.strftime("%d/%m/%Y"),
                            T_eval=date_eval.strftime("%d/%m/%Y"),
                            freq_coupon=freq_map[freq]
                        )
                        st.session_state.obligations.append(oblig)
                        st.success("✅ Obligation ajoutée")
                        st.session_state.show_form = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erreur: {str(e)}")
            
            with col2:
                if st.form_submit_button("❌ Annuler", use_container_width=True):
                    st.session_state.show_form = False
                    st.rerun()
    
    # Table des obligations
    if len(obligation.Toutes_les_oblig) > 0:
        st.markdown("### Obligations en portefeuille")
        
        data = []
        total_nominal = 0
        total_value = 0
        total_rate = 0
        
        for idx, oblig in enumerate(obligation.Toutes_les_oblig):
            try:
                taux_actu = oblig.calc_taux_actu() if st.session_state.bam_loaded else None
                prix = oblig.calc_prix() if st.session_state.bam_loaded else None
                
                total_nominal += oblig.N
                if prix:
                    total_value += prix
                total_rate += oblig.r
                
                freq_text = ["Annuel", "Semestriel", "Trimestriel", "Mensuel"][oblig.freq - 1]
                
                data.append({
                    "ID": idx + 1,
                    "Nominal": f"{oblig.N:,.2f}",
                    "Taux facial": f"{oblig.r*100:.4f}%",
                    "Émission": oblig.d_init,
                    "Échéance": oblig.d_final,
                    "Évaluation": oblig.d_eval,
                    "Maturité": f"{oblig.T_resid} j",
                    "Fréquence": freq_text,
                    "Taux actuariel": f"{taux_actu*100:.4f}%" if taux_actu else "N/A",
                    "Prix": f"{prix:,.2f}" if prix else "N/A"
                })
            except Exception as e:
                st.warning(f"Erreur calcul obligation {idx+1}: {str(e)}")
        
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Statistiques
        st.markdown("### 📊 Statistiques du portefeuille")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Obligations", len(obligation.Toutes_les_oblig))
        
        with col2:
            st.metric("Nominal total", f"{total_nominal:,.2f}")
        
        with col3:
            st.metric("Valeur totale", f"{total_value:,.2f}")
        
        with col4:
            avg_rate = (total_rate / len(obligation.Toutes_les_oblig) * 100) if len(obligation.Toutes_les_oblig) > 0 else 0
            st.metric("Taux moyen", f"{avg_rate:.4f}%")
    else:
        st.info("📋 Aucune obligation en portefeuille. Ajoutez-en une pour commencer.")


# ============================================
# TAB 2: COURBE BAM
# ============================================

with tab2:
    st.markdown("## 📈 Courbe des Taux BAM")
    
    if st.session_state.bam_loaded and st.session_state.bam_data is not None:
        df_bam = st.session_state.bam_data.copy()
        
        st.markdown(f"**Date de valuation:** {date_valuation.strftime('%d/%m/%Y')}")
        
        # Afficher le tableau
        st.dataframe(df_bam, use_container_width=True, hide_index=True)
        
        # Graphique des taux
        try:
            df_bam_clean = df_bam.copy()
            df_bam_clean = df_bam_clean.drop(columns=["Transaction"], errors="ignore")
            
            if len(df_bam_clean) > 0:
                st.markdown("### Visualisation des taux")
                
                import matplotlib.pyplot as plt
                
                fig, ax = plt.subplots(figsize=(12, 6))
                
                # Supposant qu'il y a une colonne de maturité et taux
                if "Maturite_resid" in df_bam_clean.columns and "Taux moyen pondéré" in df_bam_clean.columns:
                    ax.plot(df_bam_clean["Maturite_resid"], 
                           df_bam_clean["Taux moyen pondéré"], 
                           marker='o', linewidth=2, markersize=8, color='#1f77b4')
                    ax.set_xlabel("Maturité résiduelle (jours)", fontsize=12)
                    ax.set_ylabel("Taux moyen pondéré", fontsize=12)
                    ax.set_title("Courbe des Taux BAM", fontsize=14, fontweight='bold')
                    ax.grid(True, alpha=0.3)
                    st.pyplot(fig)
        except Exception as e:
            st.warning(f"Impossible de créer le graphique: {str(e)}")
    else:
        st.info("💡 Cliquez sur 'Charger données BAM' dans la configuration pour voir la courbe des taux.")


# ============================================
# TAB 3: IMPORT EXCEL
# ============================================

with tab3:
    st.markdown("## 📥 Import d'obligations depuis Excel")
    
    st.markdown("""
    ### 📋 Format attendu
    
    Le fichier Excel doit contenir les colonnes suivantes:
    - **Nominal**: Montant nominal de l'obligation
    - **Taux_facial**: Taux facial (ex: 0.03 pour 3%)
    - **Date_emission**: Date d'émission (format: JJ/MM/AAAA)
    - **Date_echeance**: Date d'échéance (format: JJ/MM/AAAA)
    - **Date_evaluation**: Date d'évaluation (format: JJ/MM/AAAA)
    - **Frequence**: Fréquence des coupons (1=annuel, 2=semestriel, 3=trimestriel, 4=mensuel)
    """)
    
    uploaded_file = st.file_uploader("Sélectionner un fichier Excel", type=["xlsx", "xls"])
    
    if uploaded_file is not None:
        try:
            df_import = pd.read_excel(uploaded_file)
            
            required_cols = ['Nominal', 'Taux_facial', 'Date_emission', 
                           'Date_echeance', 'Date_evaluation', 'Frequence']
            
            missing_cols = [col for col in required_cols if col not in df_import.columns]
            
            if missing_cols:
                st.error(f"❌ Colonnes manquantes: {', '.join(missing_cols)}")
            else:
                st.success(f"✅ Fichier valide: {len(df_import)} ligne(s) détectée(s)")
                
                # Aperçu
                st.markdown("### Aperçu des données")
                st.dataframe(df_import, use_container_width=True, hide_index=True)
                
                # Bouton d'import
                if st.button("✅ Importer les obligations", use_container_width=True):
                    imported = 0
                    errors = 0
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    for i, (idx, row) in enumerate(df_import.iterrows()):
                        try:
                            oblig = obligation(
                                N=float(row['Nominal']),
                                r=float(row['Taux_facial']),
                                T_init=str(row['Date_emission']),
                                T_final=str(row['Date_echeance']),
                                T_eval=str(row['Date_evaluation']),
                                freq_coupon=int(row['Frequence'])
                            )
                            st.session_state.obligations.append(oblig)
                            imported += 1
                        except Exception as e:
                            errors += 1
                            st.warning(f"Erreur ligne {i+1}: {str(e)}")
                        
                        progress_bar.progress((i + 1) / len(df_import))
                        status_text.text(f"Traitement: {i + 1}/{len(df_import)}")
                    
                    st.success(f"✅ Import terminé: {imported} obligation(s) importée(s), {errors} erreur(s)")
                    if imported > 0:
                        st.rerun()
        
        except Exception as e:
            st.error(f"❌ Erreur lors de la lecture du fichier: {str(e)}")


# ============================================
# FOOTER
# ============================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #7f8c8d; font-size: 12px;">
Gestionnaire d'Obligations BAM | Développé avec Streamlit
</div>
""", unsafe_allow_html=True)
