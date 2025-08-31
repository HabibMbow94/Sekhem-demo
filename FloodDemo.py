#!/usr/bin/env python3
"""
Script de démonstration - Système de prédiction d'inondations avec MNDWI
Surveillance environnementale intégrée pour le Sénégal

Auteur: Système SEKHEM
Date: 2025
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd

# Ajout du chemin pour importer les modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from sekhem_utils import Utils
    from config import *
    import ee
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")
    print("Assurez-vous que tous les modules sont installés:")
    print("pip install earthengine-api geemap streamlit plotly pandas")
    sys.exit(1)

class FloodDemo:
    """Classe de démonstration du système de prédiction d'inondations"""
    
    def __init__(self, department_name="Bignona", country_code="SEN"):
        """Initialisation de la démonstration"""
        print("🌍 === SYSTÈME SEKHEM - PRÉDICTION D'INONDATIONS ===")
        print("🌊 Démonstration MNDWI avec Sentinel-2")
        print("-" * 60)
        
        self.department_name = department_name
        self.country_code = country_code
        
        # Initialisation du système
        print("🔧 Initialisation du système...")
        try:
            self.utils = Utils(country_code=country_code)
            print("✅ Système initialisé avec succès")
        except Exception as e:
            print(f"❌ Erreur d'initialisation: {e}")
            sys.exit(1)
        
        # Configuration des dates (derniers 6 mois)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=180)
        
        self.utils.setBeginingDate(start_date.strftime('%Y-%m-%d'))
        self.utils.setEndDate(end_date.strftime('%Y-%m-%d'))
        self.utils.setDepartment(department_name)
        
        print(f"📅 Période d'analyse: {start_date.strftime('%Y-%m-%d')} à {end_date.strftime('%Y-%m-%d')}")
        print(f"🏘️ Département: {department_name}")

    def run_system_check(self):
        """Vérification de l'état du système"""
        print("\n🔍 === VÉRIFICATION DU SYSTÈME ===")
        
        status = self.utils.get_system_status()
        
        checks = [
            ("Connexion Google Earth Engine", status['gee_connected']),
            ("Département chargé", status['department_loaded']), 
            ("Données feux disponibles", status['fires_data_available']),
            ("Données forêt disponibles", status['forest_data_available']),
            ("Données Sentinel-2 disponibles", status['sentinel2_data_available']),
            ("Classification terminée", status['classification_completed']),
            ("Analyse inondations terminée", status['flood_analysis_completed'])
        ]
        
        all_good = True
        for check_name, check_status in checks:
            status_icon = "✅" if check_status else "❌"
            print(f"{status_icon} {check_name}")
            if not check_status:
                all_good = False
        
        if all_good:
            print("🎉 Tous les systèmes sont opérationnels!")
        else:
            print("⚠️ Certains systèmes présentent des problèmes")
        
        return all_good

    def demonstrate_mndwi_calculation(self):
        """Démonstration du calcul MNDWI"""
        print("\n📊 === DÉMONSTRATION CALCUL MNDWI ===")
        
        print("🔬 Formule MNDWI:")
        print("   MNDWI = (Vert - SWIR1) / (Vert + SWIR1)")
        print("   MNDWI = (B03 - B11) / (B03 + B11)  [Sentinel-2]")
        print()
        
        print("📈 Interprétation des valeurs:")
        print("   MNDWI > 0.3  : Eau très probable (zones inondées)")
        print("   MNDWI 0-0.3  : Eau probable (zones humides)")
        print("   MNDWI -0.3-0 : Zone sèche")
        print("   MNDWI < -0.3 : Zone très sèche")
        print()
        
        print("🆚 Avantages MNDWI vs NDWI:")
        print("   ✓ Utilise SWIR au lieu du proche infrarouge")
        print("   ✓ Moins sensible aux effets de la végétation")
        print("   ✓ Meilleure suppression du bruit atmosphérique") 
        print("   ✓ Plus adapté à la détection automatique")
        print("   ✓ Précision améliorée en zones végétalisées")

    def show_flood_statistics(self):
        """Affichage des statistiques d'inondation"""
        print("\n📈 === STATISTIQUES D'INONDATION ===")
        
        try:
            stats = self.utils.get_flood_statistics()
            
            print(f"💧 MNDWI moyen: {stats['mndwi_mean']:.3f}")
            print(f"🏞️ Surface d'eau détectée: {stats['water_area_ha']:.1f} hectares")
            print(f"📊 Pourcentage d'inondation: {stats['flood_percentage']:.2f}%")
            print(f"🚨 Niveau d'alerte: {stats['alert_level']}/4")
            print(f"💬 Message: {stats['alert_message']}")
            
            # Analyse du risque
            if stats['alert_level'] >= 3:
                print("🔴 ⚠️ SITUATION CRITIQUE - Action immédiate requise")
            elif stats['alert_level'] >= 2:
                print("🟠 ⚡ VIGILANCE RENFORCÉE - Surveillance active")
            elif stats['alert_level'] >= 1:
                print("🟡 👁️ SURVEILLANCE NORMALE - Suivi de routine")
            else:
                print("🟢 ✅ SITUATION NORMALE - Pas de risque immédiat")
                
        except Exception as e:
            print(f"❌ Erreur lors de la récupération des statistiques: {e}")

    def demonstrate_temporal_analysis(self):
        """Démonstration de l'analyse temporelle"""
        print("\n⏱️ === ANALYSE TEMPORELLE ===")
        
        try:
            print("📊 Récupération des données temporelles...")
            flood_df = self.utils.get_flood_temporal_data()
            
            if not flood_df.empty:
                print(f"✅ {len(flood_df)} points temporels récupérés")
                print("\n📈 Évolution MNDWI:")
                
                # Statistiques descriptives
                if 'mndwi_values' in flood_df.columns:
                    mndwi_mean = flood_df['mndwi_values'].mean()
                    mndwi_max = flood_df['mndwi_values'].max()
                    mndwi_min = flood_df['mndwi_values'].min()
                    mndwi_std = flood_df['mndwi_values'].std()
                    
                    print(f"   Moyenne: {mndwi_mean:.3f}")
                    print(f"   Maximum: {mndwi_max:.3f}")
                    print(f"   Minimum: {mndwi_min:.3f}")
                    print(f"   Écart-type: {mndwi_std:.3f}")
                    
                    # Détection de tendances
                    if mndwi_max > 0.3:
                        print("   🔴 Période avec eau détectée (MNDWI > 0.3)")
                    elif mndwi_max > 0.0:
                        print("   🟡 Période avec humidité élevée (MNDWI > 0)")
                    else:
                        print("   🟢 Période généralement sèche (MNDWI < 0)")
                
                # Affichage des premiers points
                print("\n📅 Premiers points temporels:")
                for i, row in flood_df.head(5).iterrows():
                    date = row.get('periods', 'N/A')
                    mndwi = row.get('mndwi_values', 0)
                    area = row.get('water_area', 0)
                    print(f"   {date}: MNDWI={mndwi:.3f}, Surface={area:.1f}ha")
                    
            else:
                print("⚠️ Pas de données temporelles disponibles")
                
        except Exception as e:
            print(f"❌ Erreur lors de l'analyse temporelle: {e}")

    def generate_report(self):
        """Génération du rapport final"""
        print("\n📋 === RAPPORT FINAL ===")
        
        try:
            report = self.utils.generate_flood_report()
            
            # Sauvegarde du rapport
            report_filename = f"rapport_inondations_{self.department_name}_{datetime.now().strftime('%Y%m%d')}.txt"
            
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write(report)
            
            print(f"💾 Rapport sauvegardé: {report_filename}")
            print("\n" + "="*60)
            print(report)
            print("="*60)
            
        except Exception as e:
            print(f"❌ Erreur lors de la génération du rapport: {e}")

    def run_complete_demo(self):
        """Exécution de la démonstration complète"""
        try:
            # 1. Vérification système
            system_ok = self.run_system_check()
            
            if not system_ok:
                print("\n⚠️ Le système présente des problèmes. Démonstration limitée.")
            
            # 2. Explication MNDWI
            self.demonstrate_mndwi_calculation()
            
            # 3. Statistiques actuelles
            self.show_flood_statistics()
            
            # 4. Analyse temporelle
            self.demonstrate_temporal_analysis()
            
            # 5. Rapport final
            self.generate_report()
            
            print("\n🎉 === DÉMONSTRATION TERMINÉE ===")
            print("✅ Le système SEKHEM est prêt pour la surveillance des inondations")
            print("🌊 L'analyse MNDWI fournit une détection précise des zones d'eau")
            print("📊 Les données peuvent être exportées pour analyse approfondie")
            print("🗺️ Les cartes sont disponibles via l'interface Streamlit")
            
        except Exception as e:
            print(f"❌ Erreur durant la démonstration: {e}")
            raise

def main():
    """Fonction principale"""
    print("🚀 Démarrage de la démonstration SEKHEM...")
    
    # Paramètres par défaut
    department = "Bignona"  # Changez selon vos besoins
    
    try:
        # Création et lancement de la démonstration
        demo = FloodDemo(department_name=department)
        demo.run_complete_demo()
        
    except KeyboardInterrupt:
        print("\n⏹️ Démonstration interrompue par l'utilisateur")
    except Exception as e:
        print(f"❌ Erreur critique: {e}")
        print("\n🔧 Solutions possibles:")
        print("1. Vérifiez votre connexion Internet")
        print("2. Authentifiez-vous à Google Earth Engine: ee.Authenticate()")
        print("3. Vérifiez que tous les modules sont installés")
        print("4. Contactez l'administrateur système")
        
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)