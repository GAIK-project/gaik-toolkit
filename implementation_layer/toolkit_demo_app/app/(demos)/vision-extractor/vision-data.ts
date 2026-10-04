// What the Vision Extractor demo works with: the file types it accepts, and
// ready-made documents with a matching extraction task.

export const ACCEPTED_EXTENSIONS = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".tiff",
  ".bmp",
];
export const MAX_FILE_MB = 20;

export interface ExampleFile {
  url: string;
  /** Short name for the "view" button of a set with several files. */
  label: string;
}

export interface VisionExample {
  id: string;
  title: string;
  /** The shape of the result, for the card. */
  shape: string;
  summary: string;
  files: ExampleFile[];
  task: string;
  /**
   * The task has a committed schema (api/schemas/vision_extractor_examples/<id>), so only
   * the extraction runs. Without one, the schema is generated at the first run.
   */
  readyMade: boolean;
}

const DIR = "/vision-extractor-example";

export const EXAMPLES: VisionExample[] = [
  {
    id: "application",
    readyMade: true,
    title: "Employment application form",
    shape: "form + 5 lists",
    summary:
      "A two-page form with typed labels, handwriting, ticked boxes and tables: education, jobs, references and a weekly availability grid.",
    files: [{ url: `${DIR}/employment-application.pdf`, label: "Form" }],
    task: `Extract the data of an employment application form (two pages).
Applicant and application: the date of the application, the position applied for, the applicant's full name, phone, email, street address, city, state, ZIP code, desired pay rate per hour (numeric), the date available to start, whether the applicant is eligible to work in the U.S., and whether the applicant was previously employed here. Dates should be MM/DD/YYYY. The two yes/no questions are true or false according to the ticked box.
Return the availability as a list. For each marked cell of the weekly grid, give the day (Mon, Tue, Wed, Thu, Fri, Sat, Sun) and the part of the day (morning, afternoon, evening).
Return the education history as a list. For each row, extract the level, school name, location, years attended, whether the applicant graduated (true or false), and the diploma or degree.
Return the employment history as a list. For each row, extract the employer, position, start date and end date (MM/YYYY, as written), start pay and end pay per hour (numeric), and the reason for leaving.
Return the references as a list. For each, extract the name, relationship, phone number, and the years known (numeric).
Also extract the skills and qualifications text exactly as written, and the answers to the five additional questions (at least 18 years of age, can work weekends and holidays, can lift 25 lbs, reliable transportation, employed under another name) as true or false.
Extract the emergency contact (name, relationship, phone), the name and date of the applicant's signature, and the office-use section (interviewed by, interview date, decision). Leave a value null when the form leaves it blank.`,
  },
  {
    id: "blueprint",
    readyMade: true,
    title: "Construction blueprint",
    shape: "title block + 6 lists",
    summary:
      "A foundation plan drawing. Notes, revisions, dimensions, elevations, the legend and the views are read from the image.",
    files: [{ url: `${DIR}/blueprint.png`, label: "Blueprint" }],
    task: `Extract compliance-relevant information from the construction blueprint.

Top-level fields:
- Project address
- Drawing title
- Drawing number
- Sheet number
- Project number
- Scale
- Drawing date
- Architect
- General contractor
- Surveyor

Repeated records:
1. General construction notes:
   - Note number
   - Note text
   - Compliance category: Dimensions, Structural reference, Utilities/fixtures, Survey/benchmarks, Specifications, Safety/compliance, Other

2. Revision history:
   - Revision number
   - Revision date
   - Revision description

3. Visible dimensions:
   - Dimension value exactly as written
   - Unit
   - Direction or orientation
   - Related element or view

4. Elevation references:
   - Elevation value exactly as written
   - Related element or section

5. Material and legend references:
   - Symbol or pattern name
   - Meaning
   - Location or view

6. Drawing views, grid lines, and callouts:
   - Label
   - Type
   - View title or related drawing element
   - Compliance-relevant information shown

Rules:
- Extract only explicitly visible information.
- Do not infer compliance decisions.
- Preserve original wording, dimensions, dates, and labels.
- Do not guess or infer. If the value of a field is not found, return null.`,
  },
  {
    id: "inspection",
    readyMade: true,
    title: "Site safety inspection",
    shape: "header + checklist + findings",
    summary:
      "A report with a checklist of ticked boxes (OK, not OK, not applicable), corrective actions and summary figures.",
    files: [{ url: `${DIR}/site-safety-inspection.pdf`, label: "Report" }],
    task: `Extract the data of a site safety inspection report.
Report details: the report number, report type, form number and revision, company, site, project number, inspection date, start time, end time, inspector, site manager, main contractor, construction phase, number of workers on site, number of subcontractors, areas covered, weather, and the previous report number.
Summary: the number of items checked, the number OK, the number not OK, the safety index in percent (numeric), the overall result, and the date of the next inspection. The overall result must be approved, approved_with_remarks, or work_stopped, according to the box that is ticked.
Return the checklist as a list. For each item, extract the section heading it is under, the item text, the result (ok, not_ok, or not_applicable, according to the ticked box), and the remark. The remark can be null.
Return the findings and corrective actions as a list. For each, extract the number, the finding, the severity (low, medium, or high), the person or party responsible, the due date, and the status.
Also extract the signature dates of the inspector and of the site manager.
Only fill values that are shown. Return null when a value is missing.`,
  },
  {
    id: "receipt",
    readyMade: true,
    title: "Shop receipt (Finnish)",
    shape: "header + items",
    summary:
      "A small, tilted photo of a Finnish receipt, with weighed goods, a discount line and a deposit.",
    files: [{ url: `${DIR}/receipt.jpg`, label: "Receipt" }],
    task: `Extract the most important data of a Finnish shop receipt. Keep product names as they are printed.
Receipt details: the store name, store address, date, time, receipt number (Kuitti), till number (Kassa), payment method (for example the card type), and the total amount (Yhteensä) with its currency.
Return the purchased items as a list. For each line, extract the product name, the quantity, the unit price, and the line amount.
The quantity is the number of pieces (for example 2 KPL) or the weight in kg that is printed in the small line under the product name. When there is no such line, the quantity is 1: never take the package size in the name (500G, 1L, 4RL) as the quantity.
The unit price is the price after the x in that small line (for example 1,89 EUR/kg), and null when there is no such line.
The line amount is the price at the right of the line. A discount line (such as ETU JUUSTOT) is an item with a negative line amount. Include the deposit line (PANTTI) as an item.
Amounts and quantities should be numeric: read a decimal comma as a decimal point.`,
  },
];

export const fileNameOf = (url: string): string =>
  url.split("/").pop() ?? "document";
