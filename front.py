# front.py
import streamlit as st
from PIL import Image
import pandas as pd
from sekhem_utils import Utils
from config import *
import plotly.graph_objects as go

# =========================
# Helpers d'état (session)
# =========================
def get_utils(country_code: str):
    """Crée/récupère l'instance Utils persistée dans session_state."""
    if "utils" not in st.session_state:
        st.session_state["utils"] = Utils(country_code)
    return st.session_state["utils"]


def init_session_defaults(utils: Utils):
    """Initialise les valeurs par défaut dans session_state une seule fois."""
    if "begining" not in st.session_state:
        st.session_state["begining"] = pd.to_datetime(utils.getBeginingDate())
    if "end" not in st.session_state:
        st.session_state["end"] = pd.to_datetime(utils.getEndDate())
    if "dpt" not in st.session_state:
        st.session_state["dpt"] = utils.getDepartmentName()
    if "use_enhanced_map" not in st.session_state:
        st.session_state["use_enhanced_map"] = True  # par défaut on active la carte améliorée


def _coerce_dates(begin_dt: pd.Timestamp, end_dt: pd.Timestamp):
    """S'assure que begin <= end. Si non, inverse et retourne (begin, end) corrigés."""
    if begin_dt > end_dt:
        return end_dt, begin_dt
    return begin_dt, end_dt


class front:
    def __init__(self, country_code='SEN'):
        self.utils = get_utils(country_code)
        init_session_defaults(self.utils)

        try:
            self.listDepartmentName = self.utils.getAllDepartementsName()
        except Exception:
            self.listDepartmentName = [self.utils.getDepartmentName()]

    # -------------------------
    # Affichages principaux
    # -------------------------
    def drawMap(self):
        try:
            with st.spinner("Chargement de la carte…"):
                if st.session_state.get("use_enhanced_map", True) and hasattr(self.utils, "show_enhanced_map"):
                    m = self.utils.show_enhanced_map()
                else:
                    m = self.utils.show_combined_map()
                return m.to_streamlit(height=600, use_container_width=True)
        except Exception as e:
            st.error(f"Erreur d'affichage de la carte : {e}")

    def drawGraphics(self):
        try:
            with st.spinner("Calcul des séries temporelles…"):
                st.plotly_chart(
                    self.utils.show_combined_graphics(),
                    use_container_width=True
                )
        except Exception as e:
            st.error(f"Erreur d'affichage des graphiques : {e}")

    def drawFloodDashboard(self):
        st.markdown("### 🌊 Tableau de Bord - Prédiction d'Inondations")

        # -> Statistiques améliorées (fallback automatique côté Utils si non dispo)
        flood_stats = self.utils.get_enhanced_flood_statistics()
        lvl = int(flood_stats.get('alert_level', 0) or 0)
        msg = flood_stats.get('alert_message', 'N/A')

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "💧 MNDWI Moyen",
                f"{float(flood_stats.get('mndwi_mean', 0) or 0):.3f}",
                help="Modified Normalized Difference Water Index (plus élevé ⇒ plus d'eau)"
            )
        with col2:
            st.metric(
                "🏞️ Surface d'eau",
                f"{float(flood_stats.get('water_area_ha', 0) or 0):.2f} ha",
                help="Surface totale d'eau détectée (ha)"
            )
        with col3:
            st.metric(
                "📊 % Inondation",
                f"{float(flood_stats.get('flood_percentage', 0) or 0):.2f}%",
                help="Pourcentage de la zone inondée"
            )
        with col4:
            icon = {0: "🟢", 1: "🟡", 2: "🟠", 3: "🔴", 4: "🟣"}.get(lvl, "⚫")
            alert_labels = {0:"Très faible",1:"Faible",2:"Modéré",3:"Élevé",4:"Très élevé"}
            st.metric(f"{icon} Niveau d'Alerte", f"Niveau {lvl} - {alert_labels.get(lvl, '—')}")

        if lvl >= 3:
            st.error(f"🚨 **ALERTE ÉLEVÉE**: {msg}")
        elif lvl == 2:
            st.warning(f"⚠️ **VIGILANCE**: {msg}")
        elif lvl == 1:
            st.info(f"ℹ️ **SURVEILLANCE**: {msg}")
        else:
            st.success(f"✅ **NORMAL**: {msg}")

        # Détail par type d'usage si disponible
        with st.expander("📎 Détail des surfaces inondées par type de zone"):
            urb = flood_stats.get('urban_flood_ha')
            agr = flood_stats.get('agricultural_flood_ha')
            frt = flood_stats.get('forest_flood_ha')
            rur = flood_stats.get('rural_flood_ha')
            tot = flood_stats.get('total_flood_ha')
            if any(v is not None for v in [urb, agr, frt, rur, tot]):
                st.write(f"- 🏙️ **Urbain** : {float(urb or 0):.2f} ha")
                st.write(f"- 🌾 **Agricole** : {float(agr or 0):.2f} ha")
                st.write(f"- 🌳 **Forêt/Végétation** : {float(frt or 0):.2f} ha")
                st.write(f"- 🏞️ **Autres zones rurales** : {float(rur or 0):.2f} ha")
                st.write(f"- 🧮 **Total** : {float(tot or 0):.2f} ha")
                prio = flood_stats.get('priority_zones', [])
                if prio:
                    st.info("Zones prioritaires : " + ", ".join(prio))
            else:
                st.caption("Pas de détail par type d'usage disponible (fallback).")

        # Série temporelle MNDWI (+ inondations urbaines si dispo)
        st.markdown("#### 📈 Évolution MNDWI")
        flood_df = self.utils.get_flood_temporal_data()

        if not flood_df.empty and 'mndwi_values' in flood_df.columns:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=flood_df['periods'], y=flood_df['mndwi_values'],
                mode='lines+markers', name='MNDWI',
                line=dict(color='blue', width=3),
                marker=dict(size=7)
            ))
            # Série barres pour inondations urbaines si présente
            if 'urban_flood_area' in flood_df.columns:
                fig.add_trace(go.Bar(
                    x=flood_df['periods'], y=flood_df['urban_flood_area'],
                    name="Inondations urbaines (ha)", opacity=0.4
                ))
            fig.add_hline(y=0, line_dash="dash", line_color="red",
                          annotation_text="Seuil eau (MNDWI = 0)")
            fig.add_hrect(y0=-1, y1=-0.3, fillcolor="green", opacity=0.08,
                          annotation_text="Très sec", annotation_position="left")
            fig.add_hrect(y0=-0.3, y1=0.0, fillcolor="yellow", opacity=0.08,
                          annotation_text="Sec", annotation_position="left")
            fig.add_hrect(y0=0.0, y1=0.3, fillcolor="orange", opacity=0.08,
                          annotation_text="Eau probable", annotation_position="left")
            fig.add_hrect(y0=0.3, y1=1.0, fillcolor="red", opacity=0.08,
                          annotation_text="Eau certaine", annotation_position="left")

            fig.update_layout(
                title="Évolution de l'indice MNDWI (et inondations urbaines si disponibles)",
                xaxis_title="Date",
                yaxis_title="MNDWI",
                barmode="overlay",
                showlegend=True,
                height=420
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("⚠️ Données temporelles MNDWI indisponibles.")

    # -------------------------
    # Exports / actions
    # -------------------------
    def export_csv_button(self):
        try:
            data = self.utils.export_data_to_csv()
            st.sidebar.download_button(
                key="btn_export_csv",
                label="💾 Exporter données CSV",
                data=data,
                file_name=f"donnees_surveillance_complete_{self.utils.getDepartmentName()}.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.sidebar.error(f"Export CSV impossible : {e}")

    def download_maps_button(self):
        if st.sidebar.button('📥 Télécharger cartes (PNG/GIF)', key="btn_export_maps", use_container_width=True):
            try:
                with st.spinner("Export des cartes en cours…"):
                    self.utils.exportCards()
                st.sidebar.success("Export lancé. Vérifiez le dossier Downloads.")
            except Exception as e:
                st.sidebar.error(f"Export impossible : {e}")

    # -------------------------
    # Page principale
    # -------------------------
    def paint(self):
        st.set_page_config(
            page_title="SEKHEM - Surveillance Environnementale et Inondations",
            page_icon="🌍",
            layout="wide"
        )

        # Style + logo optionnels
        try:
            with open('style.css') as f:
                st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
        except Exception:
            pass
        try:
            logo = Image.open("sekhem_logo.png")
            st.sidebar.image(logo, width=200)
        except Exception:
            st.sidebar.markdown("# 🌍 SEKHEM")

        st.sidebar.markdown("<br>", unsafe_allow_html=True)

        # Toggle carte améliorée
        st.sidebar.markdown("### 🗺️ Affichage")
        st.session_state["use_enhanced_map"] = st.sidebar.toggle(
            "Carte améliorée (occupation du sol & types d'inondation)",
            value=st.session_state.get("use_enhanced_map", True)
        )

        # Statut système (avant filtres, pour donner un retour initial)
        system_status = self.utils.get_system_status()

        # -----------------
        # Filtres latéraux
        # -----------------
        current_dep = self.utils.getDepartmentName()
        try:
            idx = self.listDepartmentName.index(current_dep)
        except ValueError:
            idx = 0

        sel_dep = st.sidebar.selectbox("🏘️ Département :", self.listDepartmentName, index=idx, key="sel_dep")

        begin_date = st.sidebar.date_input("📅 Date de début", value=st.session_state["begining"].date(), key="input_begin")
        end_date = st.sidebar.date_input("📅 Date de fin", value=st.session_state["end"].date(), key="input_end")

        # Validation & application
        begin_dt, end_dt = _coerce_dates(pd.to_datetime(begin_date), pd.to_datetime(end_date))
        if begin_dt != pd.to_datetime(begin_date) or end_dt != pd.to_datetime(end_date):
            st.sidebar.info("ℹ️ Les dates ont été réordonnées (début ≤ fin).")

        # Appliquer changements de département
        if sel_dep != st.session_state["dpt"]:
            st.session_state["dpt"] = sel_dep
            with st.spinner("Changement de département…"):
                self.utils.setDepartment(sel_dep)

        # Appliquer changements de dates
        if begin_dt != st.session_state["begining"]:
            st.session_state["begining"] = begin_dt
            with st.spinner("Mise à jour de la période (début)…"):
                self.utils.setBeginingDate(begin_dt.strftime('%Y-%m-%d'))

        if end_dt != st.session_state["end"]:
            st.session_state["end"] = end_dt
            with st.spinner("Mise à jour de la période (fin)…"):
                self.utils.setEndDate(end_dt.strftime('%Y-%m-%d'))

        # -----------------
        # Exports latéraux
        # -----------------
        st.sidebar.markdown("### 📥 Exports")
        self.export_csv_button()
        self.download_maps_button()

        # Rafraîchit le statut après éventuels changements
        system_status = self.utils.get_system_status()

        # -----------------
        # TABS
        # -----------------
        tab1, tab2, tab3 = st.tabs(["🗺️ Carte Interactive", "📊 Analyse Temporelle", "🌊 Prédiction Inondations"])

        with tab1:
            st.markdown("<h2>🗺️ Surveillance Environnementale Intégrée</h2>", unsafe_allow_html=True)
            st.markdown("*Feux, LST (MODIS), Dynamic World & détection d'inondations (MNDWI/NDWI/S1).*")
            col1, col2 = st.columns([3, 1])

            with col1:
                self.drawMap()

            with col2:
                st.markdown("### 🎛️ État des couches")
                st.markdown(f"🔥 Feux ")
                st.markdown(f"🌳 Forêts (DW) ")
                st.markdown(f"🌊 Inondations ")

                st.markdown("---")
                st.markdown("### 📊 Métriques clés")
                try:
                    forest_area = self.utils.forest_area_ha.getInfo()
                    st.metric("🌳 Superficie forestière", f"{forest_area} ha")
                except Exception:
                    st.metric("🌳 Superficie forestière", "—")

                try: 
                    fs = self.utils.get_flood_statistics() 
                    st.metric("💧 MNDWI", f"{fs['mndwi_mean']:.3f}") 
                    st.metric("🌊 Zone inondée", f"{fs['water_area_ha']} ha") 
                except Exception: 
                    st.metric("💧 MNDWI", "—") 
                    st.metric("🌊 Zone inondée", "—")

        with tab2:
            st.markdown("<h2>📈 Analyse Temporelle Multi-Indicateurs</h2>", unsafe_allow_html=True)
            st.markdown("*Évolution des feux, de la couverture (DW label) et de l'eau (MNDWI).*")
            self.drawGraphics()

            st.markdown("### 📋 Résumé")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("**🔥 Feux**\n- Points chauds (VIIRS)\n- Tendances récentes\n- Alerte précoce")
            with col2:
                st.markdown("**🌳 Occupation des sols (DW)**\n- Probabilité arbres\n- Changements spatio-temporels\n- Contexte couverture")
            with col3:
                st.markdown("**🌊 Eau (MNDWI/NDWI)**\n- Détection robuste (SWIR)\n- Sensible à l'eau libre\n- Complément S1 radar")

        with tab3:
            st.markdown("<h2>🌊 Système de Prédiction d'Inondations</h2>", unsafe_allow_html=True)
            st.markdown("*Analyse MNDWI (Sentinel-2) et fallback Radar Sentinel-1.*")
            self.drawFloodDashboard()

            st.markdown("---")
            st.markdown("### 📚 À propos de MNDWI")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
                    **🔬 Formule MNDWI**
                    **📊 Interprétation (règle pratique)**
                    - **> 0.3** : Eau très probable  
                    - **0 → 0.3** : Eau probable  
                    - **-0.3 → 0** : Zone sèche  
                    - **< -0.3** : Très sec
                """)
            with col2:
                st.markdown("""
                    **✅ Pourquoi MNDWI (vs NDWI) ?**
                    - Moins sensible à la végétation dense (usage SWIR)
                    - Meilleure robustesse atmosphérique
                    - Détection d'eau plus stable en agro-écosystèmes
                    - Combine bien avec NDWI & Sentinel-1
                """)


if __name__ == "__main__":
    app = front(country_code=COUNTRY_CODE)
    app.paint()
