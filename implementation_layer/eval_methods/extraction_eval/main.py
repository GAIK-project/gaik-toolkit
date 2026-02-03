from pathlib import Path
import os

from IE import run_field_extraction
from IE_evaluation import evaluate_field_matching

#Ground Truth (GT) is in JSON Format
#should be changed

INPUT_FOLDER = Path("/data/transcripts") 
GROUND_TRUTH_DIR = Path("data/GT") 
PREDICTION_DIR = Path("data/predictions") 
OUTPUT_FILE = Path("ErrorReport.txt") 

MODEL_NAME = "gpt-5"
API_KEY = os.getenv("OPENAI_API_KEY")

if API_KEY is None:
    raise ValueError("Please set your OPENAI_API_KEY environment variable")

if __name__ == "__main__":
    
    print("Information Extraction (IE)..")
    run_field_extraction(
        input_dir=INPUT_FOLDER,
        output_dir=PREDICTION_DIR,
        model_name=MODEL_NAME,
        api_key=API_KEY
    )
    print("IE completed.\n")

    print("IE evaluation...")
    evaluate_field_matching(
        ground_truth_dir=GROUND_TRUTH_DIR,
        prediction_dir=PREDICTION_DIR,
        output_file=OUTPUT_FILE
    )
    print("IE Evaluation finished")