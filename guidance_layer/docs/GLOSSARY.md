# GAIK Toolkit Glossary

An alphabetized reference of terms and concepts used in the GAIK Toolkit.

---

## A

**Agent Skills**: No-code assets that define specific capabilities or behaviors for AI agents, used in no-code implementations of generic use cases.

**AIOps**: AI-powered operations for monitoring, evaluation, and continuous improvement of deployed GenAI solutions. Also referred to as LLMOps in the context of large language models.

**Audit Logging**: A security and compliance mechanism that records system activities, user actions, and data access for accountability and regulatory compliance.

**Authentication**: Security mechanisms (auth) that verify user identity before granting access to system resources, part of the security and compliance framework.

## B

**Business Layer**: One of the six layers in GAIK's architecture, containing business process modeling, workflows, GenAI product canvas, workflow templates, and work systems definitions for each generic use case.

## C

**Code-based Assets**: Implementation resources including software components, software modules, solution configurations, and deployment packages that require programming knowledge.

**Code-based Deployment Packages**: Complete deployment bundles for each generic use case, including Docker files, configuration files, and deployment manifests for containerized environments.

**Code-based Implementation**: Implementation approach using programming, software components, and software modules rather than no-code tools or prompts.

**Configuration Wizard**: An interactive tool that guides users through selecting knowledge processes, generic use cases, and configuring solutions. Also called Solution Configuration Wizard.

**Connector Framework**: A standardized system for integrating GAIK solutions with internal and external data sources such as ERPs, drives, databases, and APIs.

## D

**Demo Apps**: Interactive applications deployed in environments like Rahti that showcase GAIK capabilities, allowing users to "try and see" how solutions work. Also called Demos.

**Deployment Package**: A complete bundle of code, configuration, and deployment manifests (including Docker files) required to deploy a solution for a specific generic use case.

**Docker File**: A configuration file that defines how to build a containerized version of a GAIK solution for deployment in cloud or on-premises environments.

## E

**Evaluation Methods**: Techniques and scripts for assessing solution performance for each generic use case, including metrics, test cases, and LLM-as-judge approaches.

**Extended BPMN**: An extension of Business Process Model and Notation adapted for modeling GenAI workflows, combining visual and textual representation.

## G

**GAIK**: Generative AI-Enhanced Knowledge Management. A research project (2025-2027) led by Haaga-Helia University and co-funded by ERDF, and the Python toolkit that implements its capabilities.

**GAIK GenAI Toolkit**: The complete Python toolkit that implements GAIK's layer-based architecture, providing reusable components, modules, and frameworks for building GenAI solutions.

**GenAI Maturity Assessment**: A tool or model for evaluating an organization's readiness and capabilities for adopting and scaling generative AI solutions.

**GenAI Product Canvas**: A structured framework (available in PPTX and XML formats) for defining and planning GenAI products, with specific canvases created for each generic use case.

**GenAI Success Framework**: A framework or canvas for ensuring successful implementation and adoption of GenAI solutions in organizations.

**Generic Use Case**: A reusable, template-based solution pattern applicable across multiple organizations or scenarios, such as "invoice processing" or "incident reporting." Each has associated workflows, product canvases, test cases, and implementation assets.

**Guidance Layer**: One of the six layers in GAIK's architecture, containing documentation, best practices, development guides, process guides, configuration wizard, glossary, and the project website.

## I

**Implementation Layer**: One of the six layers in GAIK's architecture, containing executable code (software components and modules), examples, tests, deployment packages, demos, connectors, evaluation methods, and AIOps monitoring.

## K

**Knowledge Capture**: One of the three core knowledge processes in GAIK, focusing on precise and accurate retrieval of information from various data sources through techniques like RAG (Retrieval-Augmented Generation).

**Knowledge Extraction**: One of the three core knowledge processes in GAIK, focusing on extracting structured information from unstructured content such as documents, PDFs, and audio transcripts.

**Knowledge Generation**: One of the three core knowledge processes in GAIK, focusing on using structured representations and AI models to produce summaries, reports, insights, and tailored outputs.

**Knowledge Processes**: The three fundamental processes that GAIK addresses—Knowledge Extraction, Knowledge Capture, and Knowledge Generation—each with associated software modules and value evaluation models.

**Knowledge Service**: A logical capability or service that implements one or more knowledge processes, such as speech-to-text, document parsing, or information extraction.

## L

**Layer-Based Architecture**: GAIK's comprehensive six-layer framework spanning from strategic guidance (Guidance Layer, Strategy Layer, Requirements Layer) through business design (Business Layer) to implementation (Implementation Layer) and governance (Security Compliance Layer).

## M

**Metrics**: Quantitative measures used in evaluation methods to assess the performance, accuracy, efficiency, or other qualities of GenAI solutions.

## N

**No-Code Assets**: Implementation resources such as prompts, agent skills, and instructions that enable solution deployment without programming, available for each generic use case.

**No-Code Implementation**: An implementation approach that uses prompts, agent configurations, and pre-built tools rather than custom code, making solutions accessible to non-developers.

## P

**Prompts**: Carefully crafted instructions or templates used in no-code implementations to guide GenAI models in performing specific tasks without custom coding.

## R

**Rahti**: CSC's Finnish container cloud platform (specifically CSC Rahti 2) used for deploying GAIK demonstration apps and production solutions in OpenShift-compatible environments.

**Requirements Layer**: One of the six layers in GAIK's architecture, containing requirements templates, test cases/evals, ground truth data, and input-output pairs for each generic use case.

**Roles**: Part of the security and compliance framework, defining user permissions and access levels to system functionality and data based on organizational responsibilities.

## S

**Security Compliance Layer**: One of the six layers in GAIK's architecture, containing security policies, privacy frameworks, compliance guidelines, authentication, roles, secrets management, and audit logging.

**Software Components**: Low-level, atomic, reusable utilities that perform specific tasks with fine-grained control. Examples include schema generators, parsers, transcribers, and RAG components. Located in `gaik.software_components.*`.

**Software Modules**: High-level, end-to-end pipelines that orchestrate multiple software components into complete workflows for knowledge processes. Examples include AudioToStructuredData, DocumentsToStructuredData, and RAGWorkflow. Located in `gaik.software_modules.*`.

**Solution Configuration Wizard**: An interactive tool in the guidance layer that helps users configure GenAI solutions by selecting knowledge processes, use cases, and implementation options. Also called Configuration Wizard.

**Solution Configs**: Configuration files and settings that define how software modules and components are assembled and parameterized for each specific generic use case.

**Specific Use Case**: A customized implementation of a generic use case tailored to a particular organization's requirements, data, and processes.

**Strategy Layer**: One of the six layers in GAIK's architecture, containing strategic planning documents, lists of knowledge processes and services, value evaluation frameworks and models, use case identification frameworks, maturity assessments, and success frameworks.

## T

**Test Cases**: Input-output pairs and evaluation scenarios in the requirements layer used to validate that generic use cases produce expected results, often including ground truth data.

## V

**Value Evaluation Framework**: A structured approach in the strategy layer for assessing the business value and ROI of implementing GenAI solutions, with specific models for each knowledge process and generic use case.

**Value Evaluation Model**: A specific model within the value evaluation framework for quantifying the expected value, costs, and benefits of implementing a particular knowledge process or generic use case.

## W

**Work System Templates**: Structured templates in the business layer that define the complete work system context for each generic use case, including people, processes, technology, and information flows.

**Workflow Modeling Language**: A notation system (BPMN) used in the business layer to visually and textually represent GenAI workflows, making them understandable to both business and technical stakeholders.

**Workflow Template**: A reusable workflow pattern in the business layer that defines the process flow, decision points, and activities for implementing a generic use case, available in both visual and textual formats.

---

## Acronyms

- **AIOps**: Artificial Intelligence for IT Operations
- **API**: Application Programming Interface
- **Auth**: Authentication
- **BPMN**: Business Process Model and Notation
- **CRM**: Customer Relationship Management
- **CSC**: Finnish IT Center for Science (manages Rahti platform)
- **ERDF**: European Regional Development Fund
- **ERP**: Enterprise Resource Planning
- **GAIK**: Generative AI-Enhanced Knowledge Management
- **GenAI**: Generative Artificial Intelligence
- **LLM**: Large Language Model
- **LLMOps**: Large Language Model Operations
- **OCR**: Optical Character Recognition
- **RAG**: Retrieval-Augmented Generation
- **ROI**: Return on Investment
- **SSE**: Server-Sent Events

---

## Related Resources

- **GAIK Website**: [gaik.ai](https://gaik.ai)
- **GitHub Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **PyPI Package**: [pypi.org/project/gaik](https://pypi.org/project/gaik/)
- **Documentation**: [https://gaik-project.github.io/gaik-toolkit/](https://gaik-project.github.io/gaik-toolkit/)

---

*Last Updated: January 2026*
