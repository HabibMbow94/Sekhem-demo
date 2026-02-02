import streamlit as st
from PIL import Image
import pandas as pd
from sekhem_utils import FloodMonitoringSystem  # Importez votre classe
from config import *
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import ee
import hashlib
from datetime import datetime, timedelta
from streamlit_folium import st_folium

st.set_page_config(
    page_title="SEKHEM - Surveillance Environnementale et Inondations",
    page_icon="🌍",
    layout="wide"
)

# =========================
# Fonctions de cache
# =========================

def generate_cache_key(dept_name: str, begin_date: str, end_date: str, stat_type: str) -> str:
    """Génère une clé de cache unique basée sur les paramètres."""
    key_string = f"{dept_name}_{begin_date}_{end_date}_{stat_type}"
    return hashlib.md5(key_string.encode()).hexdigest()

@st.cache_data(ttl=3600)  # Cache pendant 1 heure
def get_cached_flood_statistics(dept_name: str, begin_date: str, end_date: str):
    """Cache des statistiques d'inondation."""
    try:
        monitoring_system = st.session_state.get("monitoring_system")
        if monitoring_system:
            return monitoring_system.get_flood_statistics()
    except Exception as e:
        st.error(f"Erreur cache flood stats: {e}")
    return {'wei_mean': 0.0, 'water_area_ha': 0.0, 'flood_percentage': 0.0}

@st.cache_data(ttl=3600)  # Cache pendant 1 heure
def get_cached_forest_statistics(dept_name: str, begin_date: str, end_date: str):
    """Cache des statistiques forestières."""
    try:
        monitoring_system = st.session_state.get("monitoring_system")
        if monitoring_system:
            return monitoring_system.get_forest_statistics()
    except Exception as e:
        st.error(f"Erreur cache forest stats: {e}")
    return {'forest_area_ha': 0.0, 'forest_percentage': 0.0}

@st.cache_data(ttl=1800)  # Cache pendant 30 minutes
def get_cached_comprehensive_statistics(dept_name: str, begin_date: str, end_date: str):
    """Cache des statistiques complètes."""
    try:
        monitoring_system = st.session_state.get("monitoring_system")
        if monitoring_system:
            return monitoring_system.get_comprehensive_statistics()
    except Exception as e:
        st.error(f"Erreur cache comprehensive stats: {e}")
    return {}

@st.cache_data(ttl=1800)  # Cache pendant 30 minutes
def get_cached_temporal_data(dept_name: str, begin_date: str, end_date: str):
    """Cache des données temporelles."""
    try:
        monitoring_system = st.session_state.get("monitoring_system")
        if monitoring_system:
            return monitoring_system.get_flood_temporal_data()
    except Exception as e:
        st.error(f"Erreur cache temporal data: {e}")
    return pd.DataFrame()

@st.cache_data(ttl=1800)  # Cache pendant 30 minutes
def get_cached_temporal_data_complete(dept_name: str, begin_date: str, end_date: str):
    """Cache des données temporelles complètes (WEI, MNDWI, NDVI, Forest)."""
    try:
        monitoring_system = st.session_state.get("monitoring_system")
        if monitoring_system:
            return monitoring_system.get_temporal_data_complete()
    except Exception as e:
        st.error(f"Erreur cache temporal complete data: {e}")
    return pd.DataFrame()

@st.cache_data(ttl=7200)  # Cache pendant 2 heures (données plus stables)
def get_cached_forest_temporal_data(dept_name: str, begin_date: str, end_date: str):
    """Cache des données temporelles forestières."""
    try:
        monitoring_system = st.session_state.get("monitoring_system")
        if monitoring_system:
            # Récupérer les données temporelles complètes
            complete_data = monitoring_system.get_temporal_data_complete()
            if not complete_data.empty and 'forest_percentage' in complete_data.columns:
                return complete_data[['date', 'forest_percentage']]
    except Exception as e:
        st.error(f"Erreur cache forest temporal: {e}")
    return pd.DataFrame()

# =========================
# Helpers d'état (session)
# =========================

def get_monitoring_system(country_code: str):
    """Crée/récupère l'instance FloodMonitoringSystem persistée dans session_state."""
    if "monitoring_system" not in st.session_state:
        st.session_state["monitoring_system"] = FloodMonitoringSystem(country_code)
    return st.session_state["monitoring_system"]

def init_session_defaults(monitoring_system: FloodMonitoringSystem):
    """Initialise les valeurs par défaut dans session_state une seule fois."""
    if "begining" not in st.session_state:
        st.session_state["begining"] = pd.to_datetime(monitoring_system.begining)
    if "end" not in st.session_state:
        st.session_state["end"] = pd.to_datetime(monitoring_system.end)
    if "dpt" not in st.session_state:
        st.session_state["dpt"] = monitoring_system.department_name

def _coerce_dates(begin_dt: pd.Timestamp, end_dt: pd.Timestamp):
    """S'assure que begin <= end. Si non, inverse et retourne (begin, end) corrigés."""
    if begin_dt > end_dt:
        return end_dt, begin_dt
    return begin_dt, end_dt

class FrontApp:
    def __init__(self, country_code='SEN'):
        self.monitoring_system = get_monitoring_system(country_code)
        init_session_defaults(self.monitoring_system)
        try:
            self.list_department_name = self.monitoring_system.getAllDepartementsName()
        except Exception:
            self.list_department_name = [self.monitoring_system.department_name]

    # -------------------------
    # Affichages principaux
    # -------------------------
    def draw_map(self):
        try:
            with st.spinner("Chargement de la carte…"):
                m = self.monitoring_system.show_map()
                # Utiliser st_folium pour afficher la carte geemap dans Streamlit
                return st_folium(m, height=600, width=True)
        except Exception as e:
            st.error(f"Erreur d'affichage de la carte : {e}")
            # Afficher une carte de base en cas d'erreur
            import geemap
            basic_map = geemap.Map(center=[12.5, -16.5], zoom=8)
            return st_folium(basic_map, height=600, width=True)

    def draw_graphics(self):
        """Affiche WEI (eau) + Couverture forestière (évolutions)."""
        try:
            with st.spinner("Calcul des séries temporelles…"):
                temporal_data = get_cached_temporal_data_complete(
                    self.monitoring_system.department_name,
                    self.monitoring_system.begining,
                    self.monitoring_system.end
                )

                if temporal_data.empty:
                    st.warning("Aucune donnée temporelle disponible pour cette période.")
                    return

                temporal_data['date'] = pd.to_datetime(temporal_data['date'])
                temporal_data = temporal_data.sort_values('date')

                fig = make_subplots(
                    rows=2, cols=1,
                    subplot_titles=("🌊 Évolution WEI (Extension d'eau)", "🌳 Évolution Couverture Forestière"),
                    vertical_spacing=0.12,
                    row_heights=[0.5, 0.5]
                )

                # WEI
                if 'WEI' in temporal_data.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=temporal_data['date'],
                            y=temporal_data['WEI'],
                            mode='lines+markers',
                            name='WEI (Eau)',
                            line=dict(color='red', width=3),
                            marker=dict(size=8)
                        ),
                        row=1, col=1
                    )
                    fig.add_hline(y=0.3, line_dash="dash", line_color="red",
                                annotation_text="Seuil eau (WEI=0.3)", row=1, col=1)

                # Forêt
                if 'forest_percentage' in temporal_data.columns:
                    fig.add_trace(
                        go.Scatter(
                            x=temporal_data['date'],
                            y=temporal_data['forest_percentage'],
                            mode='lines+markers',
                            name='Couverture Forestière (%)',
                            line=dict(color='green', width=3),
                            marker=dict(size=8)
                        ),
                        row=2, col=1
                    )
                    for y, dash, txt in [(60,"dot","Élevé (60%)"),(30,"dash","Modéré (30%)"),(10,"dot","Faible (10%)")]:
                        fig.add_hline(y=y, line_dash=dash, line_color="gray",
                                    annotation_text=txt, row=2, col=1)

                fig.update_layout(
                    title=f"📈 Analyse Temporelle : WEI & Couverture Forestière — {self.monitoring_system.department_name}",
                    height=700,
                    showlegend=False
                )
                fig.update_xaxes(title_text="Date", row=2, col=1)
                fig.update_yaxes(title_text="WEI (0–1)", row=1, col=1, range=[0,1])
                fig.update_yaxes(title_text="Forêt (%)", row=2, col=1, range=[0,100])

                st.plotly_chart(fig, width=True)

                # mini-trend badges
                # self.display_trend_analysis(temporal_data)

        except Exception as e:
            st.error(f"Erreur d'affichage des graphiques temporels : {e}")
            
    def draw_water_indices_timeseries(self):
        """Affiche les courbes MNDWI et WEI dans l'onglet Zones en Eau."""
        df = get_cached_temporal_data_complete(
            self.monitoring_system.department_name,
            self.monitoring_system.begining,
            self.monitoring_system.end
        )
        if df.empty:
            st.info("Aucune série temporelle disponible pour MNDWI/WEI.")
            return

        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')

        # MNDWI
        if 'MNDWI' in df.columns:
            fig_mndwi = go.Figure()
            fig_mndwi.add_trace(go.Scatter(
                x=df['date'], y=df['MNDWI'],
                mode='lines+markers', name='MNDWI'
            ))
            fig_mndwi.add_hline(y=0.0, line_dash="dash", line_color="gray",
                                annotation_text="Seuil 0", annotation_position="top right")
            fig_mndwi.update_layout(
                title="Évolution MNDWI",
                xaxis_title="Date", yaxis_title="MNDWI",
                height=350
            )
            st.plotly_chart(fig_mndwi, width=True)

        # WEI
        if 'WEI' in df.columns:
            fig_wei = go.Figure()
            fig_wei.add_trace(go.Scatter(
                x=df['date'], y=df['WEI'],
                mode='lines+markers', name='WEI (Eau)'
            ))
            fig_wei.add_hline(y=self.monitoring_system.wei_threshold, line_dash="dash", line_color="red",
                            annotation_text=f"Seuil WEI ({self.monitoring_system.wei_threshold})",
                            annotation_position="top right")
            fig_wei.update_layout(
                title="Évolution WEI",
                xaxis_title="Date", yaxis_title="WEI (0–1)",
                yaxis=dict(range=[0,1]),
                height=350
            )
            st.plotly_chart(fig_wei, width=True)

    # def display_trend_analysis(self, temporal_data):
    #     """Affiche l'analyse des tendances."""
    #     if len(temporal_data) < 2:
    #         return
        
    #     st.markdown("### 📊 Analyse des Tendances")
        
    #     col1, col2, col3 = st.columns(3)
        
    #     # Analyse WEI
    #     if 'WEI' in temporal_data.columns:
    #         wei_trend = temporal_data['WEI'].iloc[-1] - temporal_data['WEI'].iloc[0]
    #         with col1:
    #             if wei_trend > 0.1:
    #                 st.error(f"🔺 **WEI**: Augmentation significative (+{wei_trend:.3f})")
    #             elif wei_trend < -0.1:
    #                 st.success(f"🔻 **WEI**: Diminution significative ({wei_trend:.3f})")
    #             else:
    #                 st.info(f"➡️ **WEI**: Stable ({wei_trend:+.3f})")
        
    #     # Analyse Forêt
    #     if 'forest_percentage' in temporal_data.columns:
    #         forest_trend = temporal_data['forest_percentage'].iloc[-1] - temporal_data['forest_percentage'].iloc[0]
    #         with col3:
    #             if forest_trend > 2:
    #                 st.success(f"🔺 **Forêt**: Croissance (+{forest_trend:.1f}%)")
    #             elif forest_trend < -2:
    #                 st.error(f"🔻 **Forêt**: Perte ({forest_trend:.1f}%)")
    #             else:
    #                 st.info(f"➡️ **Forêt**: Stable ({forest_trend:+.1f}%)")

    def draw_flood_dashboard(self):
        st.markdown("### 🌊 Tableau de Bord Risque d'Inondation")
        flood_stats = get_cached_flood_statistics(
            self.monitoring_system.department_name,
            self.monitoring_system.begining,
            self.monitoring_system.end
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("💧 WEI moyen",
                    f"{flood_stats.get('wei_mean', 0):.3f}",
                    help="Water Extent Index (plus élevé ⇒ plus d'eau)")
        with col2:
            st.metric("🏞️ Surface d'eau",
                    f"{flood_stats.get('water_area_ha', 0):.2f} ha",
                    help="Surface totale d'eau détectée (seuil WEI)")
        with col3:
            st.metric("📊 % Zone en eau",
                    f"{flood_stats.get('flood_percentage', 0):.2f}%",
                    help="Pourcentage de la zone couverte par l'eau (seuil WEI)")

    def draw_forest_dashboard(self):
        """Affiche le tableau de bord forestier avec courbe d'évolution."""
        st.markdown("### 🌳 Tableau de Bord Forestier")
        forest_stats = get_cached_forest_statistics(
            self.monitoring_system.department_name,
            self.monitoring_system.begining,
            self.monitoring_system.end
        )
        col1, col2 = st.columns(2)
        with col1:
            st.metric("🌳 Superficie forestière", 
                    f"{forest_stats.get('forest_area_ha', 0):.2f} ha",
                    help="Surface totale couverte par la forêt")
        with col2:
            st.metric("📊 % Couverture forestière", 
                    f"{forest_stats.get('forest_percentage', 0):.2f}%",
                    help="Pourcentage du territoire couvert par la forêt")
        forest_percentage = forest_stats.get('forest_percentage', 0) or 0
        st.markdown(f"**État de la couverture forestière :** {forest_percentage:.1f}% (plus c’est élevé, plus la zone est boisée).")
        
        st.markdown("#### 📈 Évolution de la Couverture Forestière")
        try:
            forest_df = get_cached_forest_temporal_data(
                self.monitoring_system.department_name,
                self.monitoring_system.begining,
                self.monitoring_system.end
            )
            if not forest_df.empty and 'forest_percentage' in forest_df.columns:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=pd.to_datetime(forest_df['date']), 
                    y=forest_df['forest_percentage'],
                    mode='lines+markers', 
                    name='Couverture forestière (%)',
                    line=dict(color='green', width=3),
                    marker=dict(size=7, color='darkgreen')
                ))
                fig.add_hline(y=60, line_dash="dot", line_color="green", annotation_text="Seuil élevé (60%)")
                fig.add_hline(y=30, line_dash="dot", line_color="orange", annotation_text="Seuil modéré (30%)")
                fig.add_hline(y=10, line_dash="dot", line_color="red", annotation_text="Seuil faible (10%)")
                fig.update_layout(
                    title="Évolution de la couverture forestière dans le temps",
                    xaxis_title="Date",
                    yaxis_title="Couverture forestière (%)",
                    yaxis=dict(range=[0, 100]),
                    showlegend=True,
                    height=400
                )
                st.plotly_chart(fig, width=True)
                # if len(forest_df) > 1:
                #     first_value = float(forest_df['forest_percentage'].iloc[0])
                #     last_value = float(forest_df['forest_percentage'].iloc[-1])
                #     trend = last_value - first_value
                #     if abs(trend) < 0.5:
                #         st.info(f"➡️ **Tendance** : Stable ({trend:+.2f}%)")
                #     elif trend > 0:
                #         st.success(f"📈 **Tendance** : Augmentation (+{trend:.2f}%)")
                #     else:
                #         st.error(f"📉 **Tendance** : Diminution ({trend:.2f}%)")
            else:
                st.info("📊 Données d'évolution forestière en cours de traitement...")
        except Exception as e:
            st.error(f"Erreur lors de l'affichage de l'évolution forestière : {e}")

    def clear_cache_button(self):
        """Bouton pour vider le cache et forcer le rechargement."""
        if st.sidebar.button('🗑️ Vider le cache', key="clear_cache", help="Supprime les données mises en cache pour forcer un nouveau calcul"):
            try:
                st.cache_data.clear()
                st.sidebar.success("Cache vidé ! Rechargement en cours...")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur lors du vidage du cache : {e}")

    # -------------------------
    # Exports / actions
    # -------------------------
    def export_csv_button(self):
        try:
            data = self.monitoring_system.export_data_to_csv()
            if data != "No data available" and data != "Error exporting data":
                st.sidebar.download_button(
                    key="btn_export_csv",
                    label="💾 Exporter données CSV",
                    data=data,
                    file_name=f"donnees_surveillance_{self.monitoring_system.department_name}_{self.monitoring_system.begining}_{self.monitoring_system.end}.csv",
                    mime="text/csv"
                )
            else:
                st.sidebar.error("Aucune donnée à exporter")
        except Exception as e:
            st.sidebar.error(f"Export CSV impossible : {e}")

    def download_maps_button(self):
        if st.sidebar.button('📥 Télécharger rapport', key="btn_export_maps"):
            try:
                with st.spinner("Génération du rapport…"):
                    report = self.monitoring_system.generate_report()
                    st.sidebar.success("Rapport généré!")
                    st.sidebar.text_area("📋 Rapport", value=report, height=200)
            except Exception as e:
                st.sidebar.error(f"Génération impossible : {e}")

    # -------------------------
    # Page principale
    # -------------------------
    def paint(self):

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

        # -----------------
        # Filtres latéraux
        # -----------------
        current_dep = self.monitoring_system.department_name
        try:
            idx = self.list_department_name.index(current_dep)
        except ValueError:
            idx = 0

        sel_dep = st.sidebar.selectbox("🏘️ Département :", self.list_department_name, index=idx, key="sel_dep")
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
                try:
                    self.monitoring_system.setDepartment(sel_dep)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur changement département : {e}")

        # Appliquer changements de dates
        needs_update = False
        if begin_dt != st.session_state["begining"]:
            st.session_state["begining"] = begin_dt
            needs_update = True

        if end_dt != st.session_state["end"]:
            st.session_state["end"] = end_dt
            needs_update = True

        if needs_update:
            with st.spinner("Mise à jour de la période…"):
                try:
                    self.monitoring_system.setBeginingDate(begin_dt.strftime('%Y-%m-%d'))
                    self.monitoring_system.setEndDate(end_dt.strftime('%Y-%m-%d'))
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur mise à jour dates : {e}")

        # -----------------
        # Exports latéraux
        # -----------------
        st.sidebar.markdown("### 📥 Exports & Actions")
        self.export_csv_button()
        self.download_maps_button()
        self.clear_cache_button()

        # -----------------
        # TABS
        # -----------------
        tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Carte Interactive", "📊 Analyse Temporelle", "🌊 Zones en Eau", "🌳 Forêts"])

        with tab1:
            st.markdown("<h2>🗺️ Surveillance Environnementale</h2>", unsafe_allow_html=True)
            col1, col2 = st.columns([3, 1])
            
            with col1:
                self.draw_map()
            
            with col2:
                st.markdown("### 🎛️ État du système")
                st.markdown(f"**📍 Département:** {self.monitoring_system.department_name}")
                date_debut = datetime.strptime(self.monitoring_system.begining, "%Y-%m-%d")
                date_fin = datetime.strptime(self.monitoring_system.end, "%Y-%m-%d")
                date_debut_fr = date_debut.strftime("%d-%m-%Y")
                date_fin_fr = date_fin.strftime("%d-%m-%Y")
                st.markdown(f"**📅 Période:** {date_debut_fr} → {date_fin_fr}")
                
                st.markdown("### 📊 Métriques")
                try:
                    # Utiliser les statistiques complètes avec cache
                    comprehensive_stats = get_cached_comprehensive_statistics(
                        self.monitoring_system.department_name,
                        self.monitoring_system.begining,
                        self.monitoring_system.end
                    )
                    
                    if comprehensive_stats:
                        st.metric("🌳 Superficie forestière", 
                                f"{comprehensive_stats.get('forest_area_ha', 0):.1f} ha")
                        st.metric("💧 WEI moyen", f"{comprehensive_stats.get('wei_mean', 0):.3f}")
                        st.metric("🌊 Zone en eau", 
                                f"{comprehensive_stats.get('water_area_ha', 0):.1f} ha")
                    
                except Exception as e:
                    st.error(f"Erreur calcul métriques : {e}")
                    
                # Bouton pour forcer le rafraîchissement du cache
                if st.button("🔄 Actualiser données", key="refresh_cache"):
                    st.cache_data.clear()
                    st.rerun()

        with tab2:
            st.markdown("<h2>📈 Analyse Temporelle </h2>", unsafe_allow_html=True)
            st.markdown("*Évolution du risque d’inondation (WEI) et de la couverture forestière.*")
            self.draw_graphics()
            
            st.markdown("---")
            st.markdown("### 📋 Guide d'Interprétation des Indicateurs")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown("""
                **🌊 WEI (Water Extent Index)**
                - Indice composite pour les inondations
                - Formule : (1 - NDWI) × MNDWI
                - Seuil critique : 0.3
                - Seuil élevé : 0.7
                """)
            with col2:
                st.markdown("""
                **🌳 Couverture Forestière**
                - Estimée via NDVI et Dynamic World
                - Seuil critique : 10%
                - Seuil modéré : 30%
                - Seuil élevé : 60%
                """)

        with tab3:
            st.markdown("<h2>🌊 Surveillance des Zones en Eau</h2>", unsafe_allow_html=True)
            st.markdown("*Analyse des Risques d'inondations basée sur le Sentinel-2.*")
            self.draw_flood_dashboard()
            
            st.markdown("#### 📈 Évolutions des indices (MNDWI & WEI)")
            self.draw_water_indices_timeseries()
            
            st.markdown("---")
            st.markdown("### 📚 Méthodologie")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
                **🔬 Indices Utilisés**
                - **MNDWI**: `(Green - SWIR1) / (Green + SWIR1)`
                - **NDWI**: `(Green - NIR) / (Green + NIR)`
                - **WEI**: `(1 - NDWI) × MNDWI`
                
                **📊 Seuils d'Interprétation**
                - **> 0.3** : Eau très probable
                - **0 → 0.3** : Eau probable
                - **-0.3 → 0** : Zone sèche
                - **< -0.3** : Très sec
                """)
            with col2:
                st.markdown("""
                **✅ Avantages MNDWI**
                - Moins sensible à la végétation dense
                - Utilise le canal SWIR pour plus de robustesse
                - Meilleure performance en milieu tropical
                - Complémentarité avec données radar
                
                **🎯 Applications**
                - Surveillance continue des zones en eau
                - Suivi des zones humides
                - Cartographie des surfaces en eau
                - Support à la gestion environnementale
                """)

        with tab4:
            st.markdown("<h2>🌳 Monitoring Forestier</h2>", unsafe_allow_html=True)
            st.markdown("*Analyse de la couverture forestière via Dynamic World et NDVI.*")
            self.draw_forest_dashboard()
            
            st.markdown("---")
            st.markdown("### 📚 À propos de Dynamic World et NDVI")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
                **🛰️ Source de Données**
                - Sentinel-2 (10m de résolution)
                - Classification IA (Google Dynamic World)
                - NDVI pour estimation temporelle
                - 9 classes d'occupation du sol
                
                **🌳 Classe 'Trees'**
                - Probabilité 0-1 de présence d'arbres
                - Seuil adaptatif selon région
                - Adapté aux forêts tropicales
                """)
            with col2:
                st.markdown("""
                **📊 Méthodes de Calcul**
                - Masque forestier : probabilité > seuil adaptatif
                - Surface en hectares via pixelArea()
                - Estimation temporelle via NDVI
                - Échelle de traitement : 100m
                
                **🎯 Indicateurs Clés**
                - Surface forestière totale
                - Pourcentage de couverture
                - État de conservation
                - Évolution temporelle estimée
                """)

if __name__ == "__main__":
    app = FrontApp(country_code=COUNTRY_CODE)
    app.paint()
