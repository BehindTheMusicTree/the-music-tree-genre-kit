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
| `expression_style` | Expression → style canonique | Accès depuis le style à l'expression ; aucun accès inverse |
| `anchoring` | Genre → overview | Descriptive uniquement |

Un overview ne peut appartenir qu'à un autre overview. Aucun genre canonique ne
peut être enfant ou parent d'une appartenance régionale : une population limitée
à une région exige une expression distincte. Une expression a au moins un style
canonique explicite. Ses descendants régionaux appartiennent à sa population.

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

Les IDs B/M/R/E des noms de tests renvoient au plan multiparent. Les tests du kit
couvrent le contrat en mémoire, le stockage et ses sélections SQL. Les tests
PostgreSQL utilisent une application minimale et les vraies migrations du kit ;
ils vérifient les créations concurrentes, les conflits de révision et la cohérence
des lectures verrouillées. Ils sont ignorés sous SQLite et exécutés dans un job CI
séparé. La migration du catalogue, les caches des consommateurs, les décisions
géohistoriques et le rejeu de bout en bout restent ouverts chez leurs propriétaires.

## Stockage, concurrence et restauration

`replace_graph(key=..., payload=..., expected_revision=...)` valide le graphe
avant toute écriture. `None` exige une création ; une révision existante exige
le jeton relu par le client. Le remplacement conserve les clés des concepts
inchangés, archive le payload et reconstruit l'index de sélection dans la même
transaction. Supprimer un concept encore attribué échoue ; aucune attribution
ni aucun track n'est supprimé pour rendre l'import possible.

`select_tracks`, `effective_attributions` et `tracks_needing_refinement` utilisent
des sous-requêtes SQL : ils ne matérialisent pas les populations de tracks en
Python. Le queryset fourni par le consommateur conserve son périmètre d'accès
et ses critères de jouabilité. Les comptes utilisent les tracks distincts,
y compris lorsqu'une attribution possède plusieurs chemins.

Pour rendre plusieurs résultats avec leurs jetons, évaluer tous les querysets
à l'intérieur de `graph_read_transaction(key=...)`. Ce contexte verrouille le
dataset, comme les écrivains, et évite de mélanger deux états sous PostgreSQL
READ COMMITTED. Garder ce verrou court ; les lecteurs utilisant ce contexte
se sérialisent entre eux et avec les imports.

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
connues, une provenance complète et la révision courante du graphe. Une répétition
identique ne réécrit rien. Les états précédents et suivants sont archivés avec
leurs identités sémantiques et leur provenance, sans FK vers les concepts qui
pourraient être retirés. `restore_track_attributions` restaure un instantané
explicite ; il refuse les concepts absents et ne recrée pas de track supprimé.
Ces archives couvrent les écritures par ce service, pas les écritures ORM/SQL
directes. `restore_graph` restaure uniquement le graphe : pour restaurer les deux,
restaurer d'abord les concepts nécessaires, puis les instantanés d'attribution,
dans une transaction englobante. Les consommateurs doivent archiver leurs
mappings de migration et leurs autres projections séparément.

## Compatibilité Python

Le kit exige Python 3.14 ; les pipelines acceptent Python 3.12. Le module
`genre_graph/boundaries.py` ne dépend ni de Django ni de `jsonschema` et reste
compatible avec Python 3.12. La préparation pipelines en conserve une copie
identique, une fixture commune et leurs empreintes. Aucune dépendance livrée
ne pointe vers un checkout local. Une future synchronisation de ces copies doit
mettre à jour les empreintes et rejouer les deux suites ; elle ne remplace pas
la préparation des consommateurs ni les prérequis de publication des packages.
