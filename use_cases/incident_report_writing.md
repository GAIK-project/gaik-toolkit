# Incident reporting use case

Incident reporting (cross-cutting use case)

The incident reporting use case illustrates how the toolkit connects use case design, value evaluation, and implementation into a single GenAI-enabled solution for safety and incident management.

**Business layer – use case specification**

At the business layer, the use case is specified using the GenAI product canvas. The focus is on improving how incidents, near misses, safety observations, and safety-related initiatives are reported in operational environments. The canvas clarifies the purpose of the solution (supporting incident reporting as part of daily work), the main users (employees and supervisors), and the expected outcomes.

Concrete example fragments reflected in the use case design include:
- Reporting is based on spoken descriptions of incidents and safety observations
- The goal is to produce complete, standardized incident reports
- The solution supports reporting directly from operational contexts (e.g. on-site, during work)
- Success is defined in terms of faster reporting, higher reporting quality, and better downstream usability of incident data

The canvas provides a shared understanding of what the GenAI solution does and why it is valuable, without digging into technical implementation details.

```mermaid
flowchart TB

subgraph C1["Context & Need"]
  A1["Name\nIncident reporting assistant"]
  A2["Knowledge processes\nKnowledge capture + Knowledge synthesis"]
  A3["Business need\nIncidents such as broken equipment, water leaks, or spills occasionally occur on company premises and must be reported quickly so they can be resolved. Currently, employees must go to a computer and complete a web form in system X, which slows down the incident-reporting process."]
end

subgraph C2["Solution & Users"]
  B1["Task\nIncident reporting"]
  B2["User/-s\nEveryone in the company"]
  B3["Solution\nThe new AI-driven solution will enable employees to report incidents quickly through voice input on their mobile phones from different locations (including outdoors). The process will involve recording verbal descriptions of incidents, capturing images of hazards, and converting this information into a structured incident report that can be saved directly to the system X."]
end

subgraph C3["Inputs"]
  D1["Input\n1. Voice input (verbal description of an incident)\n2. Images (photos), maybe with annotations\n3. Template/-s for incident reports (list/-s of questions)\n4. Reference data (list of equipment, list of facilities, list of incident types and severity levels)"]
end

subgraph C4["Outputs & Value"]
  E1["Output\nIncident report (filled in template)"]
  E2["Expected benefits / value\n1. Faster response time\n2. Increased accuracy and consistency\n3. Improved safety\n4. Better compliance and documentation"]
end

C1 --> C2
C2 --> C3
C3 --> C4
```


- **Reference GenAI Product Description for Incident Reporting** - [Download Raw File (GenAI_product_canvas_Incident reporting_v0.1.pptx)](https://github.com/GAIK-project/gaik-toolkit/blob/main/business_layer/genAI_product_canvas/GenAI_product_canvas_Incident%20reporting_v0.1.pptx)

**Strategy layer – value evaluation and monitoring**

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


