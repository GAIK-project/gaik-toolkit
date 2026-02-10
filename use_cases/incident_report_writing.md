# Incident reporting generic use case (cross-cutting use case)

The incident reporting use case illustrates how the toolkit connects use case design, value evaluation, and implementation into a single GenAI-enabled solution for safety and incident management.


## Business layer – use case specification

At the business layer, the use case is specified using the GenAI product canvas. The focus is on improving how incidents, near misses, safety observations, and safety-related initiatives are reported in operational environments. The canvas clarifies the purpose of the solution (supporting incident reporting as part of daily work), the main users (employees and supervisors), and the expected outcomes.

Concrete example fragments reflected in the use case design include:
- Reporting is based on spoken descriptions of incidents and safety observations
- The goal is to produce complete, standardized incident reports
- The solution supports reporting directly from operational contexts (e.g. on-site, during work)
- Success is defined in terms of faster reporting, higher reporting quality, and better downstream usability of incident data

The canvas provides a shared understanding of what the GenAI solution does and why it is valuable, without digging into technical implementation details.

![GenAI Product Description for Incident Reporting](https://github.com/GAIK-project/gaik-toolkit/blob/main/images/genai_product_canvas_incident_reporting.png)

- **Reference GenAI Product Description for Incident Reporting** - [Download Raw File (GenAI_product_canvas_Incident reporting_v0.1.pptx)](https://github.com/GAIK-project/gaik-toolkit/blob/main/business_layer/genAI_product_canvas/GenAI_product_canvas_Incident%20reporting_v0.1.pptx)



## Strategy layer – value evaluation and monitoring**

At the strategy layer, the value evaluation model for incident reporting applies the [Value Evaluation Framework](https://github.com/GAIK-project/gaik-toolkit/blob/main/strategy_layer/value_evaluation_framework/README.md) 
to this generic use case and makes value assumptions explicit.

Example value fragments from the model include:

Functional value (primary):
“Faster reporting”, “Less effort”, “Complete, standardized reports”, “Accessible on-site”
→ Outcome: More incidents reported, faster fixes

Informational value:
“Better incident data”, “Improved insights”, “Stronger analytics”
→ Outcome: Smarter prevention decisions

Emotional value:
“Higher confidence”, “Increased trust”, “Less reporting friction”
→ Outcome: Employees feel safer and heard

The same model can be used both before implementation (to evaluate expected value) and after deployment (to monitor realized value across different dimensions).

![Value evaluation model: Incident reporting](https://github.com/GAIK-project/gaik-toolkit/blob/main/images/Value_evaluation_Incident%20reporting.jpg)

The source version of the **Value evaluation model: Incident reporting** - [Download Raw File (Value_evaluation_model_for Incident_reporting_v0.1.pptx)](https://github.com/GAIK-project/gaik-toolkit/blob/main/strategy_layer/value_evaluation_framework/Value_evaluation_model_for%20Incident_reporting_v0.1.pptx) 
“Lower admin effort”, “Accident cost avoidance”, “Productivity gains”

## Implementation layer using No-Code**

Incident reporting can be supported by Generative AI using no-code approach.

The no-code layer shows how a GenAI solution can be used in everyday work without building software. Business users work with ready-made templates and rules that define what information should be captured and how the result should look.

What the business user sets up (once)

A safety manager defines a reporting template, not code. Conceptually, it says:
- “These are the fields our incident report must contain”
- “These are the only allowed options for key fields”
- “Do not guess or invent missing information”
- “If something is not said, leave it empty”

This logic is captured in a prompt template, which acts like a digital reporting policy.

What happens in daily work

**Step 1 – Reporting by voice**
An employee or supervisor records a short voice message describing:
an incident
a safety observation
or a safety-related initiative

No form, no typing, no computer required.

**Step 2 – Automatic structuring (no-code logic)**
The prompt template converts the spoken description into a standardized incident report, following strict business rules.
For example, the assistant is instructed to:
extract only information explicitly mentioned
classify the report using fixed categories (e.g. Safety observation, Near miss: Yes/No)
keep descriptions short and factual
ensure dates, locations, and causes follow a consistent format

From a business perspective, this is equivalent to enforcing rules like:
“If the speaker does not mention a date, leave the date field empty.”
“If the cause does not match our predefined categories, do not fill it in.”
“Never add explanations or extra text.”

Example of what the business gets out

Instead of free text, the output is a ready-to-use structured report, aligned with the company’s reporting form:

- Type of form: Safety observation
- Event date and time: 15.03.2024 14:30
- Location: Building A, Assembly line
- Near miss: Yes
- Direct cause: 5S
- Corrective actions performed: Yes

Anything not mentioned in the voice report is intentionally left blank.

This makes the result:
- easy to paste into an existing system
- safe to store in a database
- reliable for analytics and reporting
- suitable for audits and compliance
