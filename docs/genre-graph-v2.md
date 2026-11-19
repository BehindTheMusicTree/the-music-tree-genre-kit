# Contrat du graphe sémantique v2

Ce contrat prépare le plan régional multiparent. `GenreGraph` valide un instantané
en mémoire ; `genre_graph.storage` le persiste dans des tables Django séparées,
avec sélections SQL. Les endpoints, la migration des catalogues et les interfaces
restent à adapter. Le contrat
historique `genre_tree` et les arbres personnels continuent d'utiliser leur import
actuel. Aucun producteur ne doit émettre ce nouveau format avant ses consommateurs.

## Identités et relations

`contractVersion: 2`, `curationExportedOn`, `nodes`, `relations` et `boundaries`
sont obligatoires. Une liste de frontières explicitement vide est valide ; une
configuration absente échoue. Les identités sont des QID ou des identités `LOCAL:`
persistantes, indépendantes du libellé et du parent d'affichage.

| Relation enfant → parent | Portée | Transmission |
| --- | --- | --- |
| `classification` | Genre → genre | État des frontières ; population selon les règles ci-dessous |
| `regional_membership` | Nœud régional → overview, genre non canonique ou expression | Toute la population régionale de l'enfant |
| `expression_style` | Expression → style (canonique ou non) | Accès depuis le style à l'expression ; aucun accès inverse |
| `anchoring` | Genre → overview | Descriptive uniquement |

Un overview ne peut appartenir qu'à un autre overview. Aucun genre canonique ne
peut être enfant ou parent d'une appartenance régionale : une population limitée
à une région exige une expression distincte. Une expression a au moins un style
explicite, canonique ou non. Un genre classé (parent de classification) ne peut
être membre régional : seule une racine de classification (genre sans parent de
classification) peut appartenir à une région. Ses descendants régionaux appartiennent à sa population.

Les relations et frontières portent `decisionId`, `source` et `rationale`.
`displayParentId`, lorsqu'il existe, désigne un parent accepté ; il ne choisit
jamais l'état ni la population. Les références inconnues, doublons d'identité ou
de relation, cycles et contradictions échouent avant de rendre un instantané.
Les cycles sont également vérifiés sur les unions de relations transmettrices.

## Frontières et provenance

`evaluate_boundaries(parents, boundaries)` calcule les états depuis les seuls
parents de classification acceptés. Il ne lit aucun statut prérempli. Un genre
sans parent hérite de `before_entry`. Une entrée produit `canonical`, une sortie
depuis cet état produit `after_exit`. Toute autre transition explicite est
invalide. Des entrées indépendantes dans une forêt sont autorisées.

Les parents multiples doivent transmettre le même état avant application de la
frontière locale. `before_entry` et `after_exit` restent différents, même s'ils
sont tous deux non canoniques. Un conflit fournit deux chemins témoins ; aucune
frontière locale ni préférence d'affichage ne le masque.

Chaque résultat conserve l'état, l'état hérité, un prédécesseur témoin et la
décision de frontière pertinente. Les chemins sont reconstruits à la demande.
Le stockage de provenance croît avec les nœuds, pas avec le nombre de chemins.
À l'import, `GenreGraph` recalcule ces résultats et rejette un `canonicalState`
fourni qui les contredit.

## Sélections et normalisation

| Nœud sélectionné / scope inclusif | Ensemble de nœuds attribuables |
| --- | --- |
| Canonique / `canonical` | Genre choisi, descendants de classification canoniques, expressions associées et leur population régionale |
| Canonique / `regional` | Genre choisi, descendants sortis de l'intervalle canonique et leur population régionale, expressions associées et leur population régionale |
| Canonique / `all` | Union distincte des deux scopes |
| Non canonique / `all` | Nœud choisi, descendants de population, expressions de chaque style non canonique retenu et leur population régionale |
| Régional / `all` | Nœud choisi et descendants régionaux, y compris les descendants de classification non canoniques |

Sans descendants, seul le nœud choisi est retenu. Les scopes `canonical` et
`regional` ne sont pas acceptés sur un nœud régional. Un préfixe `before_entry`
ne traverse jamais une entrée canonique pour récupérer la population mondiale
du style ou ses expressions. Une sélection régionale ne remonte jamais une
association de style pour redescendre dans les expressions des autres régions.

`normalize_attributions` retire les ancêtres directs couverts par une attribution
plus précise suivant les chemins d'accès inclusifs admissibles. Les ancrages
ne rendent aucune attribution redondante. La normalisation précède le calcul
des overviews directement attribués qui restent « à préciser ».

Un overview `current` est toujours umbrella. Un overview `historical` l'est
exactement lorsqu'il possède un enfant régional accepté, indépendamment de son
parent d'affichage et du nombre de songs. Le type et sa provenance sont explicites.
Un flag `isUmbrella` fourni contradictoire est rejeté.

La réduction porte uniquement sur les relations `regional_membership`, jamais
sur la classification, les ancrages ou les associations. `ancestry_subgraph`
rend les nœuds partagés et les relations de population régionale, y compris la
classification non canonique ; il n'énumère pas toutes les routes.

Ces fonctions travaillent sur les concepts, pas sur les songs du catalogue.
Les consommateurs doivent appliquer les ensembles obtenus et compter les songs
distincts en SQL ; additionner des buckets par attribution serait incorrect.

## Fixtures et validation

`tests/fixtures/genre_graph/regional-v2.json` est synthétique. Les noms musicaux
ne constituent pas une curation approuvée. Les tests de frontières utilisent
aussi des entrées sans aucun état fourni, dont un graphe de 3 001 nœuds.

`observed-additional-children.json` fige les 44 observations de
`/tmp/regional-staging-validation/leaf-cases.json`, diagnostic du 13 novembre 2026.
SHA-256 : `a3496975abd53eb0fa4752c6288b860f23a22d932976e574934f39a25b8b339b`.
Chaque observation est rejouée avec un autre parent d'affichage et vérifie les
enfants, la sélection et le flag umbrella. Les rôles et types du rejeu sont
des entrées de test ; ils ne valident ni chronologie réelle ni inclusion musicale.
Ce rejeu ne prétend pas couvrir tout le pipeline du diagnostic historique.

Les IDs B/M/R/E des noms de tests renvoient à la matrice
[`genre-graph-fixture-matrix.md`](genre-graph-fixture-matrix.md). Les tests du kit
couvrent le contrat en mémoire, le stockage et ses sélections SQL. Les tests
PostgreSQL utilisent une application minimale et les vraies migrations du kit ;
ils vérifient les créations concurrentes, les conflits de révision et la cohérence
des lectures verrouillées. Ils sont ignorés sous SQLite et exécutés dans un job CI
séparé. La migration du catalogue, les caches des consommateurs, les décisions
géohistoriques et le rejeu de bout en bout restent ouverts chez leurs propriétaires.

## Stockage, concurrence et restauration

`replace_graph(key=..., payload=..., expected_revision=...)` valide le graphe
avant toute écriture. `None` exige une création ; une révision existante exige
le jeton relu par le client. Le remplacement conserve les clés permanentes des concepts, archive le payload et
applique les différences de fermeture dans la même transaction. Chaque concept retiré
exige une décision explicite `{target: identité | null, provenance: {decisionId, source,
rationale}}`. Le concept reste archivé avec `is_active=False` ; sa réactivation
réutilise sa clé. Les attributions sont remappées en SQL vers la cible explicite, ou
retirées pour une cible nulle, en conservant leur historique et toutes les preuves
d'origine, de destination et de retrait. Aucun track n'est supprimé.

Un track porte au plus un nœud par dataset. `GenreGraphAttribution.dataset` est
dénormalisé depuis le nœud et immuable (clé étrangère composite
`(dataset_id, node_id)` sur PostgreSQL, triggers équivalents sur SQLite), et
`UNIQUE(dataset_id, track_id)` s'applique à tout le kit, y compris aux écritures
SQL directes. `replace_track_attributions` et `restore_track_attributions`
rejettent plus d'une identité, `publish_staged_attributions` rejette un ensemble
staged comportant plusieurs nœuds pour un même track. Le remappage d'une
retrait ne peut pas créer de doublon : le track n'avait qu'un nœud, il n'en a
qu'un, avec les preuves d'origine, de destination et de retrait. La migration
0022 échoue en nommant le dataset et le track tant que des doublons existent ;
elle ne choisit jamais un nœud.

`select_tracks(tracks, *, node, scope, include_descendants)` prend le `GenreGraphNode`
déjà chargé (lu dans le même snapshot que l'évaluation du résultat) et n'émet aucune
requête à l'appel ; un nœud inactif ne sélectionne rien, un scope invalide ou un
scope ≠ `all` sur un nœud non canonique lève `GraphValidationError`.
`select_tracks`, `effective_attributions` et `tracks_needing_refinement` utilisent
des sous-requêtes SQL : ils ne matérialisent pas les populations de tracks en
Python. `effective_attributions` renvoie les attributions actives du dataset (il
n'y a plus de normalisation « plus précis » à faire) ; `tracks_needing_refinement`
garde la sémantique umbrella. Le queryset fourni par le consommateur conserve son
périmètre d'accès et ses critères de jouabilité. Les comptes utilisent les tracks
distincts, y compris lorsqu'un nœud possède plusieurs chemins d'accès.

Pour rendre plusieurs résultats avec leurs jetons, évaluer tous les querysets
à l'intérieur de `graph_read_snapshot()`, après l'authentification. Sous PostgreSQL,
ce contexte ouvre une transaction extérieure REPEATABLE READ, READ ONLY ; les
lecteurs peuvent se chevaucher et n'empêchent pas une publication concurrente.
`graph_read_transaction(key=...)` charge aussi le dataset dans cet instantané, sans
`payload` (différé) ; passer `with_payload=True` pour le charger d'emblée, et ne lire un
`payload` différé qu'à l'intérieur du bloc.
Les contextes de lecture imbriqués partagent l'instantané ; entrer depuis une
transaction extérieure non possédée par ce contexte échoue. Matérialiser les résultats
avant de sortir du contexte : un queryset paresseux ne transporte pas l'instantané.

Les consommateurs qui écrivent les attributions en lot ou suppriment des tracks
attribués doivent entrer dans `graph_write_transaction(key=..., expected_revision=...)`
avant de verrouiller ou modifier les tracks et leurs attributions. Pour plusieurs
datasets, acquérir ces contextes par ordre de clé. Le service d'attribution prend
déjà ses verrous dans cet ordre. Les triggers assurent l'invalidation des écritures
ORM/SQL directes, mais ne peuvent pas corriger leur ordre de verrouillage : sans
ce contexte, une écriture concurrente peut être annulée par PostgreSQL pour deadlock.
Le jeton vérifie la version du graphe ; les écritures exigent READ COMMITTED et
sont interdites dans un instantané de lecture. Chaque jeu d'attributions possède
aussi un `expected_assignment_revision` : `None` permet sa première création, puis
le jeton courant est obligatoire, y compris après un effacement explicite. Une
révision périmée échoue avant d'enregistrer les preuves.

`revision` identifie le graphe ; `membership_revision` invalide les populations.
Un remplacement du graphe change les deux. Les triggers d'attribution changent
le second pour les insertions, mises à jour et suppressions, y compris les
écritures en lot et les cascades de suppression des tracks. Sous PostgreSQL,
les tables de transition limitent l'invalidation à une fois par dataset et
instruction SQL. SQLite utilise des triggers par ligne. Un rollback annule les
jetons comme les mutations. L'index de concepts et de fermeture est interne :
le modifier directement par ORM ou SQL n'est pas un contrat d'édition du graphe.
Les changements de relations, frontières et types passent par `replace_graph`.

`replace_track_attributions` exige un track sans propriétaire, des identités
connues, un tableau non vide de preuves par identité, la révision courante du
graphe et le jeton du jeu d'attributions. Chaque preuve contient `decisionId`,
`source` et `rationale`. Son contenu est immuable au sein du dataset : réutiliser
un identifiant avec un autre contenu échoue. Une répétition identique, même avec
les preuves dans un ordre différent, ne réécrit rien. Les états précédents et suivants sont archivés avec
leurs identités sémantiques et leur provenance, sans FK vers les concepts qui
pourraient être retirés. `restore_track_attributions` restaure un instantané
explicite ; il refuse les concepts absents et ne recrée pas de track supprimé.
Les archives et preuves refusent les modifications et suppressions directes.
Les mutations ORM/SQL directes invalident les jetons, mais ne créent pas
l'historique métier complet : les publications doivent utiliser les services. `restore_graph` restaure uniquement le graphe : pour restaurer les deux,
restaurer d'abord les concepts nécessaires, puis les instantanés d'attribution,
dans une transaction englobante. Les consommateurs doivent archiver leurs
mappings de migration et leurs autres projections séparément.

## Compatibilité Python et installation

Le kit Django exige Python 3.14. Le package indépendant
`the-music-tree-genre-graph`, dans `packages/genre-graph`, accepte Python 3.12 et
ne dépend que de `jsonschema`. Les producteurs importent `GenreGraph`,
`GraphValidationError` et `load_genre_graph_schema` depuis
`the_music_tree_genre_graph` ; ils ne copient pas le classificateur du kit Django.
La dépendance du kit est bornée à `>=0.1.0,<0.2.0`. La CI construit le wheel
et le sdist et rejoue les mêmes tests hors du workspace sur Python 3.12 et 3.14,
sans Django. Elle installe aussi le wheel et le sdist du kit avec un wheel pur
explicite sur Python 3.14 et rejoue les tests de stockage SQLite. Ces contrôles
valident les artefacts locaux, pas leur disponibilité sur un index public.

La source uv du workspace ne se transmet pas aux projets consommateurs. Une
installation Git du kit nécessite donc une source publiée explicite pour le package
pur ; la branche de développement ne constitue pas encore une dépendance livrable.
La publication et les changements de pins nécessitent une autorisation de release
séparée. Les pins existants restent inchangés jusque-là.

La migration `0020` refuse une descente si le stockage de preuves ou d'historique
est peuplé : aplatir plusieurs preuves détruirait la provenance. La restauration
applicative du graphe et des attributions reste une opération en avant ; un retour
physique au schéma antérieur exige une sauvegarde de base prise avant migration.
