Extract the following fields from the provided content.

If a field cannot be determined, apply this policy: state unavailable and omit the claim rather than speculate

1. executive_summary (string, REQUIRED): Summarize overall Q2 supplier performance, identify the main concern, and state the management decision. Use only supplied evidence and cite source filenames inline.
2. kpi_overview (string, REQUIRED): Create a Markdown table for Nordic Components, Baltic Fasteners, Alpine Sensors, and Overall. Show total deliveries, on-time delivery percentage, total units, defective units percentage, and spend in EUR. Calculate from the KPI workbook and round percentages to one decimal place.
3. supplier_findings (string, REQUIRED): Give a separate evidence-grounded finding for each supplier, combining the KPI workbook with relevant audit, incident, and meeting evidence.
4. risks (string, REQUIRED): Describe supported quality and delivery risks. Explicitly identify the approximate EUR 410,000 meeting-note figure versus the exact workbook spend instead of silently choosing the approximate number.
5. actions (string, REQUIRED): Create a table with Action, Owner, Due Date, and Completion Condition. Include only actions explicitly stated in the evidence.
6. source_references (string, REQUIRED): List every source file used in the report. Use exact filenames.