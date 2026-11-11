# Historique des versions

Chaque section `## X.Y.Z` devient la partie « Nouveautés » des notes de la release GitHub `vX.Y.Z`
(`packaging/reefkit_release.py`).

## 1.3.0

### Ajouts

- **Palette PNG affinée** : quand la palette rapide est refusée, Shrimp'It essaie une palette construite par
  le quantificateur ExoQuant (licence MIT, intégré), puis l'affine jusqu'à trois fois en redonnant leur place
  aux couleurs rares (liserés, reflets). Elle n'est gardée que si elle passe les mêmes contrôles de fidélité
  qu'avant, sans seuil assoupli. Exemple : une illustration transparente au halo lumineux passe de 1,85 Mo à
  289 Ko (−84 %) au lieu de rester en PNG fidèle ; un pixel art agrandi de 962 Ko à 137 Ko. Les photographies
  et les dégradés restent en PNG fidèle.

### Distribution

- Le moteur de palette est une petite DLL compilée depuis ses sources C à chaque construction ; sans elle,
  l'application garde le comportement de la 1.2.0. Les licences d'ExoQuant et du runtime mingw-w64 sont
  fournies avec l'application.

## 1.2.0

### Ajouts

- **PNG déjà optimisés jamais alourdis** : en compression PNG, l'encodage d'origine d'un PNG est réutilisé,
  sans ses métadonnées, quand il est plus léger et redonne exactement les mêmes pixels. Sur 400 PNG
  d'applications Windows, 35 ressortaient plus lourds qu'à l'entrée (jusqu'à +54 %) ; plus aucun désormais.
- Mesures avant/après et limites mises à jour dans le README (mascotte −90,7 %, icône −77,0 %, dégradé et
  photo gardés en PNG fidèle).

## 1.1.1

### Distribution

- Version de maintenance, sans changement dans l'application : la documentation désigne le lanceur de la
  suite sous son nouveau nom, ReefKit Launcher.

## 1.1.0

### Ajouts

- **Compression PNG automatique** : en choisissant PNG, Shrimp'It essaie une palette de 256 couleurs et ne
  la garde que si le fichier est plus léger et le rendu fidèle sur fond blanc et noir (fond transparent
  conservé, contours semi-transparents propres, pas de bandes). Sinon, le PNG fidèle est conservé. Exemple :
  la mascotte transparente passe de 507 Ko à 47 Ko. L'agrandissement, dont le mode Pixel Art, n'est pas
  modifié.
- L'encodage retenu est indiqué sous l'aperçu et dans l'historique.

### Corrections

- Limites de côté JPEG et WebP vérifiées avant tout traitement.
- Aperçu d'agrandissement PNG plus rapide, avec un poids estimé.
- Historique limité aux 5 000 derniers exports ; avertissement d'historique illisible affiché une seule fois.
- Messages d'erreur identiques à l'import et à l'export ; journaux toujours écrits quand une autre instance
  est ouverte ; glissement de la comparaison plus fluide.

### Distribution

- Livrables nommés selon la convention ReefKit lue par ReefKit Launcher : `ShrimpIt-v1.1.0-win64.zip`,
  `ShrimpIt-v1.1.0-setup.exe` et `SHA256SUMS.txt`. Les releases précédentes gardent leurs noms d'origine.

## 1.0.0

Première version Windows publique : installateur (`ShrimpIt-v1.0.0-Windows-Setup.exe`) et version portable
(`ShrimpIt-v1.0.0-Windows-Portable.zip`), autonomes, pour Windows 10 et 11, 64 bits.
