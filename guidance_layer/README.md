---
title: Guidance Layer
description: Guides and automates GenAI solution development
---

The guidance layer provides process guidance and supporting tools that help organizations navigate the journey from identifying a GenAI opportunity to deploying a working solution. Rather than requiring teams to figure out everything from scratch, this layer offers structured pathways, decision support, and automation to make the development process more efficient and less error-prone.

---

## GenAI Solution Implementation Process

At the core of the guidance layer is a **GenAI solution implementation process and guide** that walks teams through the key steps: from strategic planning and requirements capture, through design and development, to deployment and evaluation.

This process integrates activities across all other layers of the toolkit, ensuring that technical implementation is grounded in business needs, supported by clear requirements, and aligned with security and compliance expectations.

GenAI implementation activities are structured along two lenses: 1. Solution lens (or use case lens), 2. Organization lens

![GenAI solution implementation process](https://github.com/GAIK-project/gaik-toolkit/blob/main/images/GenAI_solution_implementation_process.jpg)
**Fig. 1** The end-to-end GenAI solution implementation process, including phases, key activities, and decision points.

---

## Overview

From the solution (use case) lens the process consists of **three phases** that guide an organization from initial exploration to value creation with GenAI. It starts from the organization’s strategic goals and concrete problems or challenges, and progresses through **demos**, a **proof-of-concept (PoC)**, and finally a **Minimum Viable Product (MVP)**.
Progress between phases is governed by **decision points** (shown as purple diamonds in Fig. 1), ensuring that further investment is made only when sufficient value and feasibility are demonstrated.

## Phase 1 – Explore via Demos

**Purpose:** Rapid learning and shared understanding.

**Key activities:**
- Explore demo GenAI use cases  
- Explore demo designs  
- Run demos  
- Learn about opportunities and potential solution value  

**Outcome:**
A shared understanding of what GenAI can do, which use cases are relevant, and whether there is enough potential value to proceed.

**Decision Point D1:**
At the first decision point, stakeholders decide whether to:
- Proceed to a Proof-of-Concept (PoC)
- Refine the problem or use case
- Stop the initiative

## Phase 2 – Test via Proof-of-Concept (PoC)

**Purpose:** Validate feasibility and value in a realistic organizational context.

**Key activities**
- Customize the GenAI use case  
- Customize the PoC design  
- Build and deploy the PoC  
- Evaluate, monitor, and analyze PoC results  

**Outcome**
Evidence regarding:
- Technical feasibility  
- Quality and reliability of outputs  
- Business relevance and early value  

**Decision Point D2**
At the second decision point, stakeholders decide whether to:
- Proceed to an MVP
- Rework or extend the PoC
- Stop the initiative due to limited value or high risk

## Phase 3 – Create Value via Minimum Viable Product (MVP)

**Purpose:** Transform validated ideas into tangible business value.

**Key activities**
- Refine the GenAI use case based on PoC learnings  
- Design the MVP and the surrounding work system (processes, roles, governance)  
- Build and implement the MVP  
- Evaluate, monitor, and analyze MVP performance  

**Outcome**
A working GenAI solution embedded in real operations and delivering measurable value.

**Decision Point D3**
At the final decision point, stakeholders decide whether to:
- Scale the solution further
- Integrate it into core systems and operations
- Iterate on the MVP or discontinue the solution

## Summary

This process is:
- **Iterative and decision-driven**, rather than purely linear  
- Designed to **progressively reduce uncertainty**  
- Structured to ensure that investment increases only when learning, feasibility, and value are demonstrated  

The decision points act as safeguards, helping organizations move from experimentation to sustainable value creation with GenAI.

## Organization Lens: GenAI Implementation at Scale

In addition to developing individual GenAI solutions, organizations must address GenAI implementation from an **organization-wide lens**. This lens focuses on alignment, coordination, and value creation across multiple initiatives.

**Identify and Select AI Use Cases:** Organizations identify and prioritize GenAI use cases in line with strategic goals and business priorities, forming a coherent portfolio of initiatives.

**Plan and Coordinate AI Projects:** GenAI initiatives are planned and coordinated across teams to ensure alignment, efficient use of resources, and consistency across projects.

**Assess and Build Organizational AI Readiness:** Organizations assess and strengthen their readiness for GenAI adoption, covering technology, data, skills, governance, and ways of working.

**Measure and Manage Business Value:** Business value from GenAI is measured and managed at an organizational level to guide investment decisions and ensure alignment with strategic objectives.

## Relationship Between Solution Lens and Organization Lens

- The **solution lens** focuses on developing and validating individual GenAI solutions.  
- The **organization lens** ensures coherence, scalability, and value across all GenAI initiatives.  

Together, both lenses enable structured and sustainable GenAI adoption.

---

## How to Start with the Toolkit

The GAIK toolkit serves different user needs depending on your role and objectives. Choose your starting point:

### Starting from the Technical Side

**For developers and technical teams implementing GenAI solutions:**

1. **Explore the [Implementation Layer](/toolkit/software-components)** - Review available software components and modules
2. **Try the [Toolkit Demo](/demo)** - Test individual components and complete pipelines interactively
3. **Review [Use Cases](/use-cases/incident-reporting)** - See technical implementation examples for real-world scenarios
4. **Check usage examples** - Visit [software component examples](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components) and [software module examples](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_modules) for code samples
5. **Install the Python package** - Get started with code-based implementation using `pip install gaik`
6. **Check the [GitHub repository](https://github.com/GAIK-project/gaik-toolkit)** - Access source code, examples, and technical documentation

**Recommended path:** Demo → Software Components → Usage Examples → Implementation

### Starting from the Strategic Side

**For decision-makers evaluating GenAI adoption and use case selection:**

1. **Review the [Strategy Layer](/strategy-layer)** - Understand use case selection frameworks and value evaluation approaches
2. **Explore [Use Cases](/use-cases/incident-reporting)** - See how GenAI addresses real business challenges across different sectors
3. **Assess organizational readiness** - Contact our team for AI implementation capability assessment tool (AICapDev)
4. **Evaluate expected value** - Apply the value evaluation framework to potential use cases 
5. **Review the [Roadmap](/docs#gaiks-roadmap)** - Understand the project's development phases and planned capabilities

**Recommended path:** Strategy Layer → Use Cases → Value Evaluation → Use Case Selection

### Starting from the Business Side

**For business analysts and process owners designing GenAI solutions:**

1. **Explore the [Business Layer](/business-layer)** - Learn how to define use cases and design workflows
2. **Review [Use Cases](/use-cases/incident-reporting)** - See complete business context, workflows, and expected outcomes
3. **Try [No-Code Assets](/toolkit/no-code-assets)** - Deploy solutions using prompt templates and agent skills without coding
4. **Define your use case** - Use the GenAI Product Canvas to structure your solution
5. **Test with the [Demo](/demo)** - Validate concepts with real toolkit capabilities

**Recommended path:** Business Layer → Use Cases → No-Code Assets → Demo

### Starting with Testing & Exploration

**For anyone wanting to try the toolkit hands-on:**

1. **Visit the [Live Demo](https://gaik-demo.2.rahtiapp.fi/)** - Access is available upon registration request
2. **Test software modules** - Try Audio-to-Structured-Data, Document-to-Structured-Data, and RAG-Workflow
3. **Experiment with components** - Test individual capabilities like Transcriber, Extractor, Parser, and Classifier
4. **Try real-world demos** - Test incident reporting and construction diary use cases
5. **Explore [Use Cases](/use-cases/incident-reporting)** - See detailed documentation for what you tested

**Recommended path:** Demo → Software Modules → Use Cases → Implementation Layer

---

## GAIK's Roadmap

The GAIK project follows a phased development approach throughout 2026, progressing from initial toolkit development to real-world application:

![GAIK Project Roadmap](/images/roadmap.png)

The project evolves through four major versions (V1-V4), transitioning from **Development** phase (Q1-Q3) to **Application** phase (Q4). Core toolkit components are established in early versions with a minimum scope of 2 generic use cases, expanding to 10 generic use cases by V3. The final quarter focuses on mature toolkit deployment, additional components, and AI-powered development assistance. Continuous feedback loops throughout the year ensure the toolkit remains aligned with real-world needs.

---

## GAIK Consortium

The GAIK project is implemented by a consortium of **four companies and five academic partners** with expertise in business digitalization, knowledge management, data science, generative AI, and natural language processing.

### Project Partners

**Academic Partners:**
- **Haaga-Helia University of Applied Sciences (coordinator)**
- **University of Helsinki**
- **Tampere University of Applied Sciences**

**Industry Partners:**
- **Luvata** - Manufacturing sector
- **Lotus Demolition** - Construction sector
- **QAdental** - Healthcare and well-being sector
- **Azets** - Business digitalization and consulting

The consortium combines cutting-edge research with real-world business needs from manufacturing, healthcare and well-being, and construction sectors. The toolkit targets identified use cases tailored to contemporary business requirements, as reflected by the needs analysis of the partner companies.

The project continues to extend cooperation with additional companies and international partners.

---

## GAIK Support for Companies

Beyond providing the open-source toolkit, the GAIK team offers direct support to help companies successfully adopt and customize GenAI solutions for their specific use cases. We provide two tailored support tracks depending on where you need the most help:

![GAIK Company Support Model](/images/offer.png)

### Strategy-Level Support

**Best for:** Companies exploring GenAI opportunities and needing guidance on use case selection and value assessment.

**What we provide:**
- **Workshop 1: GenAI Use Case Selection & Specification** - Starting from the strategy layer, we help you identify, evaluate, and specify the most promising GenAI use cases for your organization
- **Joint Meeting** - Collaborative session to align on approach and requirements
- **Proof-of-Concept Development** - Your team develops the PoC with continuous support from the GAIK team for evaluation and improvement
- **Workshop 2: Solution Integration & Implementation Planning** - Guidance on integrating the GenAI solution into your operations and scaling to production

### Implementation-Level Support

**Best for:** Companies with identified use cases who need technical guidance on toolkit implementation.

**What we provide:**
- **Workshop 1: Toolkit Guidance** - Starting from the business and implementation layers, we guide you through selecting and configuring toolkit components for your use case
- **Joint Meeting** - Technical alignment and hands-on guidance
- **Proof-of-Concept Development** - Your team implements with GAIK team support for evaluation and improvement
- **Workshop 2: On-Demand Support** - Flexible follow-up assistance tailored to your specific needs

---

### Get Started with GAIK Support

<Callout type="info">
**We want to help you succeed with GenAI!**

If your organization has a GenAI-related use case that aligns with the GAIK toolkit capabilities (knowledge capture, access, or synthesis), we invite you to request GAIK assistance.

Our team will work with you to customize the toolkit for your specific requirements and guide you through successful implementation.
</Callout>

**Request GAIK Assistance**

![GAIK Assistance Request Form QR Code](/images/qr.png)

Scan the QR code to access our assistance request form.

---

## Accessing the Toolkit (Project Resources)

The GAIK toolkit is accessible through multiple channels to serve different user needs:

![GAIK Access Points](/images/access.png)

The central **GitHub repository** serves as the source of truth for both documentation and code. From there, the toolkit is distributed through:
- **Project Website** - Project's website with announcements, news, and updates ([gaik.ai](https://gaik.ai))
- **GitHub Website** - This documentation site you're viewing now, providing comprehensive guides and references ([gaik-project.github.io](https://gaik-project.github.io))
- **Online Demo Applications** - Live, interactive demonstrations of toolkit capabilities ([gaik-demo.2.rahtiapp.fi](https://gaik-demo.2.rahtiapp.fi))
- **Python Repository (PyPI)** - Installable `gaik` packages available through Python repositories for code-based implementations ([pypi.org/project/gaik](https://pypi.org/project/gaik/))

This multi-channel approach ensures that both technical and non-technical users can access the resources most relevant to their needs.

---

## Glossary

The guidance layer provides a **glossary** that defines key concepts, terminology, and architectural patterns used throughout the GAIK toolkit.

This shared vocabulary ensures that teams—whether technical or non-technical—can communicate clearly about GenAI solutions and understand how different components and layers fit together.

---

## Documentation & Contribution

The guidance layer includes **documentation and contribution guidelines** that help developers and practitioners contribute to the toolkit, extend its capabilities, and adapt it to new use cases.

By making the toolkit's design principles and extension points explicit, the guidance layer supports a growing ecosystem of reusable GenAI building blocks and best practices.

---

## Key Components

- **Implementation Process Guide** - Step-by-step guidance for GenAI solution development
- **Configuration Wizard** - Interactive tool for selecting and configuring building blocks (under development)
- **Glossary** - Shared terminology and concept definitions
- **Documentation** - Comprehensive guides for software components, modules, and workflows
- **Contribution Guidelines** - Standards and processes for extending the toolkit
