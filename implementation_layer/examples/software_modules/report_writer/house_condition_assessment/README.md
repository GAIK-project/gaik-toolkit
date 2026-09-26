# Synthetic house condition assessment

A fictional test case for the ReportWriter, taken from `use_cases/report_writing.md`: a condition
assessment of 12 Example Road, Sampleton, a 1½-storey timber-frame house built in 1978. It
consists of three site recordings and five customer documents. Planted situations test the source
hierarchy, the missing-data markers, knowledge filtering and grounding. The people, companies,
addresses and figures are all invented.

| File | Role |
|------|------|
| `inputs/rec1_exterior_attic.mp3` | Primary: exterior, roof seen from the ground, attic |
| `inputs/rec2_interior_wet_rooms.mp3` | Primary: interior and wet rooms, with moisture readings |
| `inputs/rec3_building_services.mp3` | Primary: heating, ventilation, water and sewer, electrical |
| `inputs/renovation_report_1998.pdf` | Secondary: 4 pages; ventilation and distribution board on page 3, costs on page 4 |
| `inputs/roof_renovation_2012.pdf` | Secondary: new underlay and steel sheet roof |
| `inputs/moisture_survey_2019.docx` | Secondary: no elevated readings in 2019 |
| `inputs/maintenance_log.xlsx` | Secondary: filter changes, sewer flushing and garden entries |
| `inputs/floor_plan.png` | Secondary: room areas, 130.0 m2 living area |
| `sample_report.docx` | Style example for a different house; its facts must never leak |
| `recording_scripts/*.txt` | Texts of the recordings, also usable as reference transcripts for WER |
| `report_spec.json` | Sections, required items, instructions and sources for the ReportWriter |
| `expected_behaviours.md` | The checks C1–B1: what is planted where, and how to verify the output |

## Regenerating the data

Every document is written by `generate_dataset.py`. The PDFs and the PNG are byte-identical on
each run; the DOCX and XLSX files differ only in their zip timestamps.

The documents alone, with no API call:

```sh
uv run python implementation_layer/examples/software_modules/report_writer/house_condition_assessment/generate_dataset.py --documents-only
```

The recordings are synthesized from `recording_scripts/` with the TextToSpeech component, which is
a paid API call. Leave out `--documents-only` to write the documents and then the three mp3 files:

```sh
uv run python implementation_layer/examples/software_modules/report_writer/house_condition_assessment/generate_dataset.py
```

It uses Azure by default and needs `TTS_ENDPOINT`, `AZURE_API_KEY` and `AZURE_ENDPOINT`. With
`--openai` it uses OpenAI and needs `OPENAI_API_KEY`. The variables are read from the environment
or from the nearest `.env` file above the script, such as `implementation_layer/.env`. A missing
credential stops the script with an error.

The synthesized recordings run about two minutes each. A transcript has no time stamps, so a fact
unit that quotes a recording has the locator `null`.
