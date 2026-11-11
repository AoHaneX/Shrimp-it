# Shrimp'It

[![Checks](https://github.com/AoHaneX/Shrimp-it/actions/workflows/checks.yml/badge.svg)](https://github.com/AoHaneX/Shrimp-it/actions/workflows/checks.yml)

Application de bureau pour **compresser, convertir et agrandir des images localement**, avec une interface océanique en pixel art.

Projet personnel développé dans l’univers **ReefKit**, dans le cadre de mon parcours de développeur Python junior. Il me permet de travailler la séparation entre interface et traitement d’images, les tests et la distribution d’une application. Version actuelle : **1.2.0**, destinée à Windows.

Les traitements utilisent **Pillow**, sans modèle d’IA ni compte utilisateur. L’interface est construite avec **PySide6**. L’application fonctionne indépendamment des autres projets ReefKit.

## Fonctionnalités

### Compresser et convertir

Importez une ou plusieurs images, choisissez le format de sortie et comparez le résultat avant d’enregistrer. La compression conserve les dimensions de l’image.

![Page Compression de Shrimp'It avec comparaison avant/après et réglages de sortie](docs/images/compress.jpg)

Trois formats de sortie sont disponibles :

| Format | Fonctionnement et usage |
| --- | --- |
| **JPEG** | Pour les photographies : le réglage de qualité permet de trouver un compromis entre poids et détails. La transparence est remplacée par un fond blanc. |
| **PNG** | Pour conserver la transparence. Sans curseur de qualité : Shrimp'It choisit seul entre une palette de 256 couleurs, nettement plus légère, et l’encodage fidèle, selon le critère décrit ci-dessous. |
| **WebP** | Une autre possibilité pour réduire le poids, avec qualité réglable et conservation de la transparence. L’encodage utilisé ici est avec perte, comme pour le JPEG. |

Pour JPEG et WebP, diminuer la qualité peut alléger le fichier, mais aussi rendre la perte de détails visible. L’aperçu permet de choisir le compromis adapté à chaque image ; un fichier plus léger n’est pas garanti.

#### Compression PNG automatique

En compression, le format PNG compare plusieurs encodages, entièrement en local. Les variantes 2 à 4 sont **avec perte** : elles modifient légèrement les pixels et ne sont gardées que si les contrôles ci-dessous sont respectés. Le PNG fidèle reste **sans perte**.

1. **PNG fidèle** : les pixels normalisés, encodés sans perte et optimisés (le seul encodage des versions précédant la 1.1.0). Si la source est déjà un PNG, son propre encodage est aussi essayé, réduit aux blocs qui portent les pixels (`IHDR`, `PLTE`, `tRNS`, `IDAT`, `IEND`) : textes, EXIF, profils ICC, gamma et date sont retirés comme avant. Il n’est gardé que s’il est plus léger et qu’une fois relu, il redonne exactement les mêmes pixels (pas de PNG 16 bits, pas de rotation EXIF, pas de bloc endommagé). Un PNG déjà optimisé par un autre outil n’est ainsi plus réencodé en un fichier plus lourd (« PNG fidèle, encodage d’origine sans métadonnées »).
2. **PNG à palette** : 256 couleurs au maximum, opacité comprise. Une image qui contient déjà 256 couleurs ou moins est convertie sans aucune perte ; les autres sont réduites par l’octree rapide de Pillow, après avoir vidé la couleur cachée sous les pixels totalement transparents.
3. **PNG à palette affinée** (1.3.0) : essayé quand la palette rapide est refusée. Le quantificateur [ExoQuant](https://github.com/exoticorn/exoquant) (licence MIT, intégré sous forme de DLL) construit une palette de 256 couleurs à partir d’un échantillon régulier de 192 × 192 pixels, sans tramage. La palette est ensuite **affinée** jusqu’à trois fois : les pixels dont l’écart dépasse 16 niveaux sur fond blanc ou noir sont réinjectés dans l’histogramme (32 768 au plus par passe), ce qui donne leur propre entrée aux couleurs rares d’un liseré ou d’un reflet. Chaque passe subit le contrôle complet ci-dessous ; l’affinage s’arrête dès qu’une passe est acceptée, ou dès qu’elle échoue sur les bandes ou le PSNR global, que l’affinage ne sait pas corriger. Une entrée de palette entièrement transparente est réservée aux pixels d’opacité nulle : le fond reste invisible.
4. **PNG à couleurs réduites, opacité d’origine** : essayé quand les palettes sont refusées et que l’image a des pixels semi-transparents. Les couleurs sont réduites à 256, mais l’opacité de chaque pixel est recopiée telle quelle.

Une variante à palette n’est retenue que si son fichier est plus léger que le meilleur PNG fidèle et si, une fois rouverte, elle garde les dimensions, laisse chaque pixel totalement transparent à 0 d’opacité et respecte tous les seuils suivants, **identiques pour les trois variantes**, mesurés après composition sur fond blanc **et** sur fond noir (le pire des deux compte) :

| Critère | Seuil | Rôle |
| --- | --- | --- |
| PSNR global | ≥ 34 dB | Écart moyen sur toute l’image |
| Pire bloc de 4 × 4 px | écart moyen ≤ 24 niveaux sur 255 | Détecte un petit contour perdu, invisible dans une moyenne globale |
| Faux contours | ≤ 1 % des pixels | Détecte les bandes : marche d’au moins 3 niveaux là où l’original varie d’au plus 1 |
| Bords semi-transparents | écart moyen ≤ 8, 99ᵉ centile ≤ 32 | Contours anticrénelés propres |

Sinon, le PNG fidèle est conservé. Le calcul est déterministe : l’aperçu et l’export font le même choix, affiché sous l’aperçu (« Encodage retenu ») et dans le détail de l’historique. L’agrandissement, y compris le mode Pixel Art, garde l’encodage fidèle.

**Repli sans le moteur ExoQuant** : si `exoquant.dll` est absente (sources lancées sans l’avoir compilée), illisible ou incomplète, la variante 3 est simplement ignorée et Shrimp'It se comporte comme la 1.2.0. Un manque de mémoire pendant la construction ou la mesure d’une variante conserve aussi le PNG fidèle. Le portable et l’installateur embarquent la DLL, et leur autotest vérifie qu’elle se charge.

Ces seuils ont été choisis à partir des essais du 6 novembre 2026 (Pillow 13.0.0, Python 3.13) et n’ont pas été modifiés pour la palette affinée. Les palettes refusées montraient des bandes dans le ciel ou les dégradés, des taches de couleur, ou un pixel de fond devenu visible. Mesures refaites le 9 novembre 2026 pour la 1.2.0 (« 1.1.x » : même calcul sans l’encodage d’origine) :

| Image | Taille | Fichier source | PNG fidèle (Pillow) | 1.1.x | 1.2.0 | Résultat |
| --- | --- | --- | --- | --- | --- | --- |
| Mascotte transparente (`branding/shrimpy.png`) | 1185 × 1185 | 507 067 o | 409 907 o | 46 945 o | **46 945 o** (−90,7 %) | Palette : 41,9 dB, pire bloc 20, faux contours 0,59 %, bords 3,8 / 18 |
| Icône transparente (`icons/settings.png`) | 256 × 256 | 92 412 o | 92 412 o | 21 247 o | **21 247 o** (−77,0 %) | Palette : 34,8 dB, pire bloc 14, faux contours 0,31 %, bords 7,8 / 19 |
| Dégradé de couleurs synthétique | 512 × 512 | 5 936 o | 2 376 o | 2 376 o | 2 376 o (−60,0 %) | Fidèle : la palette pèserait 10 054 o et crée 6,9 % de faux contours |
| Paysage (fond d’écran Windows `ThemeA/img20.jpg`, réduit à 1600 px et enregistré en PNG) | 1600 × 1000 | 738 047 o | 667 747 o | 667 747 o | 667 747 o (−9,5 %) | Fidèle : la meilleure palette crée 2,3 à 3,7 % de faux contours |
| PNG déjà optimisé (niveaux de gris 4 bits avec un bloc texte, généré par les tests) | 64 × 64 | 2 207 o | 4 699 o | 2 240 o (**+1,5 %**) | **2 180 o** (−1,2 %) | Encodage d’origine, pixels identiques, bloc texte retiré |

Sur 400 PNG d’applications Windows installées (5 Ko à 3 Mo), 35 ressortaient plus lourds qu’à l’entrée en 1.1.x, jusqu’à +54 % (palette d’une ombre, 14 455 → 22 227 o) ; aucun en 1.2.0, où 29 gardent leur encodage d’origine. La vérification de l’encodage d’origine prend 0,2 s sur une image de 25 MP.

Contrôles complémentaires : une photographie de rue au téléphone (2064 × 1161, non versionnée) restait en PNG fidèle (pire bloc 34 avec la palette) ; les quatre autres icônes passent en palette (de −73 à −76 %), la barre latérale transparente aussi (127 793 → 24 799 o) ; l’illustration d’exemple (palette à 30,3 dB) et le décor pixel art `ocean.png` (pire bloc 43, des couleurs rares disparaissent) restent fidèles. Une image transparente entourée d’un large halo flou, couverte par les tests, illustre la quatrième variante : la palette rendait visibles des pixels de fond, la variante à opacité d’origine est retenue.

**Palette affinée, mesures du 11 novembre 2026** (moteur de l’application `convert_image`, Windows 11, Python 3.13, Pillow 13.0.0 ; temps médian de 3 exécutions, chacune dans un processus séparé ; sorties identiques octet pour octet d’une exécution à l’autre) :

| Image | Taille | Source | 1.2.0 | 1.3.0 | Temps 1.2.0 → 1.3.0 | Résultat 1.3.0 |
| --- | --- | --- | --- | --- | --- | --- |
| Illustration transparente avec halo lumineux (personnelle, non versionnée) | 1246 × 1263 | 1 848 369 o | 1 766 729 o (fidèle) | **289 367 o** (−84,3 %) | 0,9 → 1,7 s | Palette affinée, 3ᵉ passe : 36,4 dB, pire bloc 23, faux contours 0,27 %, bords 6,6 / 19 |
| Pixel art agrandi ×2 (non versionné) | 2880 × 2880 | 962 431 o | 962 431 o (fidèle) | **137 420 o** (−85,7 %) | 1,1 → 3,9 s | Palette affinée, 4ᵉ passe : 41,6 dB, pire bloc 23 |
| Pixel art synthétique, 320 couleurs | 576 × 576 | 24 147 o | 24 147 o | **10 342 o** (−57,2 %) | 0,06 → 0,11 s | Palette affinée |
| Illustration générée par IA, opaque (non versionnée) | 1183 × 1329 | 2 075 797 o | 1 905 612 o | 1 905 612 o | 1,1 → 1,3 s | Fidèle : 3,3 à 3,8 % de faux contours avec toutes les palettes essayées |
| Capture d’écran agrandie ×2 (non versionnée) | 3812 × 1932 | 1 629 525 o | 1 629 525 o | 1 629 525 o | 1,8 → 2,5 s | Fidèle : 2,5 % de faux contours dès la 1ʳᵉ passe, arrêt immédiat |
| Illustration synthétique de 25 MP, transparente | 5000 × 5000 | 7 244 874 o | 6 207 514 o | **1 300 785 o** (−82,0 %) | 19,4 → 20,5 s | Palette affinée ; pic mémoire 760 Mo dans les deux versions |

Pour comparaison, le fichier produit par un service en ligne pour l’illustration au halo pèse 434 028 o (−76,5 %) ; mesuré de la même façon, il obtient 37,9 dB, un pire bloc de 43 (168 blocs au-dessus de 24 contre 0 pour la 1.3.0) et 0,64 % de faux contours : il serait refusé par ces seuils. Aucune des deux versions n’est identique à l’original : à 100 % sur fond noir, les dégradés de l’étoile centrale et des ovales rouges sont un peu aplatis dans les deux cas (environ 31 à 33 dB localement), ce que le PSNR global moyenne avec le reste de l’image. Les mascottes, icônes, logos, photos synthétiques et images déjà indexées ou entièrement transparentes gardent exactement le même résultat qu’en 1.2.0 : la palette rapide y est acceptée ou l’encodage d’origine retenu avant que la palette affinée soit essayée.

Réglages essayés (illustration au halo et pixel art ×2 ; poids, ou « fidèle » quand aucune passe n’est acceptée) :

| Échantillon | Passes max. | Halo | Pixel art ×2 | Remarque |
| --- | --- | --- | --- | --- |
| 192 px | 1 (sans affinage) | fidèle (pire bloc 37-38) | fidèle (pire bloc 41) | Les couleurs rares manquent |
| 128 px | 4 | 287 595 o | fidèle | Plus rapide, moins régulier |
| **192 px** | **4** | **289 367 o** | **137 420 o** | **Retenu** |
| 192 px | 6 | 289 367 o | 137 420 o | Aucun gain |
| 256 px | 4 | 312 617 o | 146 456 o | Plus lourd, plus lent |
| 192 px, tramage ordonné 2 × 2 | 1 | 443 625 o, refusé | — | Le tramage crée 1,8 % de faux contours et alourdit le fichier |

Le mode « haute qualité » d’ExoQuant (optimisation de la palette après chaque division) donnait des résultats proches pour un temps 5 à 15 fois supérieur : il n’est pas utilisé.

Limites observées :

- Les photographies et les dégradés restent presque toujours en PNG fidèle : sans tramage, 256 couleurs y créent des bandes, palette affinée comprise. Pour ces images, JPEG ou WebP restent plus adaptés. Aucune réduction de 75 à 80 % n’est garantie.
- Le résultat d’une image proche des seuils dépend des réglages : une image refusée avec un échantillon de 192 px a été acceptée avec 128 px. Ces seuils mesurent des pixels et ne garantissent pas une différence invisible : vérifiez l’aperçu à 100 % sur les dégradés lumineux.
- Sur une image refusée, la palette affinée ajoute du temps de calcul (de +0,2 s à +0,7 s dans les essais ci-dessus) ; sur une image acceptée, elle ajoute jusqu’à 3 s pour 8 MP, et 1 s environ pour 25 MP.
- Un PNG déjà optimisé n’est jamais alourdi s’il est en 8 bits ou moins, sans rotation EXIF et intact. Un PNG 16 bits est ramené en 8 bits et peut, rarement, ressortir plus lourd.
- Le choix encode et compare plusieurs variantes. Mesuré en 1.2.0 sur une image transparente de 25 MP : 7,1 s et 0,74 Gio de mémoire au maximum, contre 2,2 s et 0,5 Gio pour le seul PNG fidèle ; sur une illustration opaque de 24 MP, 14,4 s et 0,59 Gio contre 12,9 s et 0,46 Gio. L’aperçu de compression fait le même calcul.
- Les seuils sont des mesures de pixels, pas une évaluation de la perception humaine ni de la gestion des couleurs.

### Agrandir sans IA

Choisissez un facteur **×2, ×3 ou ×4**, puis un mode adapté au contenu. Les modes Photographie et Illustration permettent aussi de saisir des dimensions personnalisées, avec conservation optionnelle des proportions.

![Page Agrandissement de Shrimp'It avec comparaison avant/après et mode Illustration](docs/images/upscale.jpg)

| Mode | Méthode utilisée | À quoi sert-il ? |
| --- | --- | --- |
| **Photographie** | **Lanczos**, avec netteté supplémentaire réglable et désactivable | Agrandir les photos en recherchant un rendu naturel. Une netteté légère peut renforcer les contours ; trop de netteté peut les rendre artificiels. |
| **Illustration** | **Bicubic** par défaut, ou **Lanczos** au choix | Agrandir dessins, logos et aplats. Bicubic donne des transitions douces ; Lanczos peut rendre les contours plus marqués. Comparez les deux selon l’image. |
| **Pixel Art** | **Nearest Neighbor** — le plus proche voisin | Agrandir chaque pixel en un bloc de même couleur, sans lissage ni netteté ajoutée. Ce mode utilise les facteurs entiers ×2, ×3 ou ×4 et le format PNG. |

Ces algorithmes calculent une image plus grande à partir des pixels existants : ils ne recréent pas les détails absents de l’original.

### Outils communs

- **Import multiple** par sélection de fichiers ou glisser-déposer, pour les JPEG, PNG et WebP statiques.
- **Comparaison avant/après** avec séparation mobile (souris, curseur ou flèches du clavier) ou affichage côte à côte, dimensions et poids. Des exemples apparaissent lorsqu’aucune image n’est chargée.
- **Traitement par lots** avec progression, bilan et annulation après l’image en cours. Les conflits de noms sont numérotés pour préserver les fichiers existants.
- **Historique local** des 5 000 derniers exports réussis, avec miniatures et paramètres. Au-delà, les références les plus anciennes sont oubliées automatiquement. Supprimer une entrée ne supprime pas les images.
- **Paramètres** pour les valeurs par défaut, l’animation du menu, le son et les notifications de fin, selon leur disponibilité sous Windows.

### Nommer tout un lot

Le champ **« Modèle de nom pour toutes les images »** contient par défaut `[original name]-min.jpg` en compression ou `[original name]-x2.png` en agrandissement. Le marqueur `[original name]` reprend le nom de chaque image **sans son extension**.

Vous pouvez ajouter un préfixe ou changer le suffixe : `web-[original name]-final.png` donne par exemple `web-plage-final.png` et `web-montagne-final.png`. Le modèle s’applique à tout le lot, même si vous changez l’image sélectionnée. Un exemple du nom obtenu apparaît sous le champ.

Le suffixe par défaut suit le facteur choisi (`-x2`, `-x3`, `-x4`) ou les dimensions personnalisées. Un modèle personnalisé reste conservé lorsque le facteur change ; son extension s’adapte au format de sortie. Gardez cette extension dans le champ. Sans le marqueur, un nom commun est utilisé et les doublons sont numérotés. Les originaux ne sont jamais renommés.

## Installation et lancement

Sans Python : utilisez la version portable (`ShrimpIt-vX.Y.Z-win64.zip`, à extraire puis lancer `ShrimpIt.exe`) ou l’installateur (`ShrimpIt-vX.Y.Z-setup.exe`), avec leurs empreintes dans `SHA256SUMS.txt`. Voir [Distribution Windows](docs/distribution-windows.md).

Depuis les sources, prérequis : **Windows 11**, **Python 3.11 ou supérieur** avec `pip`, et un accès Internet pour installer les dépendances. Les traitements fonctionnent ensuite localement.

Téléchargez ou clonez le dépôt, puis ouvrez PowerShell dans le dossier contenant `pyproject.toml` :

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m shrimpit
```

L’activation de `.venv` n’est pas nécessaire avec ces commandes explicites. Pour les lancements suivants, seule la dernière commande est requise. Après un déplacement du projet, recréez l’environnement virtuel et réinstallez le projet au lieu de réutiliser une `.venv` copiée.

Les dépendances sont déclarées dans [`pyproject.toml`](pyproject.toml) : `Pillow>=13.0,<14`, `PySide6-Essentials` et `PySide6-Addons` (`>=6.8,<7`). Seuls ces deux paquets de PySide6 sont installés : le paquet complet `PySide6` ajouterait environ 300 Mo de modules inutilisés (Qt WebEngine, Qt Pdf). [`requirements-tested.txt`](requirements-tested.txt) conserve les versions directes d’une validation antérieure ; ce n’est pas un verrou complet des dépendances.

L’installation crée aussi `.venv\Scripts\shrimpit.exe`, qui lance l’application sans fenêtre de console : un raccourci vers ce fichier suffit pour les lancements suivants. Une version Windows autonome, utilisable sans Python, peut être construite comme décrit dans [Version Windows autonome](#version-windows-autonome).

## Limites à connaître

- Entrées limitées aux **JPEG, PNG et WebP statiques de 25 mégapixels maximum**. Les GIF et animations ne sont pas pris en charge.
- Sorties agrandies jusqu’à **400 MP**, sous réserve de mémoire disponible et des limites du format (16 383 pixels par côté en WebP, 65 500 en JPEG, y compris en compression). L’aperçu automatique ne calcule pas les sorties de plus de 25 MP ; en agrandissement PNG, il affiche un poids estimé, l’export final étant optimisé. La mémoire est vérifiée avant chaque grand export. Voir les [grands exports](docs/architecture.md#grands-exports).
- Une optimisation peut produire un fichier plus volumineux. L’agrandissement interpole les pixels et ne recrée pas les détails absents.
- JPEG et WebP sont encodés avec perte. En compression, PNG peut passer à une palette de 256 couleurs, donc légèrement modifier les pixels, uniquement si les critères de la [compression PNG automatique](#compression-png-automatique) sont respectés ; sinon, et toujours en agrandissement, PNG conserve les pixels après normalisation RGB/RGBA 8 bits. Les niveaux de gris 16 bits sont ramenés proportionnellement sur 8 bits. La transparence est conservée en PNG/WebP et remplacée par un fond blanc en JPEG.
- L’orientation EXIF est appliquée ; les métadonnées, GPS et profils ICC sont ensuite retirés. Cette version n’est pas destinée à un flux colorimétrique exigeant ou à la conservation des images haute profondeur.

Les originaux ne sont pas remplacés. Une erreur d’écriture gérée nettoie la sortie partielle, mais une interruption brutale du programme peut laisser un fichier incomplet.

## Développement et vérifications

Installer les outils de développement, puis lancer les contrôles de style et les tests :

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1
```

`check.ps1` compile d’abord le moteur de palette `src\shrimpit\native\exoquant.dll` s’il manque ou si ses sources ont changé, puis exige qu’il se charge : il faut pour cela le compilateur de l’extra `build` (`pip install -e ".[build]"`, paquet `ziglang` épinglé, licence MIT, utilisé seulement à la construction). Pour le compiler à la main :

```powershell
.\.venv\Scripts\python.exe scripts\build_png_engine.py
```

Sans cette DLL, l’application fonctionne mais la palette affinée n’est pas essayée. Deux compilations successives produisent un fichier identique ; la DLL n’est pas versionnée.

Pour exécuter seulement les tests :

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Les outils de sécurité sont facultatifs ; la recherche de vulnérabilités nécessite Internet :

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[audit]"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\security.ps1
```

Le [workflow Checks](.github/workflows/checks.yml) lance ces contrôles et Bandit sous Windows avec Python 3.11 et 3.13, puis installe la wheel construite dans un environnement vierge et lance son autotest. La recherche de vulnérabilités ([workflow Security audit](.github/workflows/security.yml)) tourne chaque lundi et peut être lancée à la main : une faille publiée dans une dépendance est signalée sans bloquer les autres modifications. Les actions GitHub sont épinglées par empreinte de commit ; Dependabot propose chaque semaine leurs mises à jour et celles des dépendances Python.

### Version Windows autonome

Une seule commande produit, dans `release\`, l’archive portable et l’installateur, qui embarquent Python et toutes les dépendances. Elle nécessite [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`) ; l’option `-SkipInstaller` ne produit que l’archive.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Le script installe au besoin l’extra `build` dans `.venv`, recompile `exoquant.dll` depuis ses sources, puis lance `ShrimpIt.exe --self-test` sur l’archive extraite, sans Python dans le `PATH`. Outils, fichiers produits et préparation d’une nouvelle version : [Distribution Windows](docs/distribution-windows.md).

## Organisation et documentation

```text
src/shrimpit/        Moteur Pillow, historique et configuration
src/shrimpit/gui/    Fenêtre, pages, widgets et traitements en arrière-plan
src/shrimpit/assets/ Images, animations, son et police
tests/              Tests automatisés
scripts/            Vérification, préparation des exemples et construction Windows
packaging/          Recettes PyInstaller et Inno Setup
docs/               Architecture, distribution Windows et captures d’écran
```

L’[architecture et les choix techniques](docs/architecture.md) décrivent l’organisation du code, les modes d’agrandissement, les grands exports et le format de l’historique.

L’historique (`history.json`) et les journaux (`logs\`) sont enregistrés dans `%LOCALAPPDATA%\BlueShrimp\Shrimpit`, les préférences dans la clé de registre `HKEY_CURRENT_USER\Software\BlueShrimp\Shrimpit`. Supprimer ce dossier et cette clé remet l’application à zéro sans toucher aux images. Ces fichiers peuvent contenir des chemins personnels : ne les joignez pas publiquement sans les relire. Pour signaler un problème, indiquez la version de Shrimp'It (page Paramètres), la version de Python si vous lancez les sources, les étapes de reproduction, et utilisez une image non confidentielle.

## Pistes d’évolution

- Publication de l’archive portable et de l’installateur dans les GitHub Releases, compilés automatiquement par GitHub Actions.
- Préréglages expliqués (partage, site web, qualité élevée) avec estimation du poids.
- Redimensionnement vers une taille maximale, y compris la réduction.
- Import asynchrone pour les lots de plusieurs centaines d’images.
- Gestion des profils ICC et des images haute profondeur.

## Licence et ressources

Le **code source** est distribué sous la licence MIT. Le fichier [`LICENSE`](LICENSE) précise aussi ce qu’elle ne couvre pas.

Les **illustrations, mascottes, logos, icônes, fonds et animations propres à Shrimp'It et ReefKit** ont été créés par l’auteur du projet avec le générateur d’images d’OpenAI (ChatGPT, génération assistée par IA), pour cette application. L’application elle-même n’utilise aucune IA. Ces ressources, ainsi que les sons et les captures de `docs/images/`, sont exclues de la licence MIT : tous droits réservés, comme l’indique [`LICENSE`](LICENSE). Leur présence dans ce dépôt ou dans une version distribuée n’accorde pas d’autorisation de les réutiliser, modifier ou redistribuer. Toute réutilisation nécessite une autorisation écrite préalable.

Les ressources tierces restent soumises à leurs licences respectives, fournies dans `src/shrimpit/assets/licenses/` : police Chakra Petch (OFL 1.1), quantificateur ExoQuant de Dennis Ranke (MIT, copie modifiée dans `src/shrimpit/native/`, modifications listées en tête de `exoquant.c`) et code de démarrage du runtime mingw-w64 lié dans `exoquant.dll` par la chaîne Zig (domaine public, notice ZPL 2.1 du paquet). Aucune bibliothèque sous GPL n’est utilisée ; la provenance des exemples est décrite dans leur [documentation](src/shrimpit/assets/examples/README.md).
