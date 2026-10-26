# Architecture et choix techniques

Document destiné aux personnes qui modifient le code. L’installation et l’utilisation sont décrites
dans le [README](../README.md).

## Organisation

```text
Shrimpit/
├── README.md                 Installation et utilisation
├── pyproject.toml            Version, dépendances et outils
├── requirements-tested.txt   Versions directes de référence
├── LICENSE                   Licence du code
├── docs/                     Ce document et les captures du README
├── scripts/
│   ├── check.ps1             Ruff, formatage et tests
│   ├── security.ps1          pip check, Bandit et pip-audit
│   ├── verify_compression.py Mesure des sorties de compression
│   ├── build_windows.ps1     Version autonome : PyInstaller, autotest, ZIP et installateur
│   └── build_preview_examples.py Régénération des exemples avant/après
├── packaging/                Recette PyInstaller, lanceur et script Inno Setup
├── .github/workflows/        Contrôles à chaque push et audit de sécurité hebdomadaire
├── tests/                    Tests du moteur et de l’interface
└── src/shrimpit/
    ├── __main__.py           Point d’entrée
    ├── engine.py             Compression et agrandissement Pillow
    ├── upscale.py            Modes, interpolation et netteté d’agrandissement
    ├── limits.py             Plafonds de sortie et contrôle de la RAM
    ├── processing.py         Aperçus, options et planification des sorties
    ├── history.py            Historique local et écritures JSON atomiques
    ├── examples.py           Lecture des aperçus de démonstration
    ├── filenames.py          Validation des noms de fichiers Windows
    ├── errors.py             Erreurs métier et messages d’erreur en français
    ├── preferences.py        Lecture fiable des préférences
    ├── diagnostics.py        Journaux locaux de taille limitée
    ├── resources.py          Chemins des assets et du dossier de données
    ├── selftest.py           Autotest d’une version installée ou empaquetée
    ├── assets/               Images, GIF, sons, police et licence
    └── gui/
        ├── main_window.py    Fenêtre principale et navigation
        ├── navigation.py     Sidebar et son animation
        ├── theme.py          Couleurs, police et icônes
        ├── widgets.py        Widgets réutilisables
        ├── comparison.py     Comparaison avant/après avec séparation mobile
        ├── workers.py        Traitements dans des threads Qt
        ├── history_thumbnails.py Miniatures de l’historique hors du thread d’interface
        ├── output_settings.py Format, qualité, facteur, dimensions et modèle de nom
        ├── upscale_controls.py Choix du mode et réglages de netteté
        ├── notifications.py  Son et notification de fin
        └── pages/
            ├── common.py     En-têtes partagés
            ├── home.py       Accueil
            ├── processing.py Compression et agrandissement
            ├── progress.py   Progression et bilan
            ├── history.py    Lots, fiches de détails et suppressions des références
            └── settings.py   Paramètres
```

## Principes

- Le moteur (`engine.py`, `upscale.py`, `limits.py`, `processing.py`, `history.py`) ne dépend pas de Qt.
  L’interface construit des `Options`, puis confie les calculs aux workers.
- Les workers transmettent les résultats par signaux ; les widgets ne sont modifiés que dans le thread
  principal. Les workers d’aperçu et d’export partagent un verrou : un seul calcul Pillow lourd à la fois,
  avec une attente annulable.
- Une sortie est créée en mode exclusif (`open("xb")`) : un fichier existant n’est jamais remplacé.
  En cas d’erreur gérée, le fichier partiel est supprimé.
- Les erreurs de Pillow et du système sont traduites par `errors.describe_error` ; le détail technique
  reste dans les journaux (`%LOCALAPPDATA%\BlueShrimp\Shrimpit\logs`, trois fichiers de 1 Mo au maximum).
- Les pixels sont normalisés en RGB/RGBA 8 bits ; l’orientation EXIF est appliquée, puis les métadonnées
  et profils ICC sont retirés en recréant l’image. Les niveaux de gris 16 bits (`I;16`) sont divisés par
  256 avant conversion, car une conversion directe de Pillow écrête les valeurs et blanchit l’image.
- Interface et documentation en français ; commentaires et docstrings en anglais.

`gui/pages/processing.py` gère la liste d’images, les aperçus et l’export ; les réglages de sortie et le
modèle de nom sont dans `gui/output_settings.py`.

## Agrandissement

| Mode | Traitement |
| --- | --- |
| Photographie | Lanczos, puis masque de netteté (40 %, 0,8 px, seuil 3 par défaut, désactivable) |
| Illustration | Bicubic par défaut, Lanczos au choix, sans netteté |
| Pixel Art | Nearest Neighbor, facteurs entiers et PNG uniquement |

**Réglage photo.** Quatre variantes ont été comparées en ×2, ×3 et ×4 sur la photographie de référence
`astronaut` de [scikit-image](https://scikit-image.org/docs/0.25.x/api/skimage.data.html#skimage.data.astronaut),
réduite puis réagrandie : sans netteté, 40 %/0,8 px/3, 60 %/1,0 px/3 et 100 %/1,5 px/2. La variante
forte accentue visiblement les contours. 40 %/0,8 px/3 a été retenue comme compromis discret ; ce choix
repose sur une seule image de référence, pas sur une validation universelle.

**Illustration.** Sur une transition nette, Bicubic dépasse de 11 à 12 niveaux contre 17 à 19 pour Lanczos,
d’où un halo moins marqué : Bicubic est donc le réglage par défaut.

**Transparence.** Pillow redimensionne les RGBA en alpha prémultiplié, ce qui évite les franges de couleurs
cachées. La netteté n’agit que sur RGB, hors des zones transparentes et de leur voisinage. En JPEG, le fond
blanc est appliqué après le redimensionnement. Pixel Art répète les valeurs exactes, sans prémultiplication.

**xBRZ** n’est pas intégré : sa licence GPLv3 imposerait ses conditions au projet MIT, il n’existe pas de
wrapper Python/Windows maintenu, et son lissage modifie le dessin des pixels.

## Grands exports

- Entrée limitée à 25 MP ; sortie d’agrandissement limitée à 400 MP (×4 d’une source de 25 MP).
- WebP : 16 383 pixels maximum par côté, vérifiés avant traitement.
- Aperçu automatique jusqu’à 25 MP de sortie ; au-delà, seul l’export complet est proposé.
- Au-delà de 25 MP, `limits.py` lit la RAM disponible avec l’API Windows et estime le besoin :
  12 octets par pixel de sortie en Pixel Art, 20 en Illustration ou photo sans netteté, 32 avec netteté,
  plus 16 octets par pixel source et 128 Mio de marge. L’estimation doit tenir dans 80 % de la RAM
  disponible. Si la RAM ne peut pas être lue (hors Windows), ces grands exports sont refusés.

Ces coefficients sont prudents mais ne garantissent pas l’absence de `MemoryError`, qui reste gérée.

## Historique

Fichier : `%LOCALAPPDATA%\BlueShrimp\Shrimpit\history.json`. Il ne contient que des chemins et des
métadonnées, jamais d’image ni de miniature. Les dates sont en UTC.

```text
{ "version": 1, "batches": [ { "id", "created_at", "images": [
    { "id", "created_at", "source", "destination",
      "operation": "compression" | "upscale",
      "parameters": { …réglages et dimensions réellement appliqués… },
      "input_bytes", "output_bytes" } ] } ] }
```

- Chaque image réussie est enregistrée depuis le worker d’export. Une erreur d’historique est signalée
  dans le bilan sans invalider l’image exportée.
- Écriture atomique : fichier temporaire dans le même dossier, `fsync`, puis `os.replace`. Un verrou de
  fichier (`history.lock`) empêche deux instances d’écrire en même temps ; une instance attend jusqu’à
  2 secondes que l’autre ait terminé avant de signaler une erreur.
- Un JSON invalide, ou une date impossible à convertir en heure locale, est copié dans
  `history-invalid-<id>.json`, puis remplacé par un historique vide. Au-delà de 32 Mio, le fichier n’est
  pas chargé ; « Effacer tout l’historique » reste disponible et le remplace après confirmation.
- Le fichier entier est réécrit à chaque image : suffisant pour quelques milliers d’entrées. Pour des
  dizaines de milliers, il faudrait passer à SQLite et à une pagination.
- Dans l’interface, les lots se déplient par groupes de 20 et les miniatures sont décodées une à une hors
  du thread d’interface. Supprimer une référence ne supprime jamais l’image sur le disque.

## Assets

- `backgrounds/` : `ocean.png` (pixel art dessiné sur une grille de 4 pixels, réduit de moitié au plus
  proche voisin sans perte) et `sidebar-shrimpy.png`.
- `icons/` : `home`, `image`, `expand`, `history` et `settings`, en carrés de 256 px. Les marges
  transparentes sont compensées au rendu ; si un PNG manque, un dessin Qt simple le remplace.
- `branding/shrimpy.png`, `animations/*.gif` et `sounds/finish.ogg`.
- `examples/` : aperçus de démonstration, régénérables avec `scripts/build_preview_examples.py`
  (voir [leur documentation](../src/shrimpit/assets/examples/README.md)).
- La police Chakra Petch est fournie avec sa licence dans `assets/licenses/`. Elle ne contient pas
  l’apostrophe typographique : le nom affiché est donc `Shrimp'It`.

Les droits des ressources sont décrits dans la section « Licence et ressources » du
[README](../README.md#licence-et-ressources).

## Distribution Windows

`scripts/build_windows.ps1` enchaîne les étapes suivantes :

1. PyInstaller construit un dossier `dist\Shrimpit\` (mode « un dossier », sans console) à partir de
   `packaging/shrimpit.spec`. L’icône `.ico` est générée depuis `branding/shrimpy.png` et les informations
   de version Windows depuis `shrimpit.__version__`.
2. Le rendu OpenGL logiciel, Qt Quick/QML et les traductions Qt autres que le français sont retirés :
   l’application n’utilise que Qt Widgets et Qt Multimedia (environ 116 Mo au lieu de 156 Mo).
3. `Shrimpit.exe --self-test <rapport>` est lancé avec un `PATH` réduit aux dossiers de Windows et sans
   variable `PYTHON*`. L’autotest (`selftest.py`) convertit les exemples dans les trois formats, essaie les
   trois modes d’agrandissement, décode les animations et le son, vérifie la traduction Qt et construit la
   fenêtre principale avec des préférences et un historique temporaires.
4. Le dossier est compressé en `Shrimpit-<version>-windows-x64-portable.zip`, puis Inno Setup compile
   `packaging/shrimpit.iss` en `Shrimpit-<version>-windows-x64-setup.exe`.

L’installateur s’installe par défaut pour l’utilisateur courant (`{autopf}` sans droits administrateur),
supprime `_internal\` avant une mise à jour pour ne garder aucune ancienne bibliothèque, et enregistre
l’identifiant `BlueShrimp.Shrimpit` sur le raccourci pour que la barre des tâches regroupe les fenêtres.
L’`AppId` de `shrimpit.iss` ne doit jamais changer : Windows l’utilise pour reconnaître les mises à jour.
La désinstallation ne supprime ni les images ni `%LOCALAPPDATA%\BlueShrimp\Shrimpit`.

## Vérifications

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
.\.venv\Scripts\python.exe .\scripts\verify_compression.py --output "$env:TEMP\shrimpit-mesures"
```

`verify_compression.py` convertit les PNG des assets (ou les images passées avec `--inputs`) en PNG,
JPEG et WebP à plusieurs qualités, contrôle dimensions, transparence et fidélité PNG, et écrit
`measurements.csv` et `summary.json` dans un nouveau dossier. Les tests graphiques s’exécutent hors écran :
l’affichage réel, les notifications et le son restent à vérifier manuellement.
