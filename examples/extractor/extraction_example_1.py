"""
Example 1: End-to-end dynamic schema generation and extraction.

This script demonstrates how to:
1. Configure the OpenAI/Azure client.
2. Generate a schema from natural-language requirements using SchemaGenerator.
3. Extract structured data from sample documents and save the results.
"""

import sys
from pathlib import Path

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gaik.extractor import DataExtractor, SchemaGenerator, get_openai_config

if __name__ == "__main__":
    # Simple example showing how to use the SchemaGenerator class
    print("=" * 80)
    print("SCHEMA GENERATOR - EXAMPLE USAGE")
    print("=" * 80)

    # Configure OpenAI client (Azure or standard OpenAI)
    # Set use_azure=True for Azure OpenAI, or use_azure=False for standard OpenAI
    config = get_openai_config(use_azure=True)

    # Example: Extract project information
    user_requirements = """
    The task is to extract all the required fields needed for the official Construction Site Daily Log
    (Työmaapäiväkirja) from the transcript of an audio recording made by a construction site supervisor,
    who verbally describes the day's events at the worksite.

    The output MUST follow the exact field structure below, using the English field names provided.
    Ensure exact data types for each field.
    All extracted fields should be as brief as possible, not exceeding a few key words.

    Fields to Extract:
    Extract the following fields exactly as they appear below. The structure reflects the diary template from the uploaded page:

    1. Site / Project Name [Subject of the diary]
    2. Author [Name of the person completing the diary]
    3. Weather [choose one: cold, hot, warm]
    4. Date [Use this date format: DD/MM/YYY]
    5. Resources – Personnel [e.g., Supervisors: 2 persons, Workers: 1 person, Subcontractors: 4 persons, Total: 7 persons]
    6. Work Week [Week number, e.g., 2]
    7. Tasks of the Day (Own Work) [choose one: some work, no work]
    8. Events of the Day [some events, no events]
    9. Attachments [total number of attachments]
    """

    sample_document = [
        """
Date: 10 April 2025.
Site: 4120-01 Revontulentie 3, 02100 Espoo, Revontuli Office Building, partial demolition.
Work week 4.
Weather: +6 °C, partly cloudy, wind approx. 4 m/s.
Resources: 1 site manager, 3 in-house workers, 4 workers from the asbestos removal contractor, 2 other subcontractor workers. Total of 10 persons on site.
Work performed: asbestos removal continued in the technical rooms of the basement level as planned. Interior demolition was carried out on the third floor; partition walls in the corridors, glass walls and old office furniture were demolished. Sorting was carried out in the inner courtyard, and two truckloads of debris were hauled to the landfill. Metal fraction and wood were separated.
Events: during opening works in the third-floor kitchen area, old pipe insulation containing asbestos was discovered that had not been identified in the original survey. The area was immediately isolated and work there was suspended. The asbestos removal contractor’s site manager visited the site and agreed on an additional survey and removal measures.
Attachments: 6 photos of the asbestos discovery and area isolation, 3 photos of sorting and loading of debris. In addition, an email confirmation from the asbestos removal contractor regarding the additional work is attached.
Deviations: unplanned asbestos discovery in the third-floor kitchen. Work in this area was stopped and recorded as an interrupted work phase.
Work phases started: no completely new work phases, but the scope of asbestos removal was extended to include the kitchen area.
Ongoing work phases: asbestos removal, interior demolition, sorting, debris hauling, site fencing, dust control, protection works.
Completed work phases: no work phases fully completed today.
Interrupted work phases and reasons: interior demolition in the third-floor kitchen area was interrupted due to the asbestos discovery; an additional survey and approval for the extended asbestos removal are awaited.
Requested extensions of time: the asbestos removal contractor estimates that the additional work will take approximately 2–3 working days. A request for extension of time and an additional work quotation will be submitted to the client once the additional survey has been completed.
Inspections carried out: the main contractor’s site management and the asbestos contractor’s site manager carried out an inspection of the kitchen area on site. A written report is forthcoming.
Supervisor’s remarks: the supervisor stressed that the asbestos area must be clearly marked and access must be prevented. No other remarks.
Additional or variation works: additional asbestos removal work in the third-floor kitchen area; scope and price will be specified after completion of the survey.

        """
    ]

    # Step 1: Generate schema
    generator = SchemaGenerator(config=config)

    print("\nStep 1: Generating schema...")
    print("-" * 80)

    schema = generator.generate_schema(user_requirements=user_requirements)
    print(f"\n✓ Generated schema: {schema.__name__}")
    print(f"  Structure: {generator.structure_analysis.structure_type}")
    print(f"  Fields: {[f.field_name for f in generator.item_requirements.fields]}")

    # Step 2: Extract data using generated schema
    print("\nStep 2: Extracting data...")
    print("-" * 80)

    extractor = DataExtractor(config=config)
    results = extractor.extract(
        extraction_model=schema,
        requirements=generator.item_requirements,
        user_requirements=user_requirements,
        documents=sample_document,
        save_json=True,
        json_path="extraction_results.json",
    )

    # Display results
    print("\n" + "=" * 80)
    print("EXTRACTION RESULTS")
    print("=" * 80)
    import json

    print(json.dumps(results, indent=2, default=str))
