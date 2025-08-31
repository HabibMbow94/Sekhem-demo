PROJECT_NAME = 'ee-hmbow'

# === DATASETS ===
FOREST_DATASET_NAME = 'GOOGLE/DYNAMICWORLD/V1'
FIRES_DATASET_NAME = 'NASA/LANCE/NOAA20_VIIRS/C2'
TEMPERATURE_DATASET_NAME = 'MODIS/061/MOD11A2'
SENTINEL1_DATASET_NAME = 'COPERNICUS/S1_GRD'
SENTINEL2_DATASET_NAME = 'COPERNICUS/S2_HARMONIZED'
DEPARTMENT_DATASET_NAME = 'WM/geoLab/geoBoundaries/600/ADM2'

# === BANDES SÉLECTIONNÉES ===
FIRES_SELECTED_BAND = 'Bright_ti4'
FOREST_SELECTED_BAND = 'label'
TEMPERATURE_SELECTED_BAND = 'LST_Day_1km'
SENTINEL2_GREEN_BAND = 'B3'    # Bande verte (560 nm)
SENTINEL2_NIR_BAND = 'B8'      # Proche infrarouge (842 nm)  
SENTINEL2_SWIR1_BAND = 'B11'   # SWIR1 (1610 nm)
SENTINEL2_SWIR2_BAND = 'B12'   # SWIR2 (2190 nm)

CLASS_NAMES = [
  'probability_water',
  'probability_trees',
  'probability_grass',
  'probability_flooded_vegetation',
  'probability_crops',
  'probability_shrub_and_scrub',
  'probability_built',
  'probability_bare',
  'probability_snow_and_ice',
]

# === VISUALISATIONS ===
FIRES_VISUALIZATION = {
    'min': 280.0,
    'max': 400.0,
    'palette': ['fff5eb', 'fdae61', 'e6550d', 'a63603'],
    'bands': [FIRES_SELECTED_BAND],
}

TEMPERATURE_VISUALIZATION = {
    'min': 13000.0,
    'max': 16500.0,
    'palette': ['313695', '74add1', 'fee090', 'f46d43', 'a50026'],
    'bands': [TEMPERATURE_SELECTED_BAND]
}

FOREST_VISUALIZATION = {
    "min": 0,
    "max": 8,
    "palette": ['006400', '228b22', '66c2a5', 'abdda4', 'e6f598'],
    "bands": [FOREST_SELECTED_BAND],
}

NDWI_VISUALIZATION = {
    'min': -1,
    'max': 1,
    'palette': ['f7fbff', 'c6dbef', '2171b5'],
}

MNDWI_VISUALIZATION = {
    'min': -1,
    'max': 1,
    'palette': ['fff7ec', 'fdbb84', 'e34a33', 'b30000'],
}

FLOOD_RISK_VISUALIZATION = {
    'min': 1,
    'max': 5,
    'palette': ['edf8fb', '66c2a4', '238b45', '00441b', '081d58'],
}

WATER_MASK_VISUALIZATION = {
    'min': 0,
    'max': 1,
    'palette': ['white', 'blue']
}

CHANGE_VISUALIZATION = {
    'min': -0.5,
    'max': 0.5,
    'palette': ['red', 'white', 'blue']
}

# === PARAMÈTRES DE CLASSIFICATION ===
forestVisParams = {
    'min': 0,
    'max': 1,
    'palette': ['FFFFFF', '006400']
}

SE2_BANDS = ['B2','B3','B4','B8','B8A','B11','B12']
S2_SCL_CLOUD_CLASSES = [3, 8, 9, 10, 11]

# === SEUILS MNDWI/NDWI ===
WATER_THRESHOLD_MNDWI = 0.0
WATER_THRESHOLD_NDWI = 0.1
ROBUST_WATER_THRESHOLD = 0.1

SAR_VV_VISUALIZATION = {
    'min': -25.0,
    'max': 0.0,
    'palette': ['black', 'gray', 'white'],
    'bands': ['VV']
}

FLOOD_RISK_THRESHOLDS = {
    'very_low': 1.0,
    'low': 5.0,
    'moderate': 10.0,
    'high': 15.0,
    'very_high': 25.0
}

# === PARAMÈTRES DE TRAITEMENT ===
MAX_CLOUD_PERCENTAGE = 20
FALLBACK_CLOUD_PERCENTAGE = 30 
PROCESSING_SCALE = 100
EXPORT_SCALE = 30
STATISTICS_SCALE = 500
MAX_PIXELS = 1e9

EXPORT_SCALE_S2_10M = 10
EXPORT_SCALE_S2_20M = 20
EXPORT_SCALE_S2_60M = 60

# === PARAMÈTRES GÉOGRAPHIQUES ===
DEPARTMENT_NAME = 'Bignona'
COUNTRY_CODE = 'SEN'
PREFFIX = 'T28PCU'


# === CHEMINS D'EXPORT ===
EXPORT_FOLDER = 'Downloads'
FLOOD_MAPS_FOLDER = 'Downloads/floods'
FIRE_MAPS_FOLDER = 'Downloads/fires'
FOREST_MAPS_FOLDER = 'Downloads/forests'

# === PARAMÈTRES D'EXPORT ===
IMAGE_FORMATS = ['png', 'jpg', 'tiff']
DEFAULT_IMAGE_FORMAT = 'png'

DEFAULT_EXPORT_PARAMS = {
    'dimensions': 800,
    'dpi': 100,
    'format': DEFAULT_IMAGE_FORMAT
}

GIF_PARAMS = {
    'fps': 5,
    'mp4': True,
    'duration': 0.5
}

# === MESSAGES ET TEXTES ===
ALERT_MESSAGES = {
    0: "Très faible - Pas de risque immédiat",
    1: "Faible - Surveillance recommandée",
    2: "Modéré - Vigilance requise", 
    3: "Élevé - Mesures préventives conseillées",
    4: "Très élevé - Alerte maximale"
}

# Messages d'état du système
STATUS_MESSAGES = {
    'gee_connected': "✅ Google Earth Engine connecté",
    'gee_disconnected': "❌ Problème de connexion GEE",
    'data_available': "✅ Données disponibles",
    'data_limited': "⚠️ Données limitées",
    'no_data': "❌ Pas de données",
    'processing': "⏳ Traitement en cours...",
    'completed': "✅ Traitement terminé",
    'error': "❌ Erreur de traitement"
}

# === MÉTADONNÉES ===
INDICES_INFO = {
    'MNDWI': {
        'full_name': 'Modified Normalized Difference Water Index',
        'formula': '(Green - SWIR1) / (Green + SWIR1)',
        'sentinel2_formula': '(B03 - B11) / (B03 + B11)',
        'range': '[-1, 1]',
        'water_threshold': 0.0,
        'description': 'Indice optimisé pour la détection automatique de l\'eau, plus robuste que le NDWI'
    },
    'NDWI': {
        'full_name': 'Normalized Difference Water Index', 
        'formula': '(Green - NIR) / (Green + NIR)',
        'sentinel2_formula': '(B03 - B08) / (B03 + B08)',
        'range': '[-1, 1]',
        'water_threshold': 0.0,
        'description': 'Indice classique pour la détection d\'eau, peut être perturbé par la végétation'
    }
}

SENSORS_INFO = {
    'SENTINEL2': {
        'name': 'Sentinel-2 MSI',
        'resolution': '10-20m',
        'revisit_time': '5 jours',
        'bands_used': ['B03 (Green)', 'B08 (NIR)', 'B11 (SWIR1)'],
        'provider': 'ESA/Copernicus'
    },
    'MODIS': {
        'name': 'MODIS Terra/Aqua',
        'resolution': '250m-1km',
        'revisit_time': '1-2 jours', 
        'bands_used': ['LST_Day_1km'],
        'provider': 'NASA'
    },
    'VIIRS': {
        'name': 'VIIRS NOAA-20',
        'resolution': '375m',
        'revisit_time': '12 heures',
        'bands_used': ['Bright_ti4'],
        'provider': 'NASA/NOAA'
    }
}