# GAIK – Generative AI Knowledge Management Toolkit

[![PyPI version](https://img.shields.io/pypi/v/gaik.svg)](https://pypi.org/project/gaik/)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)

This is a generative AI toolkit of the GAIK project ([gaik.ai](https://gaik.ai)). It provides a complete set of components and guidance for building knowledge-centric GenAI solutions, from strategic directions to deployable implementations.

# Project Documentation

Project documentation is available at:

https://gaik-project.github.io/gaik-toolkit/

# Why the toolkit is needed

**Generative AI has significant potential to increase the productivity of knowledge work** 
- Example experiments: consultants using AI were significantly more productive – they completed 12.2% more tasks on average, and completed tasks 25.1% more quickly (Dell'Acqua, 2023) 
- Example cases from practice: Customer-support agents at a large firm selling business-process software demonstrated a 15% increase in productivity when assisted by generative AI (Brynjolfsson, 2025).

**However, tangible business value from Generative AI implementation projects is still limited**
- “only 26% of companies have advanced beyond the proof-of-concept stage to generate value” Source: BCG’s report (de Bellefonds et al, 2024). 
- “Despite $30–40 billion in enterprise investment into GenAI, 95% of organizations are getting zero return.” Source: MIT report (Challapally et al, 2025).

Adopting Generative AI and creating value from **it is especially challenging for small and medium-sized enterprises (SMEs)**, which lack the technical expertise and capabilities to implement GenAI solutions effectively. The literature review of Oldemeyer et al. (2024) identified the following three most frequent challenges for SMEs in the AI implementation in the industrial sector: knowledge, costs, and the low maturity level in digitalization.

# Overall approach
Companies can deal with GenAI challenges by combining reusable building blocks with clear guidelines.
Instead of designing solutions from scratch, teams assemble existing components and follow proven ways of working. 
This makes it easier to turn ideas into real results, while reducing implementation time, risk, and required resources, and improving overall solution quality.

# Toolkit Focus
The knowledge management perspective for structuring GenAI development and implementation activities.

The toolkit focuses on three core **knowledge processes** in organizations:
| Knowledge process | Description | Illustration |
|-----------|-------------|--------------|
| **Knowledge capture** | Extract needed information from business documents, videos, voice recordings, emails, and meeting recordings | ![Knowledge capture](images/Knowledge_capture_image.jpg) |
| **Knowledge access** | Intelligent access to organizational knowledge (document repositories, databases, wikis, CRMs) | ![Knowledge access](images/Knowledge_access_image.jpg) |
| **Knowledge synthesis** | Automatic generation of business reports, sales proposals, marketing materials, project proposals | ![Knowledge synthesis](images/Knowledge_synthesis_image.jpg) |

The following **generic use cases** are defined as the top priority at the moment:
| Knowledge process | Generic use cases |
|---|---|
| **Knowledge capture** | A. Incident reporting in industry (e.g., for equipment, buildings)<br>B. Creating construction site diaries<br>C. Creation of transcripts and closed captions in various languages for instructional videos and podcasts<br>D. … |
| **Knowledge access** | A. Customer assistant for complex products and services<br>B. Semantic audio and video search for medical instructions<br>C. Learning assistant |
| **Knowledge synthesis** | A. Sales proposal generation<br>B. Report preparation<br>C. … |


---

## Layer-Based Architecture

The GAIK Toolkit is organized into a layer-based architecture that spans from strategic planning to implementation and security:

| Layer | Purpose | Contents |
|-------|---------|----------|
| **Strategy Layer** | Identification and selection of use cases, GenAI adoption readiness assessment and preparation, business value evaluation | Use case selection framework,  |
| **Requirements Layer** | Requirements capture and specification | Requirement templates, user stories, acceptance criteria |
| **Business Layer** | Use case definition, workflow and work system analysis and redesign | GenAI product canvas, workflow templates, work systems definitions |
| **Implementation Layer** | Executable code, examples, and tests | Source code (`gaik` package), examples, unit tests, deployment packages, connectors |
| **Security Compliance Layer** | Security policies and compliance frameworks | Security guidelines, compliance checks, audit trails |
| **Guidance Layer** | Documentation, best practices, and development guides | CONTRIBUTING.md, documentation (software components & modules), project website |

This architecture ensures that GenAI solutions are built with proper governance, clear requirements, and comprehensive implementation support.

![GAIK Architecture](images/image1.jpg)



## License

This project is licensed under the MIT License – see `LICENSE` for details.
