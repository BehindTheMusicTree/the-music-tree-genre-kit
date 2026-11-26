# Graph v2 witness matrix

This matrix is synthetic. The musical names (Reggae, Dub, Breton rock…) are not an approved curation: they serve as graph shapes. The C/X/M/R/E IDs are referenced by test names in the kit and in consumers (pipelines, grow, infrastructure, app-kit, genre-tree-view, frontend). See `docs/genre-graph-v2.md` §Fixtures and validation.

Reconstructed on 2026-11-19 from the working logs of November 13–14, 2026; the source plan was never committed.

Contract 4 mapping: `expression_style` edges became `classification` edges from a regional genre, the `expression` kind became `genre`, and the scopes `canonical`/`regional`/`all` became `restricted`/`expressions`/`extended`.

Contract 5 mapping: `regional_membership` became `classification` to an overview, `canonicalRoots` became `globalRoots` and the `canonical` genre state became `global`. Rows below use `global` for the state and otherwise keep their original wording; backticked scope names are the historical ones.

| ID | Fixture | Attendu |
| --- | --- | --- |
| C01 | Genre outside every listed root, with and without a region | Regional genre reaching no overview rejected; listing it as a root makes it global |
| C02 | Listed root, classification descendants, expressions, overviews | Descendants global; regional genres `regional`; other kinds no state; order, labels and display parents change nothing |
| C03 | Genre with one global and one regional classification parent | Rejected with one witness edge per parent |
| C04 | Unknown, duplicate, non-genre or classified global root; removed `boundaries`, `canonicalState`, `isUnacceptedRoot` | Fail explicitly with the offending identity |
| C05 | Missing `globalRoots` versus explicit empty list; classification cycle | Missing fails; empty is valid and has no global genre; cycle fails with its path |
| M01 | Global Dub plus Jamaican, French and British dub expressions, with disjoint song fixtures | Global inclusive access reaches all three; each regional selection reaches only its justified population |
| M02 | "Dub" displayed under Jamaica and "Dub" in the global tree | Equal labels do not collapse scopes; Jamaican view never becomes worldwide Dub |
| M03 | Dub song with no known region | Global access retained; no automatic Jamaica, France or Britain attribution |
| M04 | Roots reggae global with Jamaican anchoring; Jamaican and French roots song fixtures | Both songs accessible from global Roots reggae; only justified Jamaican song in Jamaica, French song in France |
| M05 | Jamaican reggae subgenre below a listed root, then a regional genre with a Jamaican anchoring | Global by inheritance in the first case; no country-based override in the second |
| M06 | French reggae as an expression of global Reggae, with regional descendants | Selected by France and by Reggae `regional`/`all`, never by Reggae `canonical`; no detected French language or name |
| M07 | Parameterized Reggae, Rock, Funk, Disco, Pop and Hip-hop fixtures with English, French, other-language and instrumental songs | Holding curated genre assignment fixed, language alone changes neither global status nor regional attribution; test each named family separately |
| M08 | French-language rock with unknown region; independently evidenced Breton rock | Language alone does not imply France or Brittany; evidenced Breton rock may belong to Brittany and France through accepted paths |
| M09 | Jazz fixtures varying US/non-US performer/location and a descriptive "American style" label | Holding curated classification fixed, these metadata changes alone do not create global entry/exit or a US regional assignment |
| M10 | Classical fixtures varying European/non-European instruments and performer nationality | Holding the classified tradition fixed, neither instrument inventory nor nationality changes global status |
| M11 | Western classical, Indian classical and its Hindustani/Carnatic tradition fixtures | Distinct concepts remain distinct; no forced placement in Western classical based on the shared word "classical" or instruments; statuses follow the listed global roots, not a newly asserted taxonomy |
| M12 | Electronic music as a listed root with descendants | Same inheritance rules as other families; no special exemption |
| M13 | Hip-hop fixtures with US, UK and other origins and English/non-English lyrics | No US/UK or English-only global whitelist; regional evidence remains separate |
| M14 | Locally concentrated global style; widely distributed non-global expression | Popularity/geographic reach alone does not change curated status |
| M15 | French dub as regional grouping without an autonomous-subgenre assertion | Regional scoped access works without manufacturing a new stylistic claim |
| M16 | Roots concept anchored in Jamaica, plus a distinct Jamaican roots expression | Anchoring does not duplicate the global concept; narrower expression has distinct scope; no global-song leakage or double counts |
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
| R15 | Global association or origin offered as shortcut during regional reduction | Not a valid regional-membership witness; no cross-region leakage |
| R16 | Cycle through an additional parent | Reject with explicit cycle path, not arbitrary QID ordering |
| R17 | Goryeo / Later Silla / Korea structural fixture | Additional child counted despite another display parent; real Goryeo membership remains unapproved without evidence |
| R18 | Sasanian Empire, Gascony, Socialist Republic of Bosnia and Herzegovina, Later Silla fixtures | Each named witness exercises generated multiparentality and identity reuse; structural tests do not assert historical musical validity |
| R19 | All 44 previously misclassified overview witnesses | Complete-graph child detection; guard and JSON Schema agree; freeze reviewed fixtures from available diagnostic evidence |
| R20 | Overview with children and zero songs | Child-derived umbrella status independent of song count |
| R21 | Explicit membership addition/prohibition and conflicting exceptions | Apply audited precedence; contradiction is visible and rejected, not silently resolved |
| E01 | Wikidata classification → Gold export → genre-kit/API import → selection/counts → shared UI | Boundary states, expression scope, identities and exact song sets remain consistent |
| E02 | Missing reference, invalid scope or conflicting supplied state | Atomic rejection; existing dataset remains usable |
| E03 | Repeated import, remapped identity, retry and rollback | No duplicates/orphans; unchanged identities preserved; data restored on rollback |
| E04 | Root list or membership change after cached queries | Affected selections, counts, provenance and refinement refreshed; no stale regional access |
| E05 | Input permutation or display-parent change | Membership, state, exact selections and counts invariant |
| E06 | Regional breadcrumbs and sectors on wide/narrow screens | Parallel clickable paths, shared portions, progressive disclosure; sectors not proportional to counts |
| E07 | Global/regional/all selections and personal-tree consumers | Existing scope meanings explicitly mapped and tested; regional anchoring does not double-count global songs |
| E08 | Baseline global replay versus curated root migration | Unaffected behavior preserved; intentional classification differences listed and reviewed |
| E09 | Songs without genre or playable video | Retained end to end; regional uncertainty never deletes a song |
| E10 | Large shared-ancestry graph and full-catalog operations | Bounded graph/provenance processing; no enumeration of every path or Python set per song population |
| E11 | Expression of a regional style (French bluegrass → Bluegrass → Country) | Selected with the style and its classification ancestors; never by the style's region (USA) |
| E12 | Expression of a global style (French reggae fusion → Reggae fusion) | Selected via style `all`, global Reggae `regional`/`all` and its region; not in `canonical` |
| E13 | Regional root genre (Country, member of the USA) and its classified descendant | Country selected by the USA and by its expressions; a classified genre cannot be a regional member |
| X01 | Country and USA selections | USA selects Country and Bluegrass; Country also selects French country and French bluegrass; USA never selects the French expressions |
| X02 | Normalization of `{USA, French country}` and `{USA, Country, Bluegrass}` | The first keeps both; the second keeps Bluegrass |
| X03 | Expression of Country located in a region nested under the USA (Texas country) | Rejected: it shares every region with its regional style |
| X04 | Expression of a regional style with no overview | Rejected: regional node reaches no overview |
