# Sample data for the agent skills

Synthetic sample inputs and example outputs for the Claude Desktop skills in
[`../agent-skills/skills/`](../agent-skills/skills). They are kept outside the plugin so that
installing the plugin does not download audio, PDFs or Office files. Plugin directories
hold such files for manual review.

| Folder | For skill | Contents |
|---|---|---|
| `construction-diary-creation/` | `construction-diary-creation` | Finnish and English site-diary recordings (`.mp3`) |
| `incident-report-writing/` | `incident-report-writing` | An incident report and a safety observation recording (`.m4a`) |
| `purchase-order-processing/sample_data/` | `purchase-order-processing` | A purchase order, three BOMs, a price list and a sample sales order, laid out as the skill expects (`customer_data/`, `price_list/`, `sample_sales_order/`) |
| `purchase-order-processing/example_output/` | `purchase-order-processing` | The sales order and calculation breakdown the skill produced from `sample_data/` |

Download a folder, then give the skill its local path, as each skill's README shows.
