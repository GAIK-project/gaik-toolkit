# Expected behaviours: synthetic house condition assessment

These are the checks from `use_cases/report_writing.md` for this dataset. Each item names the planted
situation, the expected behaviour, and how to check it in a ReportWriter workspace
(`normalized/`, `knowledge/`, `report/`). Run the commands from the workspace folder.

Two helpers used below:

```sh
# Print one section of the report; the title prefix is enough.
section() { sed -n "/^## $1/,/^## /p" report/report.md; }
# Print the conflicts of one knowledge file.
conflicts() { uv run python -c "import json,sys; [print(c['status'], '|', c['topic'], '|', c['description']) for c in json.load(open(sys.argv[1], encoding='utf-8'))['conflicts']]" "$1"; }
```

Recording quotes in `knowledge/` come from the transcript, which may differ slightly from the
script after the speech round trip, so grep for key words rather than whole sentences.

## Source hierarchy (P4)

### C1: main distribution board, known only from a document
- **Planted:** `renovation_report_1998.pdf`, page 3, section 6: "The main distribution board was
  replaced in 1998." `rec3_building_services.mp3` describes the board but gives no year.
- **Expected:** the Electrical systems section attributes the year to the document ("According to
  the 1998 renovation report, the main distribution board was replaced in 1998") and cites it. The
  year is not narrated as an observation.
- **Check:**
  - `grep -n -A2 '"file": "renovation_report_1998.pdf"' knowledge/electrical.json` shows a unit on
    the board with `"locator": "page 3"` and `"source_class": "secondary"`.
  - `section "Electrical systems" | grep -i "according to the 1998 renovation report"`

### C2: supply-air unit, known only from recording 3
- **Planted:** `rec3_building_services.mp3` (script `recording_scripts/rec3_building_services.txt`,
  Ventilation paragraph): "The machine produced a steady hum but also an unusual vibration; surface
  rust was visible on the housing."
- **Expected:** narrated as an observation ("It was observed that ...") with a field-observation
  citation, e.g. `[field observation, 14 March 2026]`.
- **Check:**
  - `grep -n -i -A5 '"quote": ".*vibration' knowledge/building_services.json` shows a unit citing
    `rec3_building_services.mp3` with `"source_class": "primary"`.
  - `section "Building services" | grep -i "it was observed that.*vibration"`
  - `section "Building services" | grep -i "field observation"`

### C3: moisture, the observation contradicts the 2019 survey
- **Planted:**
  - `moisture_survey_2019.docx`, Readings table, first data row: "Bathroom floor, next to the
    shower floor drain | 34 | Normal"; Conclusion: "No elevated readings were found in the wet
    rooms."
  - `rec2_interior_wet_rooms.mp3`: "Next to the shower floor drain the readings are elevated,
    between 115 and 125 ... The highest reading is 125."
- **Expected:** the Wet rooms section follows the observation: elevated readings next to the shower
  floor drain, stated as observed. It mentions that the 2019 survey found no elevated readings.
  `knowledge/wet_rooms.json` records the conflict as `resolved`.
- **Check:**
  - `conflicts knowledge/wet_rooms.json` shows a `resolved` moisture conflict.
  - `section "Wet rooms" | grep -iE "125|elevated"`
  - `section "Wet rooms" | grep -i "2019"`

### C4: attic underlay, an uncertain observation contradicts a document
- **Planted:**
  - `rec1_exterior_attic.mp3`: "Honestly, I'm not sure whether this underlay is the original one.
    ... I can't tell from here."
  - `roof_renovation_2012.pdf`, page 1: "The old underlay was removed and a new roof underlay was
    installed over the whole roof."
- **Expected:** "Unresolved: ..." in the Structures and roof section, giving both views, and an
  `unresolved` entry in the `conflicts` of `knowledge/structures.json`.
- **Check:**
  - `conflicts knowledge/structures.json` shows an `unresolved` underlay conflict.
  - `section "Structures and roof" | grep -i "unresolved"`

### C5: roof covering, two documents disagree
- **Planted:**
  - `renovation_report_1998.pdf`, page 1: "The original concrete tile roof was in fair condition
    and was not part of the 1998 renovation."
  - `roof_renovation_2012.pdf`, page 1: "The new roof covering is profiled steel sheet, 0.5 mm,
    coated, dark grey."
- **Expected:** the report follows the newer document: the roof covering is steel sheet. Concrete
  tiles appear, if at all, only as the covering that was replaced in 2012.
- **Check:**
  - `section "Structures and roof" | grep -i "steel sheet"`
  - `grep -n -i "concrete tile" report/report.md` shows only past or replaced wording.
  - `conflicts knowledge/structures.json` shows the covering conflict as `resolved`, if the curator
    lists it.

## Explicit missing data and scope (P7)

### G1: no electrical inspection record
- **Planted:** no source contains an electrical inspection record. `rec3_building_services.mp3`:
  "There's no electrical inspection record available."
- **Expected:** `(missing: latest electrical inspection record)` in the Electrical systems section.
- **Check:**
  - `grep -n "latest electrical inspection record" knowledge/electrical.json` shows it under
    `"missing"`.
  - `grep -nF "(missing: latest electrical inspection record)" report/report.md`

### G2: sewer flushing is not a camera inspection
- **Planted:**
  - `maintenance_log.xlsx`, sheet `Log`, row 6: "2016-04-22 | Sewer flushing: main sewer line
    flushed from the basement cleanout to the street by a drain cleaning company".
  - `rec3_building_services.mp3`: "No sewer camera inspection was done as part of this visit".
- **Expected:** `(missing: latest sewer camera inspection)`. The 2016 flushing may be mentioned,
  but only as flushing, never as an inspection.
- **Check:**
  - `grep -n "latest sewer camera inspection" knowledge/building_services.json` shows it under
    `"missing"`.
  - `grep -nF "(missing: latest sewer camera inspection)" report/report.md`
  - `grep -n -i "flush" report/report.md`: read each hit; none may call the flushing an
    inspection.

### S1: roof surface not inspected because of snow
- **Planted:** `rec1_exterior_attic.mp3`: "I couldn't inspect the roof surface today. There's a
  thick layer of snow on it, and I'm not going up on a snowy roof."
- **Expected:** a stated scope limit with its reason, e.g. "The roof surface was not inspected
  because of snow cover." It is neither a missing marker nor an observation of the roof surface's
  condition.
- **Check:**
  - `section "Structures and roof" | grep -i "snow"`
  - `grep -nF "(missing: roof" report/report.md` returns nothing.

## Knowledge filtering (P2)

### D1: garden entries in the maintenance log
- **Planted:** `maintenance_log.xlsx`, sheet `Log`, rows 2, 4, 7, 8, 11, 13 and 15: hedge trimming,
  lawn care, an apple tree, flower beds and a lawn mower.
- **Expected:** absent from every knowledge file and every section.
- **Check:** `grep -n -i -E "hedge|lawn|apple|flower|mow" knowledge/*.json report/report.md`
  returns nothing.

### D2: cost table in the 1998 renovation report
- **Planted:** `renovation_report_1998.pdf`, page 4, section 7: a cost table in FIM, total 103 100.
- **Expected:** absent from the report.
- **Check:** `grep -n -E "FIM|markka|103 100|42 800|36 500|14 200|9 600" report/report.md` returns
  nothing. The knowledge files should not hold the costs either.

## Source grounding (P1)

### L1: the sample report describes a different house
- **Planted:** `sample_report.docx` (8 Specimen Street, Modelby) describes an oil boiler and a
  3,000-litre underground oil tank. It also contains facts that must not leak: inspector Alex
  Sample, a 2019 electrical inspection record, a 2021 sewer camera inspection, a 1983 bathroom and
  a bitumen felt roof. This house has district heating and no oil heating.
- **Expected:** none of these appear in the output.
- **Check:** `grep -n -i -E "\boil\b|boiler|oil tank|Specimen|Modelby|Alex Sample|bitumen|1983" knowledge/*.json report/report.md`
  returns nothing. A plain `grep oil` also matches "toilet" and "soil".

### T1: every quote is verbatim
- **Planted:** nothing; this holds for every unit.
- **Expected:** every quote in `knowledge/` appears verbatim, whitespace aside, in the normalized
  source it cites.
- **Check:** this prints `[]`:

  ```sh
  uv run python -c "from gaik.software_components.knowledge_curator.models import KnowledgeBase; from gaik.software_components.source_normalizer.models import NormalizedSources; print(KnowledgeBase.load('knowledge').verify_quotes(NormalizedSources.load('normalized')))"
  ```

## Persistence, role separation and derived sections

### E1: edit knowledge, rerun Stage 3 only (P3, P6)
- **Planted:** after a full run, delete the unit whose quote contains "unusual vibration" from
  `knowledge/building_services.json`, and drop its id from any `unit_ids` in `conflicts`. Then run
  only `synthesize()`.
- **Expected:** the vibration and rust disappear from the Building services section and from the
  derived sections. `normalized/` and the other knowledge files are not rewritten.
- **Check:**
  - `grep -n -i "vibration" report/report.md` returns nothing.
  - `ls -l --time-style=full-iso normalized knowledge` shows the times from the first run, except
    for the edited file.

### R1: the reviewer corrects a planted wrong year (P5)
- **Planted:** a Building services draft that says the ventilation was installed in 2008 instead of
  1998 is given to the reviewer.
- **Expected:** the reviewer replaces 2008 with 1998 and logs the edit in `review_log.json`.
- **Check:**
  - `grep -n "2008" report/review_log.json` shows the edit, with 1998 in its replacement.
  - `section "Building services" | grep -c "2008"` prints 0.

### O1: derived sections use drafts only (P2)
- **Planted:** nothing; Summary and Recommendations depend on other sections.
- **Expected:** both are written from the accepted drafts only, never from `normalized/` or
  `knowledge/`.
- **Check:**
  - Every year, reading and citation in the Summary and Recommendations also appears in a technical
    section.
  - Compare `section "Summary" | grep -oE "[0-9]{4}" | sort -u` and the same for
    `"Recommendations"` with the years in the four technical sections.
  - Log-only details, such as the filter-change dates, must not appear in them unless a technical
    section carries them.

### B1: single-call baseline
- **Planted:** the same spec is run with `mode="single_call"` into a separate workspace.
- **Expected:** C1–L1 are scored for both modes and compared.
- **Check:** run the checks C1–L1 against each workspace's `report/report.md`, record pass or fail
  per check and mode, and compare the totals. The single-call run has no `knowledge/`, so its checks
  use the report only.

## Reference quotes

Documents, verbatim in the text layer:

| Check | File and place | Quote |
|-------|----------------|-------|
| Building services | `renovation_report_1998.pdf`, page 3 | Mechanical ventilation system installed during 1998 renovation. Design life 25 years. |
| C1 | `renovation_report_1998.pdf`, page 3 | The main distribution board was replaced in 1998. |
| C5 | `renovation_report_1998.pdf`, page 1 | The original concrete tile roof was in fair condition and was not part of the 1998 renovation. |
| Wet rooms | `renovation_report_1998.pdf`, page 2 | The bathroom floor and walls and the sauna floor were waterproofed in 1998 with a brush-applied waterproofing membrane, ... |
| Background | `renovation_report_1998.pdf`, page 1 | The property is a 1½-storey timber-frame detached house built in 1978. |
| C4 | `roof_renovation_2012.pdf`, page 1 | The old underlay was removed and a new roof underlay was installed over the whole roof. |
| C5 | `roof_renovation_2012.pdf`, page 1 | The new roof covering is profiled steel sheet, 0.5 mm, coated, dark grey. |
| C3 | `moisture_survey_2019.docx`, Conclusion | No elevated readings were found in the wet rooms. |
| G2 | `maintenance_log.xlsx`, `Log`, row 6 | Sewer flushing: main sewer line flushed from the basement cleanout to the street by a drain cleaning company |
| Background | `floor_plan.png` | Living area, ground and upper floor: 130.0 m2 |

Recordings, verbatim in the scripts (the transcripts may differ slightly):

| Check | Recording | Quote |
|-------|-----------|-------|
| S1 | `rec1_exterior_attic.mp3` | I couldn't inspect the roof surface today. There's a thick layer of snow on it, and I'm not going up on a snowy roof. |
| C5 | `rec1_exterior_attic.mp3` | From the ground, what I can see at the eaves and the gable ends looks like a profiled steel sheet roof, dark grey. |
| C4 | `rec1_exterior_attic.mp3` | Honestly, I'm not sure whether this underlay is the original one. |
| C3 | `rec2_interior_wet_rooms.mp3` | Next to the shower floor drain the readings are elevated, between 115 and 125, over an area of roughly 40 by 40 centimetres. |
| C2 | `rec3_building_services.mp3` | The machine produced a steady hum but also an unusual vibration; surface rust was visible on the housing. |
| G2 | `rec3_building_services.mp3` | No sewer camera inspection was done as part of this visit, so I can't say anything about the condition of the sewer pipes under the house. |
| G1 | `rec3_building_services.mp3` | There's no electrical inspection record available. |
| Heating | `rec3_building_services.mp3` | The house is on district heating. |
