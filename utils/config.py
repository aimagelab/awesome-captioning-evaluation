import json
import os

def load_model_paths(config_path="config/model_paths.json"):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Model config not found at: {config_path}")
    
    with open(config_path, "r") as f:
        return json.load(f)