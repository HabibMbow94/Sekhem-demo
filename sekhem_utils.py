import os
import io
from datetime import datetime, timedelta

import ee, json
import folium
import pandas as pd
import streamlit as st
import geemap
import geemap.foliumap as geemap_f
from geemap import cartoee

from dateutil.relativedelta import relativedelta

from config import (
    DEPARTMENT_DATASET_NAME,
    DEPARTMENT_NAME,
    COUNTRY_CODE,

    # Datasets
    FIRES_DATASET_NAME,
    TEMPERATURE_DATASET_NAME,
    FOREST_DATASET_NAME,
    SENTINEL2_DATASET_NAME,
    SENTINEL1_DATASET_NAME,

    # Bandes
    FIRES_SELECTED_BAND,
    TEMPERATURE_SELECTED_BAND,
    FOREST_SELECTED_BAND,
    CLASS_NAMES,
    SE2_BANDS,

    # Viz
    FIRES_VISUALIZATION,
    TEMPERATURE_VISUALIZATION,
    FOREST_VISUALIZATION,
    MNDWI_VISUALIZATION,
    NDWI_VISUALIZATION,
    WATER_MASK_VISUALIZATION,
    FLOOD_RISK_VISUALIZATION,
    CHANGE_VISUALIZATION,
    SAR_VV_VISUALIZATION,

    # Paramètres
    MAX_PIXELS,
    PROCESSING_SCALE,
    STATISTICS_SCALE,
    MAX_CLOUD_PERCENTAGE,
    FALLBACK_CLOUD_PERCENTAGE,
    WATER_THRESHOLD_MNDWI,
    WATER_THRESHOLD_NDWI,

    # Export
    EXPORT_FOLDER,
    FLOOD_MAPS_FOLDER,
    FIRE_MAPS_FOLDER,
    FOREST_MAPS_FOLDER,
)

# Nouveaux paramètres pour la classification améliorée
NDBI_THRESHOLD = 0.1  # Seuil pour zones urbaines
NDVI_THRESHOLD = 0.4  # Seuil pour végétation
URBAN_WEIGHT = 3  # Pondération des inondations urbaines

# Fenêtre par défaut (12 derniers mois, J-1)
BEGIN_DEFAULT = (datetime.now() + relativedelta(months=-12)).strftime('%Y-%m-%d')
END_DEFAULT   = (datetime.now() + relativedelta(days=-1)).strftime('%Y-%m-%d')


class Utils:
    """Utilitaires GEE : feux, LST, DynamicWorld, détection inondations avancée avec distinction éléments."""

    def __init__(self, country_code='SEN'):
        self.country_code = country_code or COUNTRY_CODE

        self.fires_vis = FIRES_VISUALIZATION
        self.temperature_vis = TEMPERATURE_VISUALIZATION
        self.tree_vis = FOREST_VISUALIZATION
        self.flood_vis = MNDWI_VISUALIZATION
        self.water_vis = WATER_MASK_VISUALIZATION
        self.flood_risk_vis = FLOOD_RISK_VISUALIZATION
        self.sar_vv_vis = SAR_VV_VISUALIZATION

        self.land_cover_vis = {
            'min': 0, 'max': 4,
            'palette': ['#D2B48C', '#228B22', '#FF6347', '#4169E1', '#800080']
        }
        self.urban_flood_vis = {'palette': ['#FF0000']}
        self.rural_flood_vis = {'palette': ['#FFA500']}
        self.normal_rivers_vis = {'palette': ['#0000FF']}

        self.connect()
        self.department = self.get_department_with_coordinates(DEPARTMENT_NAME)

        self.begining = BEGIN_DEFAULT
        self.end = END_DEFAULT

        self.update_datasets()

        self._ensure_export_dirs()

        self.classified_cart = None
        self.classified_rf = None
        self.flood_risk_map = None
        self.flood_alert_level = 0
        self.mndwi_current = None
        self.ndwi_current = None
        self.water_extent = None
        self.flood_probability = None
        self.mndwi_change = None
        self.flood_change_areas = None
        self.forest_area_ha = ee.Number(0)

        self.permanent_water_mask = None
        self.urban_mask = None
        self.vegetation_mask = None
        self.river_network = None
        self.land_cover_map = None
        self.normal_rivers = None
        self.flood_areas = None
        self.urban_flooding = None
        self.rural_flooding = None
        self.agricultural_flooding = None
        self.forest_flooding = None
        self.enhanced_alert_info = None

        self.classification()
        self.enhanced_flood_analysis()

    # ----------------- GEE -----------------
    def connect(self):
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

    def getAllDepartments(self):
        return ee.FeatureCollection(DEPARTMENT_DATASET_NAME).filter(
            ee.Filter.eq('shapeGroup', self.country_code)
        )

    def getDepartment(self, departmentName):
        return self.getAllDepartments().filter(ee.Filter.eq('shapeName', departmentName))

    def getAllDepartementsName(self):
        return self.getAllDepartments().aggregate_array('shapeName').getInfo()

    def get_department_with_coordinates(self, name):
        return self.getAllDepartments().filter(ee.Filter.eq('shapeName', name))

    def getDepartmentName(self):
        try:
            return self.department.aggregate_array('shapeName').getInfo()[0]
        except Exception:
            return "Unknown Department"

    def setDepartment(self, dptName):
        try:
            self.department = self.get_department_with_coordinates(dptName)
            self.update_datasets()
            self.classification()
            self.enhanced_flood_analysis()
        except Exception as e:
            print(f"[setDepartment] {e}")

    def setBeginingDate(self, date_str):
        self._set_date('begining', date_str)

    def setEndDate(self, date_str):
        self._set_date('end', date_str)

    def _set_date(self, which, date_str):
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            setattr(self, which, date_str)
            self.update_datasets()
            self.classification()
            self.enhanced_flood_analysis()
        except ValueError:
            print(f"[date] Format invalide: {date_str} (YYYY-MM-DD)")
        except Exception as e:
            print(f"[date] {e}")

    def getBeginingDate(self):
        return self.begining

    def getEndDate(self):
        return self.end

    def get_image_collection(self, beginning, end, dataset_name):
        """Filtre robuste ; étend le début si vide."""
        try:
            col = ee.ImageCollection(dataset_name).filterBounds(self.department)
            if beginning and end:
                col = col.filterDate(ee.Date(beginning), ee.Date(end))
                if col.size().getInfo() == 0:
                    ext_begin = (datetime.strptime(beginning, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
                    col2 = (ee.ImageCollection(dataset_name)
                            .filterBounds(self.department)
                            .filterDate(ext_begin, ee.Date(end)))
                    if col2.size().getInfo() > 0:
                        return col2
            return col
        except Exception as e:
            print(f"[get_image_collection] {dataset_name}: {e}")
            return ee.ImageCollection([])

    def update_datasets(self):
        print("[datasets] update …")
        self.fires_dataset = self.get_image_collection(self.begining, self.end, FIRES_DATASET_NAME)
        self.temperature_dataset = self.get_image_collection(self.begining, self.end, TEMPERATURE_DATASET_NAME)
        self.forest_dataset = self.get_image_collection(self.begining, self.end, FOREST_DATASET_NAME)

    # ----------------- Sentinel‑2 -----------------
    def mask_s2_clouds_QA60(self, img):
        """Masque nuages/cirrus via QA60 si disponible ; sinon renvoie l'image."""
        try:
            qa = img.select('QA60')
            cloudBitMask = 1 << 10
            cirrusBitMask = 1 << 11
            mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
            return img.updateMask(mask)
        except Exception:
            return img

    def get_sentinel2_collection(self):
        try:
            s2 = (ee.ImageCollection(SENTINEL2_DATASET_NAME)
                  .filterBounds(self.department)
                  .filterDate(self.begining, self.end)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_CLOUD_PERCENTAGE))
                  .map(self.mask_s2_clouds_QA60))
            if s2.size().getInfo() == 0:
                ext_begin = (datetime.strptime(self.begining, '%Y-%m-%d') - timedelta(days=60)).strftime('%Y-%m-%d')
                s2 = (ee.ImageCollection(SENTINEL2_DATASET_NAME)
                      .filterBounds(self.department)
                      .filterDate(ext_begin, self.end)
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', FALLBACK_CLOUD_PERCENTAGE))
                      .map(self.mask_s2_clouds_QA60))
            return s2
        except Exception as e:
            print(f"[get_sentinel2_collection] {e}")
            return ee.ImageCollection([])

    # ----------------- Indices calculés -----------------
    @staticmethod
    def _ratio(a, b):
        return a.subtract(b).divide(a.add(b))

    def calculate_indices(self, img):
        try:
            b2 = img.select('B2').divide(10000)
            b3 = img.select('B3').divide(10000)
            b4 = img.select('B4').divide(10000)
            b8 = img.select('B8').divide(10000)
            b11 = img.select('B11').divide(10000) # SWIR1
            b12 = img.select('B12').divide(10000) # SWIR2
            
            # Indices d'eau (existants)
            mndwi = self._ratio(b3, b11).rename('MNDWI')
            ndwi = self._ratio(b3, b8).rename('NDWI')
            
            # Nouveaux indices
            ndvi = self._ratio(b8, b4).rename('NDVI')  # Végétation
            ndbi = self._ratio(b11, b8).rename('NDBI')  # Bâti/urbain
            nbsi = self._ratio(b11.add(b4), b8.add(b2)).rename('NBSI')  # Sol nu
            
            return img.addBands([mndwi, ndwi, ndvi, ndbi, nbsi])
            
        except Exception as e:
            print(f"[Enhanced indices] {e}")
            return img

    def calculate_mndwi(self, img):
        try:
            g = img.select('B3').divide(10000)
            s1 = img.select('B11').divide(10000)
            mndwi = self._ratio(g, s1).rename('MNDWI')
            return img.addBands(mndwi)
        except Exception as e:
            print(f"[MNDWI] {e}")
            return img

    def calculate_ndwi(self, img):
        try:
            g = img.select('B3').divide(10000)
            nir = img.select('B8').divide(10000)
            ndwi = self._ratio(g, nir).rename('NDWI')
            return img.addBands(ndwi)
        except Exception as e:
            print(f"[NDWI] {e}")
            return img

    # ----------------- Masques de référence -----------------
    def create_reference_masks(self):
        """Crée les masques de référence pour différents types de surfaces."""
        try:
            print("[Reference masks] Création des masques de référence...")
            
            try:
                jrc_water = ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
                self.permanent_water_mask = jrc_water.select('occurrence').gt(50).clip(self.department)
                print("[Reference masks] Eaux permanentes JRC chargées")
            except Exception as e:
                print(f"[Reference masks] JRC Water error: {e}")
                self.permanent_water_mask = None
            
            try:
                ghsl = ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2020").clip(self.department)
                ghsl_single = ghsl.reduce(ee.Reducer.max()).rename('ghsl_built_max')
                self.urban_mask = ghsl_single.gt(0).rename('urban_ref')
                print("[Reference masks] Zones urbaines GHSL chargées (single-band)")
            except Exception as e:
                print(f"[Reference masks] GHSL error: {e}, utilisation fallback NDBI")
                self.urban_mask = None

            try:
                hydrosheds = ee.FeatureCollection("WWF/HydroSHEDS/v1/FreeFlowingRivers")
                self.river_network = hydrosheds.filterBounds(self.department)
                print("[Reference masks] Réseau hydrographique HydroSHEDS chargé")
            except Exception as e:
                print(f"[Reference masks] HydroSHEDS error: {e}")
                self.river_network = None
                
        except Exception as e:
            print(f"[Reference masks] {e}")

    def classify_land_cover(self, s2_median):
        try:
            mndwi = s2_median.select('MNDWI')
            ndwi = s2_median.select('NDWI')
            ndvi = s2_median.select('NDVI')
            ndbi = s2_median.select('NDBI')

            water_mask = mndwi.gt(WATER_THRESHOLD_MNDWI).And(ndwi.gt(WATER_THRESHOLD_NDWI))

            if self.urban_mask is None:
                urban_mask = ndbi.gt(NDBI_THRESHOLD).And(ndvi.lt(0.2))
            else:
                urban_mask = ee.Image(self.urban_mask).select([0]).rename('urban_ref_single')

            vegetation_mask = ndvi.gt(NDVI_THRESHOLD)
            self.vegetation_mask = vegetation_mask
  
            agricultural_mask = ndvi.gt(0.2).And(ndvi.lt(NDVI_THRESHOLD)).And(ndbi.lt(NDBI_THRESHOLD))

            bare_soil_mask = ndvi.lt(0.2).And(ndbi.lt(NDBI_THRESHOLD))

            land_cover = (ee.Image(0)  # Sol nu par défaut
                         .where(bare_soil_mask, 0)
                         .where(agricultural_mask, 1)
                         .where(vegetation_mask, 2)
                         .where(urban_mask, 3)
                         .where(water_mask, 4)
                         ).rename('land_cover')
            
            self.land_cover_map = land_cover
            
            return {
                'land_cover': land_cover,
                'water': water_mask,
                'urban': urban_mask,
                'vegetation': vegetation_mask,
                'agricultural': agricultural_mask,
                'bare_soil': bare_soil_mask
            }
            
        except Exception as e:
            print(f"[Land cover classification] {e}")
            return None

    def detect_flood_vs_normal_water(self, current_water):
        """Distingue les inondations des cours d'eau normaux."""
        try:
            if self.permanent_water_mask is None:
                print("[Flood detection] Création d'un masque d'eau de référence approximatif...")
                try:
                    dem = ee.Image("USGS/SRTMGL1_003").clip(self.department)
                    slope = ee.Terrain.slope(dem)
                    self.permanent_water_mask = current_water.And(slope.lt(2))
                except Exception as dem_e:
                    print(f"[Flood detection] DEM error: {dem_e}")
                    erosion_radius = 2
                    eroded_water = current_water.focal_min(erosion_radius, 'circle', 'pixels')
                    self.permanent_water_mask = eroded_water

            self.normal_rivers = current_water.And(self.permanent_water_mask).rename('normal_rivers')

            self.flood_areas = current_water.And(self.permanent_water_mask.Not()).rename('flood_areas')
            
            print(f"[Flood detection] Distinction eau normale/inondations effectuée")
            
            return {
                'normal_water': self.normal_rivers,
                'flood_areas': self.flood_areas
            }
            
        except Exception as e:
            print(f"[Flood vs normal water] {e}")
            return None

    def analyze_flood_by_land_use(self, flood_areas, land_cover_masks):
        try:
            urban_mask = ee.Image(land_cover_masks['urban']).select([0]).rename('urban_ref_single')
            veg_mask   = ee.Image(land_cover_masks['vegetation']).select([0])
            agri_mask  = ee.Image(land_cover_masks['agricultural']).select([0])

            self.urban_flooding = flood_areas.And(urban_mask).select([0]).rename('urban_flooding')
            self.rural_flooding = flood_areas.And(urban_mask.Not()).select([0]).rename('rural_flooding')
            self.agricultural_flooding = flood_areas.And(agri_mask).select([0]).rename('agricultural_flooding')
            self.forest_flooding = flood_areas.And(veg_mask).select([0]).rename('forest_flooding')

            print("[Flood by land use] Analyse par type d'occupation terminée")
            return {
                'urban_flooding': self.urban_flooding,
                'rural_flooding': self.rural_flooding,
                'agricultural_flooding': self.agricultural_flooding,
                'forest_flooding': self.forest_flooding
            }
        except Exception as e:
            print(f"[Flood by land use] {e}")
            return None


    def calculate_enhanced_statistics(self, flood_by_landuse):
    
        """Calcule des statistiques détaillées par type d'inondation (ha) + risque pondéré."""

        try:
            stats = {}
            for flood_type, mask in flood_by_landuse.items():
                try:
                    band_name = flood_type
                    area_image = (
                        mask.unmask(0)
                            .rename(band_name)
                            .selfMask()
                            .multiply(ee.Image.pixelArea())
                    )
                    area_dict = area_image.reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=self.department,
                        scale=STATISTICS_SCALE,
                        maxPixels=MAX_PIXELS
                    )
                    area_m2 = ee.Number(
                        ee.Algorithms.If(
                            area_dict.contains(band_name),
                            ee.Algorithms.If(area_dict.get(band_name), area_dict.get(band_name), 0),
                            0
                        )
                    )
                    stats[flood_type] = area_m2.divide(10000)  # ha

                except Exception as stat_e:
                    print(f"[Enhanced stats] Error for {flood_type}: {stat_e}")
                    stats[flood_type] = ee.Number(0)

            urban_area = stats.get('urban_flooding', ee.Number(0))
            rural_area = stats.get('rural_flooding', ee.Number(0))
            agricultural_area = stats.get('agricultural_flooding', ee.Number(0))
            forest_area = stats.get('forest_flooding', ee.Number(0))

            weighted_risk = (
                urban_area.multiply(URBAN_WEIGHT)
                .add(agricultural_area.multiply(1.5))
                .add(rural_area)
                .add(forest_area.multiply(0.5))

            )

            return stats, weighted_risk

        except Exception as e:
            print(f"[Enhanced statistics] {e}")
            return {}, ee.Number(0)
 

    def generate_enhanced_alert_system(self, stats, weighted_risk):
        """Système d'alerte amélioré basé sur le type d'inondation."""
        try:
            # Récupération des valeurs
            urban_flood_ha = stats.get('urban_flooding', ee.Number(0)).getInfo()
            rural_flood_ha = stats.get('rural_flooding', ee.Number(0)).getInfo()
            agricultural_flood_ha = stats.get('agricultural_flooding', ee.Number(0)).getInfo()
            forest_flood_ha = stats.get('forest_flooding', ee.Number(0)).getInfo()
            weighted_risk_val = weighted_risk.getInfo()

            alert_level = 0
            alert_message = "Aucune inondation significative détectée"
            priority_zones = []
            
            if urban_flood_ha > 1000: 
                alert_level = 4
                alert_message = "ALERTE ROUGE : Inondations urbaines majeures"
                priority_zones.append("zones urbaines critiques")
            elif urban_flood_ha > 500:
                alert_level = 3
                alert_message = "ALERTE ORANGE : Inondations urbaines importantes"
                priority_zones.append("zones urbaines")
            elif urban_flood_ha > 100:
                alert_level = 2
                alert_message = "ALERTE JAUNE : Inondations urbaines modérées"
                priority_zones.append("zones urbaines localisées")
            elif urban_flood_ha > 10:
                alert_level = 1
                alert_message = "VIGILANCE : Inondations urbaines mineures détectées"
                priority_zones.append("quelques zones urbaines")
            elif agricultural_flood_ha > 5000 or rural_flood_ha > 10000:
                alert_level = 1
                alert_message = "VIGILANCE : Inondations importantes en zones rurales/agricoles"
                if agricultural_flood_ha > 5000:
                    priority_zones.append("zones agricoles")
                if rural_flood_ha > 10000:
                    priority_zones.append("zones rurales")
            
            # Mise à jour pour compatibilité avec le système existant
            self.flood_alert_level = alert_level
            
            return {
                'alert_level': alert_level,
                'alert_message': alert_message,
                'urban_flood_ha': round(urban_flood_ha, 2),
                'rural_flood_ha': round(rural_flood_ha, 2),
                'agricultural_flood_ha': round(agricultural_flood_ha, 2),
                'forest_flood_ha': round(forest_flood_ha, 2),
                'weighted_risk': round(weighted_risk_val, 2),
                'priority_zones': priority_zones,
                'total_flood_ha': round(urban_flood_ha + rural_flood_ha + agricultural_flood_ha + forest_flood_ha, 2)
            }
            
        except Exception as e:
            print(f"[Enhanced alert] {e}")
            return {
                'alert_level': 0, 
                'alert_message': 'Erreur de calcul des alertes',
                'urban_flood_ha': 0, 'rural_flood_ha': 0,
                'agricultural_flood_ha': 0, 'forest_flood_ha': 0,
                'weighted_risk': 0, 'priority_zones': [],
                'total_flood_ha': 0
            }

    # ----------------- Analyse inondations améliorée -----------------
    def enhanced_flood_analysis(self):
        """Analyse complète avec distinction des éléments."""
        try:
            
            # 1. Obtenir les données Sentinel-2
            s2 = self.get_sentinel2_collection()
            
            # 2. Calculer tous les indices
            s2_with_indices = s2.map(self.calculate_indices)
            s2_median = s2_with_indices.median().clip(self.department)
            
            self.mndwi_current = s2_median.select('MNDWI')
            self.ndwi_current = s2_median.select('NDWI')

            self.create_reference_masks()

            land_cover_data = self.classify_land_cover(s2_median)
            self.water_extent = land_cover_data['water'].rename('water_mask')
            water_analysis = self.detect_flood_vs_normal_water(land_cover_data['water'])

            flood_by_landuse = self.analyze_flood_by_land_use(
                water_analysis['flood_areas'], 
                land_cover_data
            )

            stats, weighted_risk = self.calculate_enhanced_statistics(flood_by_landuse)

            self.enhanced_alert_info = self.generate_enhanced_alert_system(stats, weighted_risk)

            self.maintain_legacy_compatibility()

            self.generate_flood_risk_map()
            self.temporal_flood_analysis(s2_with_indices)
            
            print(f"[Enhanced flood analysis] Terminée - Niveau d'alerte: {self.enhanced_alert_info['alert_level']}")
            
        except Exception as e:
            print(f"[Enhanced flood analysis] {e} - Fallback vers analyse classique")

    def maintain_legacy_compatibility(self):
        """Maintient la compatibilité avec l'ancien système."""
        try:
            if self.enhanced_alert_info and self.water_extent is not None:
                total_flood_ha = self.enhanced_alert_info['total_flood_ha']

                total_area = ee.Image.pixelArea().reduceRegion(
                    reducer=ee.Reducer.sum(),
                    geometry=self.department,
                    scale=STATISTICS_SCALE,
                    maxPixels=MAX_PIXELS
                )
                total_ha = ee.Number(total_area.get('area')).divide(10000)
                
                self.water_area_ha = ee.Number(total_flood_ha)
                self.flood_percentage = self.water_area_ha.divide(total_ha).multiply(100)
                
        except Exception as e:
            print(f"[Legacy compatibility] {e}")

    # ----------------- Sentinel‑1 (fallback) -----------------
    def get_s1_water_mask(self):
        """Détection eau via S1 (VV en dB < -18)."""
        try:
            s1 = (ee.ImageCollection(SENTINEL1_DATASET_NAME)
                  .filterBounds(self.department)
                  .filterDate(self.begining, self.end)
                  .filter(ee.Filter.eq('instrumentMode', 'IW'))
                  .select(['VV']))
            if s1.size().getInfo() == 0:
                return None
            vv_db = s1.median().select('VV').log10().multiply(10)
            return vv_db.lt(-18).rename('water_mask')
        except Exception as e:
            print(f"[S1 water] {e}")
            return None

    def _compute_water_stats_from_mask(self, water_mask):
        try:
            water_area = water_mask.multiply(ee.Image.pixelArea()).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=STATISTICS_SCALE,
                maxPixels=MAX_PIXELS
            )
            total_area = ee.Image.pixelArea().reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=STATISTICS_SCALE,
                maxPixels=MAX_PIXELS
            )
            water_ha = ee.Number(water_area.get('water_mask')).divide(10000)
            total_ha = ee.Number(total_area.get('area')).divide(10000)
            self.water_area_ha = water_ha
            self.flood_percentage = water_ha.divide(total_ha).multiply(100)

            pct = self.flood_percentage.getInfo()
            self.flood_alert_level = 4 if pct > 15 else (3 if pct > 10 else (2 if pct > 5 else (1 if pct > 1 else 0)))
        except Exception as e:
            print(f"[water_stats_mask] {e}")
            self.flood_alert_level = 0

    def calculate_flood_statistics(self):
        try:
            self._compute_water_stats_from_mask(self.water_extent)
        except Exception as e:
            print(f"[flood_stats] {e}")

    def generate_flood_risk_map(self):
        try:
            if self.mndwi_current is None:
                return
            r = self.mndwi_current
            risk = (r.where(r.lte(-0.3), 1)
                      .where(r.gt(-0.3).And(r.lte(-0.1)), 2)
                      .where(r.gt(-0.1).And(r.lte(0.1)), 3)
                      .where(r.gt(0.1).And(r.lte(0.3)), 4)
                      .where(r.gt(0.3), 5)).rename('flood_risk')
            self.flood_risk_map = risk
            self.flood_probability = r.add(1).divide(2).max(0).min(1).multiply(100).rename('flood_prob')
        except Exception as e:
            print(f"[risk_map] {e}")

    def temporal_flood_analysis(self, s2_idx_collection):
        try:
            start = ee.Date(self.begining)
            end = ee.Date(self.end)
            mid = start.advance(end.difference(start, 'day').divide(2), 'day')

            p1 = s2_idx_collection.filterDate(start, mid).median()
            p2 = s2_idx_collection.filterDate(mid, end).median()
            if p1.bandNames().size().getInfo() == 0 or p2.bandNames().size().getInfo() == 0:
                return

            change = p2.select('MNDWI').subtract(p1.select('MNDWI')).rename('MNDWI_change')
            self.mndwi_change = change
            self.flood_change_areas = change.abs().gt(0.2).rename('change_areas')
        except Exception as e:
            print(f"[temporal] {e}")

    # ----------------- Classification forêt -----------------
    def classification(self):
        try:
            s2 = (ee.ImageCollection(SENTINEL2_DATASET_NAME)
                  .filterDate(self.begining, self.end)
                  .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', MAX_CLOUD_PERCENTAGE))
                  .map(self.mask_s2_clouds_QA60))

            if s2.size().getInfo() == 0 or self.forest_dataset.size().getInfo() == 0:
                print("⚠️ Classification: données insuffisantes")
                return

            s2_median = s2.median().select(SE2_BANDS).clip(self.department)
            dw_median = self.forest_dataset.median()

            dw_bands = dw_median.bandNames().getInfo()
            tree_band = 'probability_trees' if 'probability_trees' in dw_bands else (
                'trees' if 'trees' in dw_bands else None
            )
            if tree_band is None:
                raise ValueError(f"Bande 'trees' introuvable dans Dynamic World: {dw_bands}")

            trees_prob = dw_median.select(tree_band)
            
            points = trees_prob.addBands(trees_prob).sample(
                region=self.department,
                scale=2000,
                seed=0,
                geometries=True,
                projection='EPSG:4326'
            )

            points = points.map(lambda f: f.set('trees', ee.Number(f.get('trees')).round()))
            
            data = s2_median.select(SE2_BANDS).sampleRegions(
                collection=points,
                properties=['trees'],
                scale=1000
            )
            
            data = data.randomColumn(seed=0)
            train = data.filter(ee.Filter.lt('random', 0.8))
            test = data.filter(ee.Filter.gte('random', 0.8))

            self.classifier_cart = ee.Classifier.smileCart().train(
                features=train,
                classProperty='trees',
                inputProperties=SE2_BANDS
            )
            
            self.classifier_rf = ee.Classifier.smileRandomForest(50).train(
                features=train,
                classProperty='trees',
                inputProperties=SE2_BANDS
            )
            
            self.classified_cart = s2_median.classify(self.classifier_cart)
            self.classified_rf = s2_median.classify(self.classifier_rf)
            
            self.forest_binary = trees_prob.gt(0.5)
            
            area_image = self.forest_binary.multiply(ee.Image.pixelArea())
            forest_area = area_image.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=self.department,
                scale=1000,
                maxPixels=1e9
            )
            self.forest_area_ha = ee.Number(forest_area.get('trees')).divide(10000).round()
            print("Forest area (ha):", self.forest_area_ha.getInfo())
            
            print("Forest classification completed")

        except Exception as e:
            print(f"[classification] {e}")
            self.forest_area_ha = ee.Number(0)

    # ----------------- Rapports et statistiques améliorés -----------------
    def get_enhanced_flood_statistics(self):
        """Retourne les statistiques détaillées du nouveau système."""
        try:
            if self.enhanced_alert_info:
                return self.enhanced_alert_info

        except Exception as e:
            print(f"[Enhanced flood stats] {e}")

    def get_detailed_flood_report(self):
        """Génère un rapport détaillé de l'analyse des inondations."""
        try:
            if not self.enhanced_alert_info:
                return "Analyse améliorée non disponible - utilisation du système classique"
            
            info = self.enhanced_alert_info
            dept_name = self.getDepartmentName()
            
            report = f"""
=== RAPPORT DE SURVEILLANCE DES INONDATIONS ===
Département : {dept_name}
Période : {self.begining} à {self.end}
Date d'analyse : {datetime.now().strftime('%Y-%m-%d %H:%M')}

🚨 NIVEAU D'ALERTE : {info['alert_level']}/4
📢 {info['alert_message']}

📊 RÉPARTITION DES INONDATIONS PAR TYPE DE ZONE :
• 🏘️  Zones urbaines : {info['urban_flood_ha']} ha
• 🌾 Zones agricoles : {info['agricultural_flood_ha']} ha  
• 🌳 Zones forestières : {info['forest_flood_ha']} ha
• 🌿 Autres zones rurales : {info['rural_flood_ha']} ha
• 📏 Surface totale inondée : {info['total_flood_ha']} ha

⚖️ ÉVALUATION DU RISQUE :
• Risque pondéré : {info['weighted_risk']}
• Zones prioritaires : {', '.join(info['priority_zones']) if info['priority_zones'] else 'Aucune'}

🎯 RECOMMANDATIONS :"""
            
            if info['alert_level'] >= 4:
                report += """
• 🚨 URGENCE : Activation immédiate des plans d'urgence
• 🏃 Évacuation préventive des zones urbaines inondées
• 🚁 Déploiement des équipes de secours
• 📢 Communication d'urgence à la population"""
                
            elif info['alert_level'] >= 3:
                report += """
• ⚠️ Surveillance renforcée 24h/24
• 🏥 Préparation des équipes médicales et de secours
• 📱 Activation des systèmes d'alerte précoce
• 🚧 Fermeture préventive des routes à risque"""
                
            elif info['alert_level'] >= 2:
                report += """
• 👁️ Monitoring continu des zones sensibles
• 📞 Information des autorités locales et préfets
• 🏗️ Vérification des infrastructures critiques
• 📋 Préparation des plans d'intervention"""
                
            elif info['alert_level'] >= 1:
                report += """
• 📊 Surveillance météorologique renforcée
• 📢 Information préventive des populations
• 🔍 Monitoring des cours d'eau
• 📝 Documentation de l'événement"""
            else:
                report += """
• 📊 Surveillance normale maintenue
• 🔄 Monitoring routinier des paramètres
• 📈 Pas d'action immédiate requise"""

            # Ajout d'informations techniques
            if hasattr(self, 'mndwi_current') and self.mndwi_current is not None:
                try:
                    mean_mndwi = self.mndwi_current.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=self.department,
                        scale=STATISTICS_SCALE,
                        maxPixels=MAX_PIXELS
                    ).get('MNDWI').getInfo()
                    report += f"""

📈 INDICATEURS TECHNIQUES :
• MNDWI moyen : {mean_mndwi:.3f}
• Seuil MNDWI eau : {WATER_THRESHOLD_MNDWI}
• Seuil NDWI eau : {WATER_THRESHOLD_NDWI}"""
                except Exception:
                    pass

            report += f"""

🔗 ÉLÉMENTS ANALYSÉS :
• ✅ Classification occupation du sol
• ✅ Distinction rivières/inondations
• ✅ Identification zones urbaines
• ✅ Cartographie zones agricoles
• ✅ Délimitation zones forestières
• ✅ Analyse temporelle des changements"""

            return report
            
        except Exception as e:
            print(f"[Detailed report] {e}")
            return "Erreur dans la génération du rapport détaillé"

    # ----------------- DataFrames -----------------
    def to_pandas(self, collection, band):
        try:
            if collection.size().getInfo() == 0:
                return pd.DataFrame({'periods': [], 'values': []})

            fc = geemap.zonal_stats(
                collection.select(band),
                self.department,
                stat_type="MEDIAN",
                scale=STATISTICS_SCALE,
                return_fc=True,
                verbose=False
            )
            brut = geemap.ee_to_df(fc)
            keys = [k for k in brut.columns if band in k]
            if not keys:
                return pd.DataFrame({'periods': [], 'values': []})
            df = brut[keys].melt(var_name="periods", value_name="values")
            df['periods'] = df['periods'].apply(lambda x: x.replace(f'_{band}', ''))
            return df
        except Exception as e:
            print(f"[to_pandas] {e}")
            return pd.DataFrame({'periods': [], 'values': []})

    def get_flood_temporal_data(self):
        """Données temporelles améliorées avec distinction types d'inondation."""
        try:
            col = self.get_sentinel2_collection()
            if col.size().getInfo() == 0:
                return pd.DataFrame()

            col = col.map(self.calculate_indices)

            def attach_enhanced_stats(img):
                try:
                    mndwi = img.select('MNDWI')
                    
                    # Statistiques classiques
                    mean_dict = mndwi.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=self.department,
                        scale=STATISTICS_SCALE,
                        maxPixels=MAX_PIXELS
                    )
                    
                    # Détection eau totale
                    water_mask = mndwi.gt(WATER_THRESHOLD_MNDWI).And(img.select('NDWI').gt(WATER_THRESHOLD_NDWI))
                    water_area = water_mask.multiply(ee.Image.pixelArea()).reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=self.department,
                        scale=STATISTICS_SCALE,
                        maxPixels=MAX_PIXELS
                    ).get('MNDWI')
                    
                    # Classification simple pour chaque image
                    urban_simple = img.select('NDBI').gt(NDBI_THRESHOLD).And(img.select('NDVI').lt(0.2))
                    urban_water = water_mask.And(urban_simple)
                    urban_flood_area = urban_water.multiply(ee.Image.pixelArea()).reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=self.department,
                        scale=STATISTICS_SCALE,
                        maxPixels=MAX_PIXELS
                    ).get('MNDWI')
                    
                    return img.set({
                        'mndwi_mean': mean_dict.get('MNDWI'),
                        'water_area_m2': water_area,
                        'urban_flood_m2': urban_flood_area,
                        'date': img.date().format('YYYY-MM-dd')
                    })
                except Exception as stats_e:
                    print(f"[Temporal stats] {stats_e}")
                    return img.set({
                        'mndwi_mean': None,
                        'water_area_m2': 0,
                        'urban_flood_m2': 0,
                        'date': img.date().format('YYYY-MM-dd')
                    })

            col = col.map(attach_enhanced_stats)
            dates = col.aggregate_array('date').getInfo()
            mndwi_means = col.aggregate_array('mndwi_mean').getInfo()
            water_areas = col.aggregate_array('water_area_m2').getInfo()
            urban_floods = col.aggregate_array('urban_flood_m2').getInfo()

            rows = []
            for d, m, w, u in zip(dates, mndwi_means, water_areas, urban_floods):
                if m is None:
                    continue
                rows.append({
                    'periods': d,
                    'mndwi_values': m,
                    'water_area': (w or 0) / 10000.0,
                    'urban_flood_area': (u or 0) / 10000.0
                })
            return pd.DataFrame(rows)
        except Exception as e:
            print(f"[Enhanced flood temporal] {e}")
            return pd.DataFrame()

    def get_flood_statistics(self):
        """Statistiques de compatibilité avec l'ancien système."""
        try:
            if self.enhanced_alert_info:
                return {
                    'water_area_ha': self.enhanced_alert_info['total_flood_ha'],
                    'flood_percentage': self.flood_percentage.getInfo() if hasattr(self, 'flood_percentage') else 0.0,
                    'alert_level': self.enhanced_alert_info['alert_level'],
                    'alert_message': self.enhanced_alert_info['alert_message'],
                    'mndwi_mean': self.mndwi_current.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=self.department,
                        scale=STATISTICS_SCALE,
                        maxPixels=MAX_PIXELS
                    ).get('MNDWI').getInfo() if self.mndwi_current else 0.0
                }

            stats = {
                'water_area_ha': 0.0,
                'flood_percentage': 0.0,
                'alert_level': 0,
                'alert_message': 'Pas de données disponibles',
                'mndwi_mean': 0.0
            }
            
            if hasattr(self, 'water_area_ha'):
                stats['water_area_ha'] = round(float(self.water_area_ha.getInfo()), 2)
            if hasattr(self, 'flood_percentage'):
                stats['flood_percentage'] = round(float(self.flood_percentage.getInfo()), 2)

            alerts = {
                0: "Très faible - Pas de risque immédiat",
                1: "Faible - Surveillance recommandée",
                2: "Modéré - Vigilance requise",
                3: "Élevé - Mesures préventives conseillées",
                4: "Très élevé - Alerte maximale",
            }
            stats['alert_level'] = self.flood_alert_level
            stats['alert_message'] = alerts.get(self.flood_alert_level, "Indéterminé")

            if self.mndwi_current is not None:
                mean_val = self.mndwi_current.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=self.department,
                    scale=STATISTICS_SCALE,
                    maxPixels=MAX_PIXELS
                ).get('MNDWI')
                stats['mndwi_mean'] = round(float(mean_val.getInfo()), 3)

            return stats
        except Exception as e:
            print(f"[get_flood_statistics] {e}")
            return {
                'water_area_ha': 0.0,
                'flood_percentage': 0.0,
                'alert_level': 0,
                'alert_message': 'Erreur de calcul',
                'mndwi_mean': 0.0
            }

    # ----------------- Carte & Légende améliorées -----------------
    def show_enhanced_map(self):
        """Carte avec les nouvelles couches de distinction des éléments."""
        try:
            m = geemap_f.Map()
            m.centerObject(self.department, 10)

            try:
                m.add_basemap('SATELLITE')
            except Exception:
                m.add_basemap('OpenStreetMap')

            # Couches existantes
            try:
                m.addLayer(self.fires_dataset.median().clip(self.department.geometry()),
                           self.fires_vis, 'Feux (VIIRS)')
            except Exception as e:
                print(f"[Enhanced map] fires: {e}")

            try:
                m.addLayer(self.temperature_dataset.median().clip(self.department.geometry()),
                           self.temperature_vis, 'Température LST (MODIS)')
            except Exception as e:
                print(f"[Enhanced map] LST: {e}")

            try:
                m.addLayer(self.forest_dataset.median().clip(self.department.geometry()),
                           self.tree_vis, 'DynamicWorld (label)')
            except Exception as e:
                print(f"[Enhanced map] DW: {e}")

            # Nouvelles couches de classification
            try:
                if self.land_cover_map is not None:
                    m.addLayer(self.land_cover_map.clip(self.department.geometry()),
                               self.land_cover_vis, 'Classification du sol')
                               
                if self.normal_rivers is not None:
                    m.addLayer(self.normal_rivers.clip(self.department.geometry()),
                               self.normal_rivers_vis, 'Rivières normales')
                               
                if self.urban_flooding is not None:
                    m.addLayer(self.urban_flooding.clip(self.department.geometry()),
                               self.urban_flood_vis, 'Inondations urbaines')
                               
                if self.rural_flooding is not None:
                    m.addLayer(self.rural_flooding.clip(self.department.geometry()),
                               self.rural_flood_vis, 'Inondations rurales')
                               
            except Exception as e:
                print(f"[Enhanced map] New layers: {e}")

            # Couches d'analyse classiques
            try:
                if self.mndwi_current is not None:
                    m.addLayer(self.mndwi_current.clip(self.department.geometry()),
                               self.flood_vis, 'MNDWI')
                if self.flood_risk_map is not None:
                    m.addLayer(self.flood_risk_map.clip(self.department.geometry()),
                               self.flood_risk_vis, 'Risque inondation')
            except Exception as e:
                print(f"[Enhanced map] Classic flood layers: {e}")

            # Légende améliorée
            sections = [
                ("Classification du sol", [
                    ("#D2B48C", "Sol nu"), ("#90EE90", "Agriculture"), 
                    ("#228B22", "Végétation"), ("#FF6347", "Urbain"), ("#4169E1", "Eau")
                ], "chips"),
                ("État des eaux", [
                    ("#0000FF", "Rivières normales"), ("#FF0000", "Inondations urbaines"), 
                    ("#FFA500", "Inondations rurales")
                ], "chips"),
                ("Feux (VIIRS)", self._palette_css(FIRES_VISUALIZATION.get('palette', [])), "gradient"),
                ("MNDWI", self._palette_css(MNDWI_VISUALIZATION.get('palette', [])), "gradient"),
                ("Risque inondation", self._palette_css(FLOOD_RISK_VISUALIZATION.get('palette', [])), "gradient"),
            ]
            self._add_legend_html(m, "Surveillance Environnementale", sections, position='bottomright')
            return m
        except Exception as e:
            print(f"[Enhanced map] {e}")
            return self.show_combined_map()  # Fallback

    def show_combined_map(self):
        """Carte folium + couches + légende HTML (méthode classique conservée)."""
        try:
            m = geemap_f.Map()
            m.centerObject(self.department, 10)

            try:
                m.add_basemap('SATELLITE')
            except Exception:
                m.add_basemap('OpenStreetMap')

            # Couches classiques
            try:
                m.addLayer(self.fires_dataset.median().clip(self.department.geometry()),
                           self.fires_vis, 'Feux (VIIRS)')
            except Exception as e:
                print(f"[map] fires: {e}")

            try:
                m.addLayer(self.temperature_dataset.median().clip(self.department.geometry()),
                           self.temperature_vis, 'Température LST (MODIS)')
            except Exception as e:
                print(f"[map] LST: {e}")

            try:
                m.addLayer(self.forest_dataset.median().clip(self.department.geometry()),
                           self.tree_vis, 'DynamicWorld (label)')
            except Exception as e:
                print(f"[map] DW: {e}")

            try:
                if self.mndwi_current is not None:
                    m.addLayer(self.mndwi_current.clip(self.department.geometry()),
                               self.flood_vis, 'MNDWI')
                if self.water_extent is not None:
                    m.addLayer(self.water_extent.clip(self.department.geometry()),
                               self.water_vis, 'Eau (masque)')
                if self.flood_risk_map is not None:
                    m.addLayer(self.flood_risk_map.clip(self.department.geometry()),
                               self.flood_risk_vis, 'Risque inondation')
            except Exception as e:
                print(f"[map] flood layers: {e}")

            # Légende basée sur les palettes du config
            sections = [
                ("Feux (VIIRS)", self._palette_css(FIRES_VISUALIZATION.get('palette', [])), "gradient"),
                ("Température LST (MODIS)", self._palette_css(TEMPERATURE_VISUALIZATION.get('palette', [])), "gradient"),
                ("DynamicWorld (label)", self._palette_css(FOREST_VISUALIZATION.get('palette', [])), "gradient"),
                ("MNDWI", self._palette_css(MNDWI_VISUALIZATION.get('palette', [])), "gradient"),
                ("Eau (masque)", [("#ffffff", "Terre/NoData"), ("#0000ff", "Eau")], "chips"),
                ("Risque inondation", self._palette_css(FLOOD_RISK_VISUALIZATION.get('palette', [])), "gradient"),
            ]
            self._add_legend_html(m, "Légende", sections, position='bottomright')
            return m
        except Exception as e:
            print(f"[show_combined_map] {e}")
            m = geemap_f.Map()
            m.centerObject(self.department, 10)
            return m

    @staticmethod
    def _ensure_hex(c):
        """Ajoute # si manquant, conserve déjà-valide."""
        if isinstance(c, str):
            c = c.strip()
            if not c.startswith('#'):
                return f"#{c}"
        return c

    def _palette_css(self, palette):
        """Normalise une palette en liste hex #RRGGBB."""
        if not isinstance(palette, list):
            return []
        return [self._ensure_hex(c) for c in palette if isinstance(c, str)]
    
    
    def _add_legend_html(self, m, title, sections, position='bottomright'):
        """
        Ajoute une légende déplaçable avec drag & drop.
        sections: liste de tuples (titre_section, data, kind)
        - kind='gradient' -> data = liste de couleurs ['#hex', ...]
        - kind='chips'    -> data = liste de tuples [(#hex, label), ...]
        """
        
        # Position initiale basée sur le paramètre
        if position == 'bottomright':
            initial_pos = 'bottom: 20px; right: 20px;'
        elif position == 'bottomleft':
            initial_pos = 'bottom: 20px; left: 20px;'
        elif position == 'topright':
            initial_pos = 'top: 20px; right: 20px;'
        else:  # topleft
            initial_pos = 'top: 20px; left: 20px;'

        # Construit HTML des sections
        def gradient_bar(colors):
            if not colors:
                return ""
            n = len(colors)
            stops = ",".join([f"{c} {int(i*100/(n-1))}%" for i, c in enumerate(colors)])
            return f"""
                <div class="legend-gradient" style="background: linear-gradient(to right, {stops});"></div>
                <div class="legend-scale"><span>min</span><span style="float:right;">max</span></div>
            """

        def chips(items):
            chips_html = ""
            for c, lbl in items:
                c = self._ensure_hex(c)
                chips_html += f"""
                <div class="legend-chip">
                    <span class="chip" style="background:{c};"></span>{lbl}
                </div>
                """
            return f"<div class='legend-chips'>{chips_html}</div>"

        sections_html = ""
        for sec_title, data, kind in sections:
            body = gradient_bar(data) if kind == "gradient" else chips(data)
            sections_html += f"""
            <div class="legend-section">
                <div class="legend-sec-title">{sec_title}</div>
                {body}
            </div>
            """

        html = f"""
        <div id="map-legend" class="map-legend" style="{initial_pos}">
        <div class="legend-card">
            <div class="legend-header">
            <div class="legend-title">{title}</div>
            <div class="legend-controls">
                <button id="legend-minimize" class="legend-btn">−</button>
                <button id="legend-close" class="legend-btn">×</button>
            </div>
            </div>
            <div id="legend-content" class="legend-content">
            {sections_html}
            </div>
        </div>
        </div>

        <style>
        .map-legend {{
            position: fixed;
            z-index: 9999;
            cursor: move;
            user-select: none;
        }}
        
        .legend-card {{
            background: rgba(255,255,255,0.95);
            border: 1px solid #999;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.25);
            max-width: 320px;
            font-family: system-ui, -apple-system, Segoe UI, Roboto, "Helvetica Neue", Arial;
            font-size: 12px;
            backdrop-filter: blur(5px);
        }}
        
        .legend-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            border-bottom: 1px solid #ddd;
            cursor: move;
            background: rgba(240,240,240,0.8);
            border-radius: 10px 10px 0 0;
        }}
        
        .legend-title {{
            font-weight: 700;
            font-size: 13px;
            margin: 0;
        }}
        
        .legend-controls {{
            display: flex;
            gap: 4px;
        }}
        
        .legend-btn {{
            background: none;
            border: 1px solid #999;
            border-radius: 3px;
            width: 20px;
            height: 20px;
            cursor: pointer;
            font-size: 12px;
            line-height: 1;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .legend-btn:hover {{
            background: rgba(0,0,0,0.1);
        }}
        
        .legend-content {{
            padding: 10px 12px;
            max-height: 400px;
            overflow-y: auto;
        }}
        
        .legend-section {{
            margin-bottom: 8px;
        }}
        
        .legend-sec-title {{
            font-weight: 600;
            margin-bottom: 4px;
        }}
        
        .legend-gradient {{
            width: 100%;
            height: 12px;
            border: 1px solid #bbb;
            border-radius: 3px;
        }}
        
        .legend-scale {{
            display: flex;
            justify-content: space-between;
            margin-top: 2px;
            color: #444;
            font-size: 10px;
        }}
        
        .legend-chips {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 4px;
        }}
        
        .legend-chip {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        
        .legend-chip .chip {{
            width: 16px;
            height: 12px;
            border: 1px solid #999;
            display: inline-block;
            flex-shrink: 0;
        }}
        
        /* États de la légende */
        .legend-minimized .legend-content {{
            display: none;
        }}
        
        .legend-hidden {{
            display: none;
        }}
        </style>

        <script>
        (function() {{
            // Attendre que l'élément soit dans le DOM
            setTimeout(function() {{
            const legend = document.getElementById('map-legend');
            const header = legend.querySelector('.legend-header');
            const minimizeBtn = document.getElementById('legend-minimize');
            const closeBtn = document.getElementById('legend-close');
            const content = document.getElementById('legend-content');
            
            if (!legend || !header) return;
            
            let isDragging = false;
            let currentX;
            let currentY;
            let initialX;
            let initialY;
            let xOffset = 0;
            let yOffset = 0;
            
            // Drag & Drop functionality
            function dragStart(e) {{
                if (e.target.classList.contains('legend-btn')) return;
                
                if (e.type === "touchstart") {{
                initialX = e.touches[0].clientX - xOffset;
                initialY = e.touches[0].clientY - yOffset;
                }} else {{
                initialX = e.clientX - xOffset;
                initialY = e.clientY - yOffset;
                }}
                
                if (e.target === header || header.contains(e.target)) {{
                isDragging = true;
                legend.style.cursor = 'grabbing';
                }}
            }}
            
            function dragEnd(e) {{
                initialX = currentX;
                initialY = currentY;
                isDragging = false;
                legend.style.cursor = 'move';
            }}
            
            function drag(e) {{
                if (isDragging) {{
                e.preventDefault();
                
                if (e.type === "touchmove") {{
                    currentX = e.touches[0].clientX - initialX;
                    currentY = e.touches[0].clientY - initialY;
                }} else {{
                    currentX = e.clientX - initialX;
                    currentY = e.clientY - initialY;
                }}
                
                xOffset = currentX;
                yOffset = currentY;
                
                // Contraindre dans la fenêtre
                const rect = legend.getBoundingClientRect();
                const maxX = window.innerWidth - rect.width;
                const maxY = window.innerHeight - rect.height;
                
                currentX = Math.max(0, Math.min(currentX, maxX));
                currentY = Math.max(0, Math.min(currentY, maxY));
                
                legend.style.left = currentX + 'px';
                legend.style.top = currentY + 'px';
                legend.style.right = 'auto';
                legend.style.bottom = 'auto';
                }}
            }}
            
            // Event listeners pour le drag
            header.addEventListener('mousedown', dragStart);
            document.addEventListener('mousemove', drag);
            document.addEventListener('mouseup', dragEnd);
            
            // Touch events pour mobile
            header.addEventListener('touchstart', dragStart, {{passive: false}});
            document.addEventListener('touchmove', drag, {{passive: false}});
            document.addEventListener('touchend', dragEnd);
            
            // Bouton minimize/maximize
            if (minimizeBtn) {{
                minimizeBtn.addEventListener('click', function() {{
                legend.classList.toggle('legend-minimized');
                minimizeBtn.textContent = legend.classList.contains('legend-minimized') ? '+' : '−';
                }});
            }}
            
            // Bouton fermer
            if (closeBtn) {{
                closeBtn.addEventListener('click', function() {{
                legend.classList.add('legend-hidden');
                }});
            }}
            
            // Double-clic pour restaurer la position initiale
            header.addEventListener('dblclick', function() {{
                legend.style.left = 'auto';
                legend.style.top = 'auto';
                legend.style.right = '20px';
                legend.style.bottom = '20px';
                xOffset = 0;
                yOffset = 0;
                currentX = 0;
                currentY = 0;
            }});
            
            }}, 100);
        }})();
        </script>
        """
        
        m.get_root().html.add_child(folium.Element(html))

    # ----------------- Graphiques -----------------
    def show_combined_graphics(self):
        from plotly.subplots import make_subplots
        import plotly.graph_objects as go

        try:
            try:
                df_fires = self.to_pandas(self.fires_dataset, FIRES_SELECTED_BAND)
            except Exception:
                df_fires = pd.DataFrame({'periods': [], 'values': []})

            try:
                df_forest = self.to_pandas(self.forest_dataset, FOREST_SELECTED_BAND)
            except Exception:
                df_forest = pd.DataFrame({'periods': [], 'values': []})

            try:
                df_flood = self.get_flood_temporal_data()
            except Exception:
                df_flood = pd.DataFrame({'periods': [], 'mndwi_values': [], 'water_area': []})

            fig = make_subplots(
                rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                row_heights=[150, 150, 150, 150],
                subplot_titles=("Évolution des feux de brousse",
                                "Évolution DW (label, médiane)",
                                "Évolution MNDWI",
                                "Surface d'eau détectée (ha)")
            )

            if not df_fires.empty:
                fig.add_trace(go.Scatter(x=df_fires['periods'], y=df_fires['values'],
                                         name="Feux", mode='lines', line=dict(color='red')), row=1, col=1)
            if not df_forest.empty:
                fig.add_trace(go.Scatter(x=df_forest['periods'], y=df_forest['values'],
                                         name="DW label", mode='lines', line=dict(color='green')), row=2, col=1)
            if not df_flood.empty and 'mndwi_values' in df_flood.columns:
                fig.add_trace(go.Scatter(x=df_flood['periods'], y=df_flood['mndwi_values'],
                                         name="MNDWI", mode='lines', line=dict(color='blue')), row=3, col=1)
            if not df_flood.empty and 'water_area' in df_flood.columns:
                fig.add_trace(go.Scatter(x=df_flood['periods'], y=df_flood['water_area'],
                                         name="Surface eau (ha)", mode='lines+markers',
                                         line=dict(color='cyan')), row=4, col=1)

            fig.update_xaxes(title_text="Périodes", row=4, col=1)
            fig.update_yaxes(title_text="Intensité", row=1, col=1)
            fig.update_yaxes(title_text="DW (label)", row=2, col=1)
            fig.update_yaxes(title_text="MNDWI", row=3, col=1)
            fig.update_yaxes(title_text="Surface (ha)", row=4, col=1)

            fig.update_layout(height=820, showlegend=True,
                              title_text="Surveillance environnementale & inondations")
            return fig
        except Exception as e:
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_annotation(text=f"Erreur graphiques: {e}", x=0.5, y=0.5, showarrow=False)
            return fig

    # ----------------- Exports -----------------
    def getBBox(self):
        """[xmin, ymin, xmax, ymax]"""
        try:
            coords = self.department.geometry().bounds().coordinates().getInfo()[0]
            lons = [p[0] for p in coords]
            lats = [p[1] for p in coords]
            return [min(lons), min(lats), max(lons), max(lats)]
        except Exception as e:
            print(f"[getBBox] {e}")
            return [-17.5, 12.3, -11.4, 16.7]

    def _ensure_export_dirs(self):
        for p in [EXPORT_FOLDER, FLOOD_MAPS_FOLDER, FIRE_MAPS_FOLDER, FOREST_MAPS_FOLDER]:
            try:
                os.makedirs(p, exist_ok=True)
            except Exception:
                pass

    def export_data_to_csv(self):
        try:
            fires_df = self.to_pandas(self.fires_dataset, FIRES_SELECTED_BAND)
            forest_df = self.to_pandas(self.forest_dataset, FOREST_SELECTED_BAND)
            flood_df = self.get_flood_temporal_data()
            flood_stats = self.get_flood_statistics()

            combined = pd.concat([fires_df, forest_df, flood_df], ignore_index=True)

            summary = pd.DataFrame({
                'periods': ['RESUME_INONDATIONS'],
                'values': [flood_stats['water_area_ha']],
                'mndwi_values': [flood_stats['mndwi_mean']],
                'water_area': [flood_stats['water_area_ha']]
            })
            combined = pd.concat([combined, summary], ignore_index=True)

            buf = io.StringIO()
            combined.to_csv(buf, index=False)
            return buf.getvalue()
        except Exception as e:
            print(f"[export CSV] {e}")
            return "Error exporting data"

    def exportCards(self):
        try:
            print("📤 Export des cartes …")
            north_arrow = {
                "text": "N", "xy": (0.1, 0.3), "arrow_length": 0.15,
                "text_color": "white", "arrow_color": "white",
                "fontsize": 20, "width": 5, "headwidth": 15,
                "ha": "center", "va": "center",
            }
            scale_bar = {
                "length": 10, "xy": (0.1, 0.05), "linewidth": 3,
                "fontsize": 12, "color": "white", "unit": "km",
                "ha": "center", "va": "bottom",
            }

            # Feux (GIF)
            try:
                if self.fires_dataset.size().getInfo() > 0:
                    cartoee.get_image_collection_gif(
                        ee_ic=self.fires_dataset,
                        out_dir=os.path.expanduser(FIRE_MAPS_FOLDER),
                        out_gif="fires.gif",
                        vis_params=self.fires_vis,
                        region=self.getBBox(),
                        fps=5,
                        mp4=True,
                        grid_interval=(0.2, 0.2),
                        plot_title=f"{self.getDepartmentName()}, SN - Feux",
                        date_format="YYYY-MM-dd",
                        fig_size=(10, 8),
                        dpi_plot=100,
                        file_format="png",
                        north_arrow_dict=north_arrow,
                        scale_bar_dict=scale_bar,
                        verbose=True,
                    )
            except Exception as e:
                print(f"[export fires] {e}")

            # MNDWI
            try:
                if self.mndwi_current is not None:
                    cartoee.get_image_thumbnail(
                        ee_object=self.mndwi_current,
                        out_img=os.path.expanduser(os.path.join(FLOOD_MAPS_FOLDER, "mndwi_map.png")),
                        vis_params=self.flood_vis,
                        dimensions=800,
                        region=self.getBBox(),
                        crs='EPSG:4326'
                    )
            except Exception as e:
                print(f"[export MNDWI] {e}")

            # Risque
            try:
                if self.flood_risk_map is not None:
                    cartoee.get_image_thumbnail(
                        ee_object=self.flood_risk_map,
                        out_img=os.path.expanduser(os.path.join(FLOOD_MAPS_FOLDER, "flood_risk_map.png")),
                        vis_params=self.flood_risk_vis,
                        dimensions=800,
                        region=self.getBBox(),
                        crs='EPSG:4326'
                    )
            except Exception as e:
                print(f"[export risk] {e}")

        except Exception as e:
            print(f"[exportCards] {e}")

    # ----------------- Accesseurs & Santé -----------------
    def getFiresDataset(self): 
        return self.fires_dataset
    def getTemperatureDataset(self): 
        return self.temperature_dataset
    def getForestDataset(self): 
        return self.forest_dataset

    def get_system_status(self):
        status = {
            'gee_connected': False,
            'department_loaded': False,
            'fires_data_available': False,
            'forest_data_available': False,
            'classification_completed': False,
            'flood_analysis_completed': False,
            'sentinel2_data_available': False,
        }
        try:
            ee.Number(1).getInfo()
            status['gee_connected'] = True
        except Exception:
            pass

        try:
            self.department.getInfo()
            status['department_loaded'] = True
        except:
            pass

        try:
            status['fires_data_available'] = self.fires_dataset.size().getInfo() > 0
            status['forest_data_available'] = self.forest_dataset.size().getInfo() > 0
            status['sentinel2_data_available'] = self.get_sentinel2_collection().size().getInfo() > 0
        except Exception:
            pass

        try:
            status['flood_analysis_completed'] = (self.flood_risk_map and 
                                                 self.flood_risk_map.bandNames().size().getInfo() > 0)
            status['classification_completed'] = hasattr(self, 'forest_area_ha')
            status['flood_analysis_completed'] = self.water_extent is not None   
        except Exception:
            pass

        return status