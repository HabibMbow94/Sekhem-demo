import json
import ee
import folium
from folium import LayerControl
import geemap
# import geemap.foliumap as geemap
from streamlit_folium import st_folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from ipywidgets import interact, widgets
from IPython.display import display
from config import *
import streamlit as st
from branca.element import Element

class FloodMonitoringSystem:
    def __init__(
        self,
        country_code: str = COUNTRY_CODE,
        department_name: str = DEPARTMENT_NAME,
        begin_date: str = (datetime.now() + relativedelta(months=-3)).strftime('%Y-%m-%d'),
        end_date: str = (datetime.now() + relativedelta(days=-1)).strftime('%Y-%m-%d')
    ):
        # --- Initialisation des paramètres ---
        self.country_code = country_code
        self.department_name = department_name
        self.begining = begin_date
        self.end = end_date
        self.project_name = PROJECT_NAME
        
        # --- Seuils et paramètres de classification ---
        self.wei_threshold = 0.3
        self.mndwi_threshold = WATER_THRESHOLD_MNDWI
        self.ndwi_threshold = WATER_THRESHOLD_NDWI
        self.ndbi_threshold = 0.1
        self.ndvi_threshold = 0.4
        self.urban_weight = 3
        
        # --- Connexion à GEE ---
        self.connect_gee()
        
        # --- Récupération du département ---
        self.department = self.get_department(department_name)
        
        # --- Initialisation des datasets ---
        self.fires_dataset = None
        self.temperature_dataset = None
        self.forest_dataset = None
        self.s2_collection = None
        self.s1_collection = None
        
        # --- Initialisation des couches ---
        self.wei_map = None
        self.mndwi_map = None
        self.ndwi_map = None
        self.urban_mask = None
        self.vegetation_mask = None
        self.water_mask = None
        self.flood_risk_map = None
        self.flood_trend = None
        self.permanent_water_mask = None
        self.flood_extent = None
        self.land_cover_map = None
        
        # --- Mise à jour des datasets ---
        self.update_datasets()
        
        # --- Détection des inondations ---
        self.detect_floods()

    # =============================================
    # === CONNEXION ET RÉCUPÉRATION DES DONNÉES ===
    # =============================================
    
    def connect_gee(self):
        """Connexion à Google Earth Engine."""
        try:
            try:
                ee.data.getAssetRoots()
                return
            except Exception:
                pass
            service_account_info = st.secrets["sekhem-earthengine"]

            try:
                service_account_dict = dict(service_account_info)
            except Exception:
                service_account_dict = {k: str(v) for k, v in service_account_info.items()}

            credentials = ee.ServiceAccountCredentials(
                email=service_account_dict["client_email"],
                key_data=json.dumps(service_account_dict)
            )
            ee.Initialize(credentials)
            print("Earth Engine initialisé avec succès!")
        except Exception as e:
            st.error(f"Erreur Earth Engine: {e}")
            raise

    def get_department(self, name: str):
        """Récupère le département depuis le dataset geoBoundaries."""
        return ee.FeatureCollection(DEPARTMENT_DATASET_NAME) \
            .filter(ee.Filter.eq('shapeGroup', self.country_code)) \
            .filter(ee.Filter.eq('shapeName', name))

    def getAllDepartementsName(self):
        """Retourne la liste des noms de tous les départements."""
        try:
            departments = ee.FeatureCollection(DEPARTMENT_DATASET_NAME).filter(
                ee.Filter.eq('shapeGroup', self.country_code)
            )
            return departments.aggregate_array('shapeName').getInfo()
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des départements : {e}")
            return [self.department_name]

    def setDepartment(self, department_name):
        """Change le département actuel."""
        try:
            self.department = self.get_department(department_name)
            self.department_name = department_name
            self.update_datasets()
            self.detect_floods()
        except Exception as e:
            print(f"❌ Erreur lors du changement de département : {e}")

    def setBeginingDate(self, date_str):
        """Change la date de début."""
        try:
            self.begining = date_str
            self.update_datasets()
            self.detect_floods()
        except Exception as e:
            print(f"❌ Erreur lors du changement de la date de début : {e}")

    def setEndDate(self, date_str):
        """Change la date de fin."""
        try:
            self.end = date_str
            self.update_datasets()
            self.detect_floods()
        except Exception as e:
            print(f"❌ Erreur lors du changement de la date de fin : {e}")

    def getBeginingDate(self):
        """Retourne la date de début actuelle."""
        return self.begining

    def getEndDate(self):
        """Retourne la date de fin actuelle."""
        return self.end

    def getDepartmentName(self):
        """Retourne le nom du département actuel."""
        return self.department_name

    def get_image_collection(self, beginning: str, end: str, dataset_name: str):
        """Récupère une collection d'images pour une période donnée."""
        return ee.ImageCollection(dataset_name) \
            .filterBounds(self.department) \
            .filterDate(ee.Date(beginning), ee.Date(end))

    def get_sentinel2_collection(self):
        """Récupère et filtre les images Sentinel-2."""
        return ee.ImageCollection(SENTINEL2_DATASET_NAME) \
            .filterBounds(self.department) \
            .filterDate(self.begining, self.end) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_CLOUD_PERCENTAGE)) \
            .map(self.mask_s2_clouds)

    def mask_s2_clouds(self, image: ee.Image):
        """Masque les nuages pour les images Sentinel-2 en utilisant QA60."""
        qa = image.select('QA60')
        cloud_bit_mask = 1 << 10
        cirrus_bit_mask = 1 << 11
        mask = qa.bitwiseAnd(cloud_bit_mask).eq(0).And(
            qa.bitwiseAnd(cirrus_bit_mask).eq(0)
        )
        return image.updateMask(mask)

    def update_datasets(self):
        """Met à jour tous les datasets."""
        print(STATUS_MESSAGES['processing'])
        self.fires_dataset = self.get_image_collection(self.begining, self.end, FIRES_DATASET_NAME)
        self.temperature_dataset = self.get_image_collection(self.begining, self.end, TEMPERATURE_DATASET_NAME)
        self.forest_dataset = self.get_image_collection(self.begining, self.end, FOREST_DATASET_NAME)
        self.s2_collection = self.get_sentinel2_collection()
        self.s1_collection = self.get_image_collection(self.begining, self.end, SENTINEL1_DATASET_NAME)
        print(STATUS_MESSAGES['completed'])

    # =============================================
    # === CALCUL DES INDICES ET CLASSIFICATION ===
    # =============================================
    
    def calculate_indices(self, image: ee.Image):
        """Calcule les indices NDVI, NDWI, MNDWI, NDBI et WEI."""
        ndvi = image.normalizedDifference([SENTINEL2_NIR_BAND, 'B4']).rename('NDVI')
        ndwi = image.normalizedDifference([SENTINEL2_GREEN_BAND, SENTINEL2_NIR_BAND]).rename('NDWI')
        mndwi = image.normalizedDifference([SENTINEL2_GREEN_BAND, SENTINEL2_SWIR1_BAND]).rename('MNDWI')
        ndbi = image.normalizedDifference([SENTINEL2_SWIR1_BAND, SENTINEL2_NIR_BAND]).rename('NDBI')
        
        # Normalisation pour WEI
        ndwi_norm = ndwi.unitScale(-1, 1)
        mndwi_norm = mndwi.unitScale(-1, 1)
        
        # WEI = (1 - NDWI) × MNDWI
        wei = (ee.Image.constant(1).subtract(ndwi_norm)).multiply(mndwi_norm).rename('WEI')
        
        return image.addBands([ndvi, ndwi, mndwi, ndbi, wei])

    def classify_land_cover(self, s2_median: ee.Image):
        """Classifie l'occupation du sol en 5 classes : eau, urbain, végétation, agriculture, sol nu."""
        water_mask = s2_median.select('MNDWI').gt(self.mndwi_threshold).rename('water_mask')
        urban_mask = s2_median.select('NDBI').gt(self.ndbi_threshold).And(
            s2_median.select('NDVI').lt(0.2)
        ).rename('urban_mask')
        vegetation_mask = s2_median.select('NDVI').gt(self.ndvi_threshold).rename('vegetation_mask')
        agricultural_mask = s2_median.select('NDVI').gt(0.2).And(
            s2_median.select('NDVI').lt(self.ndvi_threshold)
        ).And(
            s2_median.select('NDBI').lt(self.ndbi_threshold)
        ).rename('agricultural_mask')
        bare_soil_mask = s2_median.select('NDVI').lt(0.2).And(
            s2_median.select('NDBI').lt(self.ndbi_threshold)
        ).rename('bare_soil_mask')
        
        # Carte finale
        land_cover = ee.Image.constant(0).rename('land_cover') \
            .where(bare_soil_mask, 1) \
            .where(agricultural_mask, 2) \
            .where(vegetation_mask, 3) \
            .where(urban_mask, 4) \
            .where(water_mask, 5)
        
        return {
            'land_cover': land_cover,
            'water_mask': water_mask,
            'urban_mask': urban_mask,
            'vegetation_mask': vegetation_mask,
            'agricultural_mask': agricultural_mask,
            'bare_soil_mask': bare_soil_mask
        }

    # =============================================
    # === DÉTECTION ET ANALYSE DES INONDATIONS ===
    # =============================================
    
    def detect_floods(self):
        """Détecte les inondations et génère les cartes de risque."""
        if not self.s2_collection or self.s2_collection.size().getInfo() == 0:
            print("❌ Aucune image Sentinel-2 disponible pour la période sélectionnée.")
            return
        
        if not self.department:
            print("❌ Le département n'est pas défini.")
            return
        
        try:
            s2_with_indices = self.s2_collection.map(self.calculate_indices)
            if s2_with_indices.size().getInfo() == 0:
                print("❌ Aucune image valide après calcul des indices.")
                return
            
            s2_median = s2_with_indices.median().clip(self.department)
            
            # Classification de l'occupation du sol
            land_cover_data = self.classify_land_cover(s2_median)
            self.land_cover_map = land_cover_data['land_cover']
            self.water_mask = land_cover_data['water_mask']
            self.urban_mask = land_cover_data['urban_mask']
            self.vegetation_mask = land_cover_data['vegetation_mask']
            
            # Détection des inondations
            self.wei_map = s2_median.select('WEI')
            self.mndwi_map = s2_median.select('MNDWI')
            self.flood_extent = self.wei_map.gt(self.wei_threshold).rename('flood_extent')
            
            # Carte de risque
            self.flood_risk_map = self.wei_map \
                .where(self.wei_map.lte(0.1), 1) \
                .where(self.wei_map.gt(0.1).And(self.wei_map.lte(0.3)), 2) \
                .where(self.wei_map.gt(0.3).And(self.wei_map.lte(0.5)), 3) \
                .where(self.wei_map.gt(0.5).And(self.wei_map.lte(0.7)), 4) \
                .where(self.wei_map.gt(0.7), 5) \
                .rename('flood_risk')
            
            # Prédiction de tendance
            self.flood_trend = self.calculate_flood_trend(s2_with_indices)
            
            print("✅ Détection des inondations terminée.")
            
        except Exception as e:
            print(f"❌ Erreur lors de la détection des inondations : {e}")

    def calculate_flood_trend(self, s2_collection: ee.ImageCollection):
        """Calcule la tendance du WEI pour prédire l'évolution des inondations."""
        if s2_collection.size().getInfo() == 0:
            print("⚠️ Aucune image disponible pour calculer la tendance.")
            return 0.0
        
        try:
            collection_list = s2_collection.toList(s2_collection.size())
            collection_size = s2_collection.size().getInfo()
            
            if collection_size < 3:
                print("⚠️ Pas assez d'images pour calculer une tendance fiable.")
                return 0.0
            
            # Premier tiers des images
            first_third_size = ee.Number(collection_size).divide(3).floor()
            first_third = ee.ImageCollection.fromImages(
                collection_list.slice(0, first_third_size)
            )
            
            # Dernier tiers des images
            last_third_start = ee.Number(collection_size).subtract(first_third_size)
            last_third = ee.ImageCollection.fromImages(
                collection_list.slice(last_third_start, collection_size)
            )
            
            # Calculer la moyenne WEI pour chaque période
            first_wei_mean = first_third.mean().select('WEI').reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            ).get('WEI')
            
            last_wei_mean = last_third.mean().select('WEI').reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            ).get('WEI')
            
            # Calculer la tendance comme différence
            if first_wei_mean is not None and last_wei_mean is not None:
                first_value = ee.Number(first_wei_mean).getInfo()
                last_value = ee.Number(last_wei_mean).getInfo()
                trend = last_value - first_value
                return trend
            else:
                return 0.0
                
        except Exception as e:
            print(f"❌ Erreur lors du calcul de la tendance : {e}")
            return 0.0

    # =============================================
    # === VISUALISATION AMÉLIORÉE ===
    # =============================================
    def show_map(self, show_fires=True, show_temperature=True, show_forest=True, show_water=True):
        # 📍 Centre sur le département
        center = self.department.geometry().centroid().coordinates().getInfo()[::-1]
        m = folium.Map(location=center, zoom_start=10, control_scale=True)
    
        # Fonction utilitaire pour convertir une image EE en couche Folium
        def add_ee_layer(ee_image, vis_params, layer_name):
            map_id_dict = ee.Image(ee_image).getMapId(vis_params)
            folium.TileLayer(
                tiles=map_id_dict['tile_fetcher'].url_format,
                attr="Google Earth Engine",
                name=layer_name,
                overlay=True,
                control=True
            ).add_to(m)
    
        # =====================================
        # 🔥 FEUX DE BROUSSE
        # =====================================
        if show_fires and self.fires_dataset and self.fires_dataset.size().getInfo() > 0:
            fires_frp = self.fires_dataset.select('frp').max().clip(self.department)
            fires_masked = fires_frp.updateMask(fires_frp.gt(5))
            vis = {
                'min': 5, 'max': 50,
                'palette': ['#FFFF00','#FFA500','#FF0000','#800000','#400000']
            }
            add_ee_layer(fires_masked, vis, "🔥 Feux de brousse")
    
        # =====================================
        # 🌡️ TEMPÉRATURE
        # =====================================
        if show_temperature and self.temperature_dataset and self.temperature_dataset.size().getInfo() > 0:
            temp = self.temperature_dataset.median().select('LST_Day_1km').clip(self.department)
            vis = {
                'min': 13000,'max': 16500,
                'palette': ['#0A4D8C','#4FA3D1','#A5E6A3','#FFE066','#FF8C42','#C62828']
            }
            add_ee_layer(temp, vis, "🌡️ Température surface")
    
        # =====================================
        # 🌳 FORÊT
        # =====================================
        if show_forest and self.forest_dataset and self.forest_dataset.size().getInfo() > 0:
            forest = self.forest_dataset.median().select('trees').clip(self.department)
            vis = {
                'min': 0.15, 'max': 0.8,
                'palette': ['#CDEAC0','#7BD389','#2E7D32','#1B5E20','#0B3D0B']
            }
            add_ee_layer(forest, vis, "🌳 Couverture forestière")
    
        # =====================================
        # 🌊 INONDATIONS (WEI)
        # =====================================
        if show_water and self.wei_map:
            water = self.wei_map.clip(self.department).updateMask(self.wei_map.gte(self.wei_threshold))
            vis = {
                'min': 0.05,'max': 0.8,
                'palette': ['#CFEFFF','#8EC9FF','#4EA3FF','#1E7AD9','#0C4A99']
            }
            add_ee_layer(water, vis, f"🌊 Inondations (WEI ≥ {self.wei_threshold})")

        legend_html = '''
        <div id="legend-container" style="position: fixed;
                     bottom: 20px; right: 20px; top: auto; left: auto; width: 300px; height: auto;
                     background-color: white; border: 2px solid #333; z-index: 9999;
                     font-size: 12px; border-radius: 8px;
                     box-shadow: 0 4px 15px rgba(0,0,0,0.3); font-family: Arial, sans-serif;">
            
            <!-- EN-TÊTE -->
            <div id="legend-header" 
                 style="display: flex; align-items: center; justify-content: space-between;
                        padding: 8px 12px; cursor: move; background: linear-gradient(135deg, #f8f9fa, #e9ecef);
                        border-bottom: 1px solid #ddd; border-radius: 6px 6px 0 0;">
                <div style="display: flex; align-items: center;">
                    <span style="font-size: 16px; margin-right: 6px;">🗺️</span>
                    <h4 style="margin: 0; color: #333; font-size: 12px; font-weight: bold;">
                        Surveillance environnementale
                    </h4>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span onclick="
                        event.stopPropagation();
                        var content = this.closest('#legend-container').querySelector('#legend-content');
                        var btn = this;
                        if (content.style.display === 'none') {
                          content.style.display = 'block';
                          btn.innerHTML = '−';
                        } else {
                          content.style.display = 'none';
                          btn.innerHTML = '+';
                        }
                        " style="cursor:pointer;color:#6c757d;font-weight:bold;font-size:14px;">−</span>
                    
                    <span onclick="
                        event.stopPropagation();
                        this.closest('#legend-container').style.display='none';
                        " style="cursor:pointer;color:#dc3545;font-weight:bold;font-size:14px;">✕</span>

                </div>
            </div>
            
            <!-- CONTENU -->
            <div id="legend-content" style="padding: 12px; max-height: 400px; overflow-y: auto;">
                
                <!-- FEUX DE BROUSSE -->
                <div style="margin-bottom: 12px; padding: 8px; border-left: 3px solid #ff6600; background: #fff5f0;">
                    <p style="margin: 2px 0; font-weight: bold; color: #cc4400; font-size: 11px;">
                        🔥 Feux de brousse
                    </p>
                    <p style="margin: 3px 0; font-size: 9px; color: #666; line-height: 1.2;">
                        <strong>FRP</strong> : Intensité énergétique des incendies détectés par satellite.
                    </p>
                    <div style="background: linear-gradient(to right, #ffff00, #ff8000, #ff0000, #800000, #400000);
                                height: 10px; width: 100%; border: 1px solid #ccc; border-radius: 2px; margin: 4px 0;"></div>
                    <div style="display: flex; justify-content: space-between; font-size: 8px; color: #666;">
                        <span>Modéré</span><span>Très intense</span>
                    </div>
                </div>
                
                <!-- TEMPÉRATURE -->
                <div style="margin-bottom: 12px; padding: 8px; border-left: 3px solid #0066cc; background: #f0f8ff;">
                    <p style="margin: 2px 0; font-weight: bold; color: #0066cc; font-size: 11px;">
                        🌡️ Température de surface
                    </p>
                    <p style="margin: 3px 0; font-size: 9px; color: #666; line-height: 1.2;">
                        <strong>LST</strong> : Température du sol mesurée par satellite infrarouge.
                    </p>
                    <div style="background: linear-gradient(to right, #0066cc, #00ccff, #66ff66, #ffff00, #ff6600, #cc0000);
                                height: 10px; width: 100%; border: 1px solid #ccc; border-radius: 2px; margin: 4px 0;"></div>
                    <div style="display: flex; justify-content: space-between; font-size: 8px; color: #666;">
                        <span>Froid (0°C)</span><span>Chaud (50°C)</span>
                    </div>
                </div>
                
                <!-- FORÊT -->
                <div style="margin-bottom: 12px; padding: 8px; border-left: 3px solid #006600; background: #f0fff0;">
                    <p style="margin: 2px 0; font-weight: bold; color: #006600; font-size: 11px;">
                        🌳 Couverture forestière
                    </p>
                    <p style="margin: 3px 0; font-size: 9px; color: #666; line-height: 1.2;">
                        Probabilité de présence d'arbres (0-100%). Analyse satellite des zones boisées.
                    </p>
                    <div style="background: linear-gradient(to right, #90EE90, #66cc66, #339933, #006600, #003300);
                                height: 10px; width: 100%; border: 1px solid #ccc; border-radius: 2px; margin: 4px 0;"></div>
                    <div style="display: flex; justify-content: space-between; font-size: 8px; color: #666;">
                        <span>Peu d'arbres</span><span>Forêt dense</span>
                    </div>
                </div>
                
               <!-- EAU (WEI) -->
                <div style="margin-bottom: 12px; padding: 8px; border-left: 3px solid #1e90ff; background: #f0f8ff;">
                    <p style="margin: 2px 0; font-weight: bold; color: #1e90ff; font-size: 11px;">
                        💧 Zones en eau
                    </p>
                    <p style="margin:3px 0;font-size:9px;color:#666;line-height:1.2;">
                        <strong>WEI</strong> : présence d'eau en surface. Plus la valeur est élevée, plus l'eau est probable.
                    </p>
                    <div style="background: linear-gradient(to right, #e6f2ff, #b3d9ff, #66b2ff, #1e90ff, #003d7a);
                            height: 10px; width: 100%; border: 1px solid #ccc; border-radius: 2px; margin: 4px 0;">
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 8px; color: #666;">
                        <span>Faible</span><span>Fort</span>
                    </div>
                </div>
                
                <hr style="margin: 10px 0; border: 0; border-top: 1px solid #eee;">
                
                <!-- INFORMATIONS TECHNIQUES -->
                <div style="background: #f8f9fa; padding: 8px; border-radius: 4px; margin-top: 8px;">
                    <p style="margin: 0 0 6px 0; font-weight: bold; font-size: 10px; color: #495057;">
                        📊 Informations techniques
                    </p>
                    <div style="font-size: 9px; color: #6c757d; line-height: 1.3;">
                        <p style="margin: 2px 0;"><strong>Période :</strong> ''' + self.begining + ''' → ''' + self.end + '''</p>
                        <p style="margin: 2px 0;"><strong>Département :</strong> ''' + self.department_name + '''</p>
                        <p style="margin: 2px 0;"><strong>Satellites :</strong> Sentinel-2, MODIS, VIIRS</p>
                        <p style="margin: 2px 0;"><strong>Résolution :</strong> 10-1000m selon la couche</p>
                    </div>
                </div>
                
            </div>
        </div>
        
        # <script>
        # (function() {
        #     // Variables pour le drag
        #     let isDragging = false;
        #     let currentX = 0;
        #     let currentY = 0;
        #     let initialX = 0;
        #     let initialY = 0;
            
        #     const container = document.getElementById('legend-container');
        #     const header = document.getElementById('legend-header');
        #     const toggleBtn = document.getElementById('toggle-btn');
        #     const closeBtn = document.getElementById('close-btn');
        #     const content = document.getElementById('legend-content');
            
        #     // ===== BOUTON TOGGLE =====
        #     toggleBtn.addEventListener('click', function(e) {
        #         e.stopPropagation();
        #         e.preventDefault();
                
        #         if (content.style.display === 'none') {
        #             content.style.display = 'block';
        #             toggleBtn.textContent = '−';
        #         } else {
        #             content.style.display = 'none';
        #             toggleBtn.textContent = '+';
        #         }
        #     });
            
        #     // ===== BOUTON CLOSE =====
        #     closeBtn.addEventListener('click', function(e) {
        #         e.stopPropagation();
        #         e.preventDefault();
        #         container.style.display = 'none';
        #     });
            
        #     // ===== DRAG & DROP =====
        #     header.addEventListener('mousedown', function(e) {
        #         // Ne pas démarrer le drag si on clique sur les boutons
        #         if (e.target === toggleBtn || e.target === closeBtn) {
        #             return;
        #         }
                
        #         isDragging = true;
        #         initialX = e.clientX - currentX;
        #         initialY = e.clientY - currentY;
                
        #         header.style.cursor = 'grabbing';
        #     });
            
        #     document.addEventListener('mousemove', function(e) {
        #         if (isDragging) {
        #             e.preventDefault();
        #             currentX = e.clientX - initialX;
        #             currentY = e.clientY - initialY;
                    
        #             container.style.transform = `translate(${currentX}px, ${currentY}px)`;
        #         }
        #     });
            
        #     document.addEventListener('mouseup', function(e) {
        #         if (isDragging) {
        #             isDragging = false;
        #             header.style.cursor = 'move';
        #         }
        #     });
        # })();
        # </script>
        '''
        
        # =====================================
        # 📍 CONTOUR DÉPARTEMENT
        # =====================================
        dept_geojson = self.department.geometry().getInfo()
        folium.GeoJson(
            dept_geojson,
            name=self.department_name,
            style_function=lambda x: {"color": "black", "weight": 2, "fillOpacity": 0}
        ).add_to(m)
    
        # =====================================
        # 🎛️ CONTROLES
        # =====================================
        folium.LayerControl(collapsed=False).add_to(m)
        
        legend = Element(legend_html)
        m.get_root().html.add_child(legend)
        # =====================================
        # 📺 STREAMLIT
        # =====================================
        # Assure-toi que st_folium et folium sont bien importés
        st_folium(m, height=600, width=True)
    
        return m


    # =============================================
    # === MÉTHODES UTILITAIRES CONSERVÉES ===
    # =============================================
    
    def show_trends(self):
        """Affiche les tendances temporelles du WEI, MNDWI et couverture forestière avec Plotly."""
        if not self.s2_collection or self.s2_collection.size().getInfo() == 0:
            print("❌ Aucune donnée disponible pour afficher les tendances.")
            return None
            
        try:
            s2_with_indices = self.s2_collection.map(self.calculate_indices)
            
            def extract_stats(image: ee.Image):
                stats = image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=self.department,
                    scale=STATISTICS_SCALE,
                    maxPixels=MAX_PIXELS
                )
                return ee.Feature(None, {
                    'date': image.date().format('YYYY-MM-dd'),
                    'WEI': stats.get('WEI'),
                    'MNDWI': stats.get('MNDWI'),
                    'NDVI': stats.get('NDVI')
                })
            
            stats_collection = ee.FeatureCollection(s2_with_indices.map(extract_stats))
            df = geemap.ee_to_df(stats_collection)
            
            if df.empty:
                print("❌ Aucune donnée récupérée pour les tendances.")
                return None
            
            # Conversion des dates
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # Créer le graphique avec sous-graphiques
            from plotly.subplots import make_subplots
            
            fig = make_subplots(
                rows=3, cols=1,
                subplot_titles=('Évolution WEI (Inondations)', 'Évolution MNDWI (Zones en eau)', 'Évolution NDVI (Végétation)'),
                vertical_spacing=0.08
            )
            
            # Graphique WEI (Inondations)
            fig.add_trace(
                go.Scatter(
                    x=df['date'], 
                    y=df['WEI'],
                    mode='lines+markers',
                    name='WEI (Inondations)',
                    line=dict(color='red', width=2),
                    marker=dict(size=6)
                ),
                row=1, col=1
            )
            
            # Seuils WEI
            fig.add_hline(y=0.3, line_dash="dash", line_color="orange", 
                         annotation_text="Seuil inondation", row=1, col=1)
            
            # Graphique MNDWI
            fig.add_trace(
                go.Scatter(
                    x=df['date'], 
                    y=df['MNDWI'],
                    mode='lines+markers',
                    name='MNDWI (Zones en eau)',
                    line=dict(color='blue', width=2),
                    marker=dict(size=6)
                ),
                row=2, col=1
            )
            
            # Seuils MNDWI
            fig.add_hline(y=0, line_dash="dash", line_color="red", 
                         annotation_text="Seuil eau", row=2, col=1)
            
            # Graphique NDVI (Végétation)
            fig.add_trace(
                go.Scatter(
                    x=df['date'], 
                    y=df['NDVI'],
                    mode='lines+markers',
                    name='NDVI (Végétation)',
                    line=dict(color='green', width=2),
                    marker=dict(size=6)
                ),
                row=3, col=1
            )
            
            # Seuils NDVI
            fig.add_hline(y=0.4, line_dash="dash", line_color="green", 
                         annotation_text="Seuil végétation dense", row=3, col=1)
            
            fig.update_layout(
                title=f"Évolution Temporelle Multi-Indicateurs ({self.department_name})",
                height=800,
                showlegend=False
            )
            
            # Mise à jour des axes
            fig.update_xaxes(title_text="Date", row=3, col=1)
            fig.update_yaxes(title_text="WEI", row=1, col=1)
            fig.update_yaxes(title_text="MNDWI", row=2, col=1)
            fig.update_yaxes(title_text="NDVI", row=3, col=1)
            
            return fig
            
        except Exception as e:
            print(f"❌ Erreur lors de l'affichage des tendances : {e}")
            return None

    def get_temporal_data_complete(self):
        """Retourne les données temporelles complètes (WEI, MNDWI, NDVI, Forest)."""
        if not self.s2_collection or self.s2_collection.size().getInfo() == 0:
            return pd.DataFrame()
        
        try:
            s2_with_indices = self.s2_collection.map(self.calculate_indices)
            
            def extract_stats(image):
                stats = image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=self.department,
                    scale=100,
                    maxPixels=MAX_PIXELS
                )
                return ee.Feature(None, {
                    'date': image.date().format('YYYY-MM-dd'),
                    'WEI': stats.get('WEI'),
                    'MNDWI': stats.get('MNDWI'),
                    'NDVI': stats.get('NDVI')
                })
            
            # Créer une FeatureCollection
            stats_collection = ee.FeatureCollection(s2_with_indices.map(extract_stats))
            
            # Convertir en DataFrame
            df = geemap.ee_to_df(stats_collection)
            
            # Ajouter simulation de données forestières basée sur NDVI
            if not df.empty and 'NDVI' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.sort_values('date')
                
                # Estimer couverture forestière basée sur NDVI et données Dynamic World
                base_forest = 45.0  # Pourcentage de base estimé
                df['forest_percentage'] = base_forest + (df['NDVI'] * 30) + (df.index * 0.1) - (df.index * 0.12)
                df['forest_percentage'] = df['forest_percentage'].clip(0, 100)
            
            return df
                
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des données temporelles complètes : {e}")
            return pd.DataFrame()

    def get_flood_statistics(self):
        """Retourne les statistiques de l'eau/ inondations basées sur WEI (et non MNDWI)."""
        if not hasattr(self, 'wei_map') or self.wei_map is None:
            return {
                'wei_mean': 0.0,
                'water_area_ha': 0.0,
                'flood_percentage': 0.0
            }

        try:
            # Moyenne de WEI sur le département
            wei_stats = self.wei_map.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            )
            wei_mean = wei_stats.get('WEI')
            wei_value = ee.Number(wei_mean).getInfo() if wei_mean is not None else 0.0

            # Surface en eau (seuil WEI)
            water_mask_wei = self.wei_map.gte(self.wei_threshold).rename('water_from_wei')
            water_area_stats = water_mask_wei.multiply(ee.Image.pixelArea()).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            )
            water_area_result = water_area_stats.get('water_from_wei')
            water_area = ee.Number(water_area_result).getInfo() if water_area_result is not None else 0.0

            # Surface totale
            total_area_stats = ee.Image.pixelArea().reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            )
            total_area_result = total_area_stats.get('area')
            total_area = ee.Number(total_area_result).getInfo() if total_area_result is not None else 1.0

            # conversions
            water_area_ha = water_area / 10000 if water_area > 0 else 0.0
            total_area_ha = total_area / 10000 if total_area > 0 else 1.0
            flood_percentage = (water_area_ha / total_area_ha) * 100 if total_area_ha > 0 else 0.0

            return {
                'wei_mean': float(wei_value),
                'water_area_ha': water_area_ha,
                'flood_percentage': flood_percentage
            }

        except Exception as e:
            print(f"❌ Erreur lors de la récupération des statistiques (WEI) : {e}")
            return {
                'wei_mean': 0.0,
                'water_area_ha': 0.0,
                'flood_percentage': 0.0
            }

    def get_forest_statistics(self):
        """Retourne les statistiques de la couverture forestière."""
        if not self.forest_dataset or self.forest_dataset.size().getInfo() == 0:
            return {
                'forest_area_ha': 0.0,
                'forest_percentage': 0.0
            }
        
        try:
            forest_prob = self.forest_dataset.median().select('trees')
            
            # Diagnostic: calculer les statistiques de probabilité forestière
            forest_stats_diag = forest_prob.reduceRegion(
                reducer=ee.Reducer.minMax().combine(ee.Reducer.mean(), None, True),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            )
            
            print(f"🌳 Diagnostic forestier:")
            trees_min = trees_max = trees_mean = 0.0
            try:
                trees_min_val = forest_stats_diag.get('trees_min')
                trees_max_val = forest_stats_diag.get('trees_max') 
                trees_mean_val = forest_stats_diag.get('trees_mean')
                
                if trees_min_val is not None:
                    trees_min = ee.Number(trees_min_val).getInfo()
                    print(f"   - Probabilité min: {trees_min:.3f}")
                if trees_max_val is not None:
                    trees_max = ee.Number(trees_max_val).getInfo()
                    print(f"   - Probabilité max: {trees_max:.3f}")
                if trees_mean_val is not None:
                    trees_mean = ee.Number(trees_mean_val).getInfo()
                    print(f"   - Probabilité moyenne: {trees_mean:.3f}")
            except Exception as e:
                print(f"   - Erreur diagnostic: {e}")
            
            # Seuil adaptatif basé sur la moyenne régionale
            if trees_mean > 0.4:
                forest_threshold = 0.5  # Zone forestière dense
            elif trees_mean > 0.2:
                forest_threshold = 0.3  # Zone de transition
            else:
                forest_threshold = 0.15  # Zone semi-aride/sahélienne
                        
            print(f"   - Seuil adaptatif utilisé: {forest_threshold}")
                    
            forest_mask = forest_prob.gt(forest_threshold)
            
            # Calculer la surface forestière
            forest_area_result = forest_mask.multiply(ee.Image.pixelArea()).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            ).get('trees')
            
            # Calculer la surface totale
            total_area_result = ee.Image.pixelArea().reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=100,
                maxPixels=MAX_PIXELS
            ).get('area')
            
            # Conversion en hectares et calculs
            forest_area = ee.Number(forest_area_result).getInfo() if forest_area_result is not None else 0.0
            total_area = ee.Number(total_area_result).getInfo() if total_area_result is not None else 1.0
            
            forest_area_ha = (forest_area / 10000) if forest_area > 0 else 0.0
            total_area_ha = (total_area / 10000) if total_area > 0 else 1.0
            
            # Calculer le pourcentage de couverture forestière
            forest_percentage = (forest_area_ha / total_area_ha) * 100 if total_area_ha > 0 else 0.0
            
            print(f"🌳 Résultats:")
            print(f"   - Surface forestière: {forest_area_ha:.2f} ha")
            print(f"   - Surface totale: {total_area_ha:.2f} ha") 
            print(f"   - Couverture forestière: {forest_percentage:.2f}%")
            
            return {
                'forest_area_ha': forest_area_ha,
                'forest_percentage': forest_percentage
            }
                
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des statistiques forestières : {e}")
            return {
                'forest_area_ha': 0.0,
                'forest_percentage': 0.0
            }

    def get_flood_temporal_data(self):
        """Retourne un DF avec MNDWI et WEI (si disponibles)."""
        if not self.s2_collection or self.s2_collection.size().getInfo() == 0:
            return pd.DataFrame()

        try:
            s2_with_indices = self.s2_collection.map(self.calculate_indices)

            def extract_stats(image):
                stats = image.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=self.department,
                    scale=100,
                    maxPixels=MAX_PIXELS
                )
                return ee.Feature(None, {
                    'date': image.date().format('YYYY-MM-dd'),
                    'MNDWI': stats.get('MNDWI'),
                    'WEI': stats.get('WEI')
                })

            stats_collection = ee.FeatureCollection(s2_with_indices.map(extract_stats))
            df = geemap.ee_to_df(stats_collection)
            return df

        except Exception as e:
            print(f"❌ Erreur lors de la récupération des données temporelles : {e}")
            return pd.DataFrame()

    def generate_report(self):
        """Génère un rapport textuel simplifié sans alertes."""
        trend_text = '↑ Augmentation' if self.flood_trend > 0 else '↓ Diminution' if self.flood_trend < 0 else '→ Stable'
        
        flood_stats = self.get_flood_statistics()
        forest_stats = self.get_forest_statistics()
        
        report = f"""=== RAPPORT DE SURVEILLANCE ENVIRONNEMENTALE ===

**Département** : {self.department_name}
**Période d'analyse** : {self.begining} → {self.end}

**ZONES EN EAU (WEI)**
- Indice WEI moyen : {flood_stats['wei_mean']:.3f}
- Surface en eau : {flood_stats['water_area_ha']:.1f} hectares
- Pourcentage du territoire : {flood_stats['flood_percentage']:.2f}%
- Tendance : {trend_text}

**COUVERTURE FORESTIÈRE**
- Surface forestière : {forest_stats['forest_area_ha']:.1f} hectares  
- Couverture forestière : {forest_stats['forest_percentage']:.2f}%

**RECOMMANDATIONS**
- Surveillance continue des zones en eau identifiées
- Monitoring de l'évolution de la couverture forestière
- Analyse comparative avec les années précédentes recommandée
"""
        return report

    # =============================================
    # === INTERFACE INTERACTIVE ===
    # =============================================
    
    def interactive_widget(self):
        """Crée un widget interactif pour sélectionner une période et recharger les données."""
        date_range = widgets.DatePickerRange(
            value=(datetime.strptime(self.begining, '%Y-%m-%d'), datetime.strptime(self.end, '%Y-%m-%d')),
            description='Période',
            disabled=False
        )
        button = widgets.Button(description="Recharger les données")
        output = widgets.Output()
        
        def on_button_click(b):
            with output:
                new_begin = date_range.value[0].strftime('%Y-%m-%d')
                new_end = date_range.value[1].strftime('%Y-%m-%d')
                self.update_dates(new_begin, new_end)
                self.show_map()
                self.show_trends()
                print(self.generate_report())
        
        button.on_click(on_button_click)
        display(date_range, button, output)

    def update_dates(self, new_begin: str, new_end: str):
        """Met à jour les dates et recalcule les données."""
        self.begining = new_begin
        self.end = new_end
        self.update_datasets()
        self.detect_floods()
        print(f"✅ Données mises à jour pour {new_begin} → {new_end}")
        
    def export_data_to_csv(self):
        """Exporte les données en CSV."""
        try:
            flood_df = self.get_flood_temporal_data()
            if flood_df.empty:
                return "No data available"
            csv_data = flood_df.to_csv(index=False)
            return csv_data
        except Exception as e:
            print(f"❌ Erreur lors de l'export des données : {e}")
            return "Error exporting data"
            
    def get_comprehensive_statistics(self):
        """Retourne toutes les statistiques : inondations, forêts, etc."""
        flood_stats = self.get_flood_statistics()
        forest_stats = self.get_forest_statistics()
        
        return {
            **flood_stats,
            **forest_stats,
            'department_name': self.department_name,
            'period': f"{self.begining} to {self.end}",
            'trend_value': self.flood_trend if hasattr(self, 'flood_trend') else 0.0
        }
