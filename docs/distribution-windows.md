# Distribution Windows

Shrimp'It est distribué sous deux formes autonomes : elles embarquent Python, Qt et toutes les dépendances.
Aucune installation de Python, aucun terminal et aucune configuration ne sont nécessaires pour l'utilisateur.
Cible : Windows 10 ou 11, 64 bits.

| Fichier | Usage |
| --- | --- |
| `ShrimpIt-vX.Y.Z-Windows-Portable.zip` | Version portable : extraire, puis double-cliquer sur `ShrimpIt.exe`. |
| `ShrimpIt-vX.Y.Z-Windows-Setup.exe` | Installateur classique avec raccourcis et désinstallation. |

`X.Y.Z` est la version déclarée dans [`src/shrimpit/__init__.py`](../src/shrimpit/__init__.py).

## Pour l'utilisateur

### Version portable

1. Télécharger `ShrimpIt-vX.Y.Z-Windows-Portable.zip`.
2. Clic droit › **Extraire tout…**, vers n'importe quel dossier (Bureau, Documents, clé USB…).
3. Double-cliquer sur `ShrimpIt.exe`.

L'archive contient `ShrimpIt.exe` et son dossier `_internal\`, qui doivent rester côte à côte.
Pour mettre à jour, supprimer l'ancien dossier et extraire la nouvelle archive. Pour supprimer l'application,
supprimer le dossier.

### Installateur

1. Télécharger puis lancer `ShrimpIt-vX.Y.Z-Windows-Setup.exe`.
2. Suivre l'assistant : licence, dossier, raccourci sur le bureau (facultatif), puis **Installer**.
3. Cocher **Exécuter Shrimp'It** pour l'ouvrir à la fin.

- Installation par défaut pour l'utilisateur courant, sans droits administrateur, dans
  `%LOCALAPPDATA%\Programs\Shrimpit`. Un administrateur peut choisir une installation pour tous les utilisateurs.
- Raccourci **Shrimp'It** dans le menu Démarrer ; raccourci sur le bureau en option.
- **Mise à jour** : lancer le Setup d'une version plus récente. Il remplace l'installation existante, au même
  endroit, sans créer de doublon ; si Shrimp'It est ouvert, l'installateur propose de le fermer.
- **Désinstallation** : Paramètres Windows › Applications › Applications installées › Shrimp'It. La
  désinstallation demande si les préférences, l'historique et les journaux doivent aussi être supprimés ; la
  réponse par défaut est **Non**. Les images ne sont jamais supprimées.
- Installation sans interface (déploiement, futur lanceur) :
  `ShrimpIt-vX.Y.Z-Windows-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER` ;
  désinstallation : `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` (les données personnelles sont
  alors toujours conservées).

### Données personnelles

Les deux versions enregistrent leurs données hors de leur propre dossier, ce qui permet d'installer
l'application dans un dossier en lecture seule et de conserver les réglages lors des mises à jour :

- historique et journaux : `%LOCALAPPDATA%\BlueShrimp\Shrimpit` ;
- préférences : registre, `HKEY_CURRENT_USER\Software\BlueShrimp\Shrimpit`.

La version portable et la version installée partagent donc les mêmes réglages sur un même compte Windows.

### Avertissement SmartScreen

Les exécutables ne sont pas signés numériquement. Au premier lancement d'un fichier téléchargé, Windows peut
afficher « Windows a protégé votre ordinateur » : cliquer sur **Informations complémentaires**, puis
**Exécuter quand même**.

## Pour le développeur

### Outils nécessaires

- Windows 10 ou 11, 64 bits.
- Python 3.11 ou supérieur, **64 bits**, avec le lanceur `py` ou `python` dans le `PATH`.
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) : `winget install JRSoftware.InnoSetup`. Le script le trouve
  dans le `PATH` ou dans les dossiers d'installation habituels.
- Un accès Internet au premier build, pour installer PySide6, Pillow et PyInstaller.

PyInstaller est déclaré dans l'extra `build` de [`pyproject.toml`](../pyproject.toml) ; aucune autre dépendance
n'est nécessaire.

### Générer les deux distributions

Depuis la racine du dépôt :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

Le script :

1. lit la version dans `src/shrimpit/__init__.py` (format `X.Y.Z` obligatoire) ;
2. vérifie l'interpréteur (Python 3.11+ 64 bits) et Inno Setup ; crée `.venv` s'il n'existe pas et y installe
   `-e ".[build]"` si Pillow, PySide6, PyInstaller ou Shrimp'It manquent ;
3. construit `dist\ShrimpIt\` avec PyInstaller ([`packaging/shrimpit.spec`](../packaging/shrimpit.spec)) ;
4. crée l'archive portable, l'extrait dans un dossier temporaire dont le nom contient des espaces et y lance
   `ShrimpIt.exe --self-test` avec un `PATH` sans Python ;
5. compile l'installateur ([`packaging/shrimpit.iss`](../packaging/shrimpit.iss)) ;
6. affiche la taille et l'empreinte SHA-256 de chaque livrable.

Options : `-Python <chemin\python.exe>` pour utiliser un autre environnement, `-SkipInstaller` pour ne produire
que l'archive portable. Un build complet prend environ une minute une fois les dépendances installées.

### Fichiers générés

| Emplacement | Contenu |
| --- | --- |
| `release\` | Les deux livrables à publier. |
| `dist\ShrimpIt\` | Application compilée, identique au contenu de l'archive portable. |
| `build\pyinstaller\` | Fichiers intermédiaires de PyInstaller, dont l'icône `.ico` générée. |

Ces trois dossiers sont exclus de Git. Aucun binaire ne doit être ajouté au dépôt.

### Préparer une nouvelle version

1. Modifier `__version__` dans `src/shrimpit/__init__.py`. C'est la seule source de version : elle alimente
   les noms des livrables, les propriétés de `ShrimpIt.exe`, l'installateur et la page Paramètres.
2. Mettre à jour la mention « Version actuelle » du [README](../README.md).
3. Lancer les contrôles : `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check.ps1`.
4. Lancer `scripts\build_windows.ps1`.
5. Vérifier à la main, de préférence sur un Windows sans Python : installation par-dessus la version
   précédente, lancement depuis le menu Démarrer, une compression, un agrandissement, l'enregistrement d'un
   réglage, puis la désinstallation.
6. Publier manuellement les deux fichiers de `release\` dans une GitHub Release `vX.Y.Z`, avec leurs
   empreintes SHA-256.

Ne jamais modifier l'`AppId` de `shrimpit.iss` : Windows s'en sert pour reconnaître les mises à jour et la
désinstallation. Les noms des livrables (`ShrimpIt-vX.Y.Z-Windows-Portable.zip`,
`ShrimpIt-vX.Y.Z-Windows-Setup.exe`) doivent rester stables pour les outils qui les téléchargeront.
