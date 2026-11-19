# Matrice des témoins du graphe v2

Cette matrice est synthétique. Les noms musicaux (Reggae, Dub, Breton rock…) ne constituent pas une curation approuvée : ils servent de formes de graphe. Les IDs B/M/R/E sont référencés par les noms de tests du kit et des consommateurs (pipelines, grow, infrastructure, app-kit, genre-tree-view, frontend). Voir `docs/genre-graph-v2.md` §Fixtures et validation.

Reconstituée le 2026-11-19 depuis les journaux de travail du 13–14 novembre 2026 ; le plan source n'a jamais été commité.

| ID | Fixture | Attendu |
| --- | --- | --- |
| B01 | Root and descendants with no entry | All `before_entry`; no automatic canonical root |
| B02 | Reggae entry → unmarked Roots reggae → unmarked descendant | Entry applies at Reggae; all three canonical without descendant flags |
| B03 | Reggae entry → French reggae exit → several descendants | Exit node and entire descendant branch `after_exit`; canonical sibling unchanged |
| B04 | European art music → Classical music entry → Breton classical music exit → descendant | Exact states before/canonical/after/after; entry below root works; labels remain illustrative |
| B05 | Attempt entry at a child or deeper descendant of Breton classical music | Reject with entry/exit witness path; no partial update |
| B06 | Unmarked descendants before entry versus after exit | Same non-canonical boolean, different states; entry accepted only before |
| B07 | Exit before entry, repeated entry, repeated exit, both markers on one node | Reject contradictory/redundant input with boundary IDs |
| B08 | Add, move or remove an entry/exit or a classification parent | Recompute affected descendants/provenance; reject newly illegal transitions; invalidate caches and matching; unrelated branches unchanged |
| B09 | Change labels, input order or display parent | Status and canonical interval unchanged |
| B10 | Add/remove regional anchoring, overview parent, origin or expression association | No change to canonical inheritance |
| B11 | Several classification parents with compatible states | Deterministic state independent of parent order; no path enumeration explosion |
| B12 | Canonical/non-canonical conflict, before/after conflict, or attempted entry reachable after an exit | Under proposed graph policy: reject with witness paths; no display-parent tie-break or canonical override |
| B13 | Missing boundary configuration, unknown boundary ID, cyclic classification | Fail explicitly; never substitute an empty list or discard a bad relation silently |
| B14 | Valid empty boundary list and a path with no exit after entry | Empty list yields before-entry nodes; entered path stays canonical without invented exit |
| M01 | Canonical Dub plus Jamaican, French and British dub expressions, with disjoint song fixtures | Canonical inclusive access reaches all three; each regional selection reaches only its justified population |
| M02 | "Dub" displayed under Jamaica and "Dub" in the canonical tree | Equal labels do not collapse scopes; Jamaican view never becomes worldwide Dub |
| M03 | Dub song with no known region | Canonical access retained; no automatic Jamaica, France or Britain attribution |
| M04 | Roots reggae canonical with Jamaican anchoring; Jamaican and French roots song fixtures | Both songs accessible from canonical Roots reggae; only justified Jamaican song in Jamaica, French song in France |
| M05 | Jamaican reggae subgenre below a canonical parent, then the same fixture with an explicit exit | Inherit canonical in the first case; non-canonical in the second despite Jamaican origin; no country-based override |
| M06 | French reggae exit branch | Non-canonical because of the supplied boundary, not detected French language or name; descendants cannot re-enter |
| M07 | Parameterized Reggae, Rock, Funk, Disco, Pop and Hip-hop fixtures with English, French, other-language and instrumental songs | Holding curated genre assignment fixed, language alone changes neither canonical status nor regional attribution; test each named family separately |
| M08 | French-language rock with unknown region; independently evidenced Breton rock | Language alone does not imply France or Brittany; evidenced Breton rock may belong to Brittany and France through accepted paths |
| M09 | Jazz fixtures varying US/non-US performer/location and a descriptive "American style" label | Holding curated classification fixed, these metadata changes alone do not create canonical entry/exit or a US regional assignment |
| M10 | Classical fixtures varying European/non-European instruments and performer nationality | Holding the classified tradition fixed, neither instrument inventory nor nationality changes boundary status |
| M11 | Western classical, Indian classical and its Hindustani/Carnatic tradition fixtures | Distinct concepts remain distinct; no forced placement in Western classical based on the shared word "classical" or instruments; statuses follow supplied boundaries, not a newly asserted taxonomy |
| M12 | Electronic music with canonical descendants and one explicitly exited branch | Same inheritance rules as other families; no special "more free" exemption or re-entry |
| M13 | Hip-hop fixtures with US, UK and other origins and English/non-English lyrics | No US/UK or English-only canonical whitelist; regional evidence remains separate |
| M14 | Locally concentrated canonical style; widely distributed non-canonical expression | Popularity/geographic reach alone does not change curated status |
| M15 | French dub as regional grouping without an autonomous-subgenre assertion | Regional scoped access works without manufacturing a new stylistic claim |
| M16 | Roots concept anchored in Jamaica, plus a distinct Jamaican roots expression | Anchoring does not duplicate the canonical concept; narrower expression has distinct scope; no global-song leakage or double counts |
| R01 | Current overview with no children, with/without a direct song | Valid export, always umbrella; direct song flagged when present |
| R02 | Historical overview with no children, including Ancient Rome fixture | Non-umbrella; matching/direct attribution allowed without automatic refinement flag |
| R03 | Historical overview with one child, parameterized over all four child types and main/additional parent | Umbrella regardless of display nesting; same result for existing/generated overviews |
| R04 | Add first/remove last historical child | Recalculate umbrella status, direct-song flags and caches |
| R05 | Brittany contains Breton traditional music and Breton rock | Both accessible; overview not restricted to traditional culture |
| R06 | Song → Breton rock and Brittany; Breton rock → Brittany → France | Remove redundant direct song/genre links only with preserved paths; same access, no Brittany refinement flag |
| R07 | R06 plus independent non-redundant umbrella attribution | Independent refinement flag remains |
| R08 | Kingdom of France → France | Historical songs accessible from France; modern French songs do not flow down into Kingdom of France |
| R09 | Succession, conquest, geographic overlap or similar display geometry alone | No automatically accepted membership; missing periods are unknown, not timeless |
| R10 | Tradition spans two historical contexts without context-wide inclusion | Both memberships allowed with evidence; no inferred parent relation between contexts |
| R11 | Unknown candidate versus previously justified membership | Candidate transmits no songs; justified relation retained absent proven redundancy |
| R12 | Parentless regional root and several independent regional roots | Nodes and songs exported; no fabricated parent |
| R13 | Cross-border tradition or expression with incomparable parents | One identity, all justified paths accessible; intersection alone insufficient |
| R14 | Diamond graph and equal-extent parents | Distinct counts at common ancestor; shared breadcrumb segments; never drop both parents or merge identities by extent |
| R15 | Canonical association or origin offered as shortcut during regional reduction | Not a valid regional-membership witness; no cross-region leakage |
| R16 | Cycle through an additional parent | Reject with explicit cycle path, not arbitrary QID ordering |
| R17 | Goryeo / Later Silla / Korea structural fixture | Additional child counted despite another display parent; real Goryeo membership remains unapproved without evidence |
| R18 | Sasanian Empire, Gascony, Socialist Republic of Bosnia and Herzegovina, Later Silla fixtures | Each named witness exercises generated multiparentality and identity reuse; structural tests do not assert historical musical validity |
| R19 | All 44 previously misclassified overview witnesses | Complete-graph child detection; guard and JSON Schema agree; freeze reviewed fixtures from available diagnostic evidence |
| R20 | Overview with children and zero songs | Child-derived umbrella status independent of song count |
| R21 | Explicit membership addition/prohibition and conflicting exceptions | Apply audited precedence; contradiction is visible and rejected, not silently resolved |
| E01 | Wikidata classification → Gold export → genre-kit/API import → selection/counts → shared UI | Boundary states, expression scope, identities and exact song sets remain consistent |
| E02 | Missing reference, invalid scope or conflicting supplied state | Atomic rejection; existing dataset remains usable |
| E03 | Repeated import, remapped identity, retry and rollback | No duplicates/orphans; unchanged identities preserved; data restored on rollback |
| E04 | Boundary or membership change after cached queries | Affected selections, counts, provenance and refinement refreshed; no stale regional access |
| E05 | Input permutation or display-parent change | Membership, state, exact selections and counts invariant |
| E06 | Regional breadcrumbs and sectors on wide/narrow screens | Parallel clickable paths, shared portions, progressive disclosure; sectors not proportional to counts |
| E07 | Canonical/regional/all selections and personal-tree consumers | Existing scope meanings explicitly mapped and tested; regional anchoring does not double-count canonical songs |
| E08 | Baseline canonical replay versus curated boundary migration | Unaffected behavior preserved; intentional classification differences listed and reviewed |
| E09 | Songs without genre or playable video | Retained end to end; regional uncertainty never deletes a song |
| E10 | Large shared-ancestry graph and full-catalog operations | Bounded graph/provenance processing; no enumeration of every path or Python set per song population |
