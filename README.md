# Volvo Sensus Sync

## Introduction

**Volvo Sensus Sync** est un outil permettant de transcoder une bibliothèque musicale vers des fichiers MP3 compatibles avec le système multimédia **Volvo Sensus**.

Le logiciel analyse automatiquement une collection de fichiers audio (FLAC, MP3, etc.), convertit uniquement les morceaux nécessaires, réécrit leurs métadonnées, répartit la bibliothèque sur plusieurs partitions de taille donnée et génère un plan de synchronisation permettant de recopier les fichiers sur une clé USB dans un ordre compatible avec le firmware du véhicule.

Le projet est né de l'étude des nombreuses contraintes du lecteur multimédia Volvo Sensus, dont certaines ne semblent pas être documentées.

---

# Genèse du projet

Ce projet est né lorsque j'ai fait l'acquisition d'une **Volvo V40 millésime 2012** équipée du système multimédia **Sensus**.

Souhaitant écouter ma bibliothèque musicale depuis une clé USB, j'ai rapidement découvert que le lecteur était beaucoup plus exigeant que ne le laissait penser la documentation.
Celle-ci indique simplement que les fichiers MP3 sont supportés, sans préciser les nombreuses contraintes réellement imposées par le firmware.

Les premières difficultés rencontrées furent relativement classiques :

* seuls les systèmes de fichiers **FAT32** sont reconnus ;
* une table de partitions **MBR** est nécessaire ;
* une organisation en deux partitions d'environ 16 Go chacune fonctionne parfaitement.

Ces limitations sont compréhensibles pour un système conçu il y a plus d'une décennie.

En revanche, une seconde difficulté s'est révélée beaucoup plus surprenante : tous les fichiers MP3 ne sont pas acceptés, y compris lorsqu'ils sont parfaitement conformes au standard MPEG Layer III.


À l'époque, plusieurs (https://ffmpeg.org/pipermail/ffmpeg-user/2014-October/023931.html?utm_source=chatgpt.com)[discussions] sur Internet rapportaient que les fichiers produits directement par LAME étaient lus sans difficulté par le système Sensus, contrairement à certains fichiers produits par FFmpeg.
Une discussion de la liste de diffusion FFmpeg datant de 2014 décrit exactement ce comportement sur un Volvo Sensus 3.0, sans toutefois en identifier la cause.
J'avais fini par produire un ensemble de scripts Bash utilisant conjointement **FFmpeg** et **LAME** afin d'obtenir des fichiers compatibles avec le Sensus. 
Ces scripts répartissaient également automatiquement la bibliothèque musicale sur deux partitions de taille équivalente.

Malheureusement, ces scripts étaient uniquement stockés sur un SSD qui est tombé brutalement en panne.
Le travail réalisé a donc été entièrement perdu.

Pendant plusieurs années, cette situation n'a pas réellement posé problème, les 32 Go de musique déjà disponibles étant largement suffisants pour les longs trajets.

---

# Réécriture en Python

Récemment, souhaitant mettre à jour cette bibliothèque musicale avec de nouveaux albums, j'ai décidé de repartir de zéro.

Plutôt que de réécrire les anciens scripts Bash, j'ai choisi de développer un véritable projet Python, plus modulaire et plus facilement maintenable.

Le développement a été réalisé avec l'assistance de **ChatGPT**, principalement pour discuter de l'architecture du projet, comparer différentes bibliothèques Python, explorer le format MP3 et accélérer certaines tâches de développement. 
La conception générale, les expérimentations ainsi que toutes les validations sur le véhicule ont cependant été réalisées manuellement.

Cette réécriture a également été l'occasion de reprendre méthodiquement toutes les expérimentations effectuées plusieurs années auparavant afin de mieux comprendre les contraintes réelles du firmware Volvo Sensus.

---

# Investigations sur le format MP3

L'une des découvertes les plus intéressantes concerne les fichiers produits par **FFmpeg**.

Lorsqu'il encode un MP3 à l'aide de **libmp3lame**, FFmpeg écrit par défaut un en-tête **Xing/LAME** décrivant les caractéristiques de l'encodage. 
Cet en-tête est normalement utilisé pour améliorer le calcul de la durée du morceau et la précision des déplacements ("seek"), notamment en VBR.

En comparant minutieusement les fichiers générés par FFmpeg et par LAME (analyse hexadécimale, `mediainfo`, `mp3guessenc`, etc.), il est apparu que :

* le flux audio MPEG produit par les deux encodeurs est pratiquement identique ;
* la principale différence réside dans la manière dont FFmpeg écrit l'en-tête Xing/LAME.

Le firmware Volvo Sensus refuse systématiquement les fichiers contenant cet en-tête généré par FFmpeg.

En revanche, les mêmes fichiers deviennent immédiatement compatibles lorsqu'ils sont produits avec l'option :

```bash
-write_xing 0
```

Cette option supprime complètement l'en-tête Xing.

Les essais réalisés montrent également que le système Sensus lit correctement des fichiers :

* CBR ;
* ABR ;
* VBR ;

même en l'absence complète d'en-tête Xing, tout en conservant un déplacement précis à l'intérieur des morceaux.

Cette découverte permet de simplifier considérablement le processus d'encodage : il n'est plus nécessaire d'utiliser conjointement FFmpeg et LAME.

---

# Comportements observés du Volvo Sensus

Au cours du développement de ce projet, les comportements suivants ont été observés expérimentalement sur un Volvo V40 équipé du système Sensus.

Les résultats ci-dessous ne constituent pas des spécifications officielles, mais des observations reproductibles réalisées lors des essais.

* seuls les systèmes de fichiers **FAT32** sont reconnus ;
* une table de partitions **MBR** est nécessaire ;
* une organisation en deux partitions d'environ 16 Go fonctionne correctement ;
* les fichiers MP3 produits par FFmpeg avec l'en-tête Xing par défaut sont refusés ;
* les mêmes fichiers sont acceptés lorsqu'ils sont produits avec `-write_xing 0` ;
* les encodages **CBR**, **ABR** et **VBR** sont correctement lus sans en-tête Xing ;
* le déplacement ("seek") fonctionne également correctement sans cet en-tête ;
* l'ordre de lecture des morceaux ne dépend ni du numéro de piste, ni du nom du fichier, ni des tags ID3.

Le dernier point est probablement le plus surprenant.

Les expérimentations montrent que le Sensus semble parcourir les entrées du répertoire FAT dans leur ordre physique de création.
Pour garantir un ordre de lecture cohérent, le logiciel génère donc un plan de synchronisation qui crée les fichiers dans l'ordre souhaité avant d'y recopier leur contenu.

---

# Fonctionnement

Le logiciel suit les étapes suivantes :

```text
Bibliothèque audio
        │
        ▼
Analyse des métadonnées
        │
        ▼
Détermination des conversions nécessaires
        │
        ▼
Répartition équilibrée sur les partitions
        │
        ▼
Transcodage FFmpeg
(-write_xing 0)
        │
        ▼
Réécriture des tags ID3v2.3 (Mutagen)
        │
        ▼
Génération du plan de synchronisation
        │
        ▼
Copie sur la clé USB
```

Les métadonnées sont volontairement supprimées pendant le transcodage (`-map_metadata -1`), puis réécrites avec **Mutagen** au format **ID3v2.3**, afin de produire des fichiers aussi simples et compatibles que possible.

---

# Installation

```bash
git clone ...
cd volvo-sensus-sync

poetry install

poetry run volvo-sensus-sync --help
```

---

# Utilisation

```bash
poetry run volvo-sensus-sync \
    -i /my/library \
    -e /my/export \
    -# 2 \
    -S 15813312512 \
    --abr 112
```

Le réglage **ABR 112 kb/s** constitue un bon compromis entre qualité sonore, taille des fichiers et capacité d'une clé USB de 32 Go.

---

# Préparation de la clé USB

Créer une table de partitions MBR puis formater les partitions en FAT32.

Par exemple :

```bash
sudo fdisk /dev/sdX

sudo mkfs.vfat -n DISK-1 /dev/sdX1
sudo mkfs.vfat -n DISK-2 /dev/sdX2
```

Après avoir réinséré la clé USB et vérifié qu'elle est montée, exécuter les scripts de synchronisation générés :

```bash
bash /my/export/1/sync-partitions.sh -d /media/.../DISK-1

bash /my/export/2/sync-partitions.sh -d /media/.../DISK-2
```

Les scripts de synchronisation sont volontairement séparés de la phase de transcodage.
Cette approche permet de préparer l'export sur une machine puissante (NAS, serveur...) puis d'effectuer ultérieurement la copie sur la clé USB depuis un autre ordinateur, tout en conservant un contrôle précis de l'ordre de création des fichiers.

---

# Technologies utilisées

* Python 3
* Poetry
* FFmpeg
* Mutagen
* Ruff

---

# Remerciements

Ce projet est le résultat d'une longue série d'expérimentations destinées à comprendre le comportement réel du système multimédia Volvo Sensus.

Si vous obtenez des résultats différents sur d'autres véhicules, millésimes ou versions du firmware, les retours d'expérience seront les bienvenus afin d'améliorer la documentation et la compatibilité du projet.

