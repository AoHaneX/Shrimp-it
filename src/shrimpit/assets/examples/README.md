# Exemples de prévisualisation

Ces fichiers sont des illustrations de démonstration. Ils ne sont jamais ajoutés aux images
de l’utilisateur, à un export ou à l’historique. Aucun téléchargement n’est nécessaire au lancement.

| Fichier | Contenu |
| --- | --- |
| `compression-before.png` | Illustration de référence, 768 × 512 px |
| `compression-after.jpg` | Conversion réelle avec le moteur de Shrimp'It, JPEG qualité 80 |
| `enlargement-before.png` | Même illustration réduite à 384 × 256 px |
| `enlargement-after.png` | Agrandissement réel ×2, Photographie/Lanczos, netteté 0,8 px / 40 % / seuil 3 |

Les réglages de démonstration sont fixes et indiqués sous l’aperçu. Ils ne prétendent pas refléter
les réglages que l’utilisateur change avant d’importer sa propre image.
Les tailles de fichiers et dimensions affichées proviennent des fichiers présents.

## Provenance

Illustration source créée le 11 octobre 2026 avec l’outil intégré **imagegen**, puis préparation
des exemples avec Pillow et les fonctions `convert_image` / `upscale_image` de Shrimp'It.
L’application reste un logiciel de traitement local sans IA : cette génération a uniquement servi
à créer la ressource graphique incluse dans le projet.

Prompt de génération :

> Use case: illustration-story. Asset type: built-in sample image for Shrimp'It, a desktop image compression and enlargement application. Create one polished landscape 3:2 digital illustration of a quiet rocky ocean cove with turquoise water, pale sand, a small lighthouse on a distant headland and clouds in a blue sky. Natural clean colors, fine readable rock and water textures, crisp illustrated edges and gradients, pleasing balanced composition. This will be used to compare the exact same image before and after deterministic Pillow processing, so output just one complete scene, no comparison layout. No text, no logo, no frame, no watermark, no shrimp mascot. Approximately 1536 by 1024.

## Remplacement

Depuis la racine du projet, fournir une autre image avec :

```powershell
.\.venv\Scripts\python.exe .\scripts\build_preview_examples.py 'C:\Images\mon-exemple.png'
```

Le script conserve les proportions de la source, remplace les quatre fichiers d’exemple et
prépare des conversions réellement comparables. Il ne modifie pas l’image source.
Relancer l’application après remplacement pour renouveler les aperçus conservés en mémoire.
