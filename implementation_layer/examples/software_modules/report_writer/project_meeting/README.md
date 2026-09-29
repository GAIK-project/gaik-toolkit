# Project meeting report

This is the meeting example of the legacy `multi_source_report_generator`, ported to a ReportWriter
`report_spec.json`. The spec does not copy the data. It points with relative paths to
`../../multi_source_report_generator/sample_inputs/` and to that folder's `sample_report.md`.

- The recording and `notes.txt` are the primary sources. The freeze policy PDF, the budget
  spreadsheet and the whiteboard sketch are secondary.
- `roadmap-presentation.pptx` is left out because the SourceNormalizer does not read `.pptx`.
- The section instructions keep the legacy wording. Executive Summary and Next Steps are derived
  sections, written from the drafts of the other sections.
- The legacy config was titled "Q2 Product Planning Meeting Report" (September 10, 2024), but its
  inputs record a Q3 roadmap review on December 15, 2024. The title, the description and one phrase
  of the Executive Summary instructions now match the inputs.
