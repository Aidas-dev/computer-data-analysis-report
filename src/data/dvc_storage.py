import pandas as pd
import subprocess
import os
from typing import Union, List

def store_dataframes_in_dvc(
    data: Union[pd.DataFrame, List[pd.DataFrame]], 
    names: Union[str, List[str]], 
    folder_type: str = 'raw',
    base_path: str = '../data'
):
    """
    Saves a DataFrame or a list of DataFrames to CSV files, pushes them to the DVC remote,
    and stages the resulting .dvc tracker files in Git.
    
    Parameters:
    - data: A single pandas DataFrame or a list of DataFrames to save.
    - names: A single string name or a list of string names for the files (without extension).
    - folder_type: The subfolder inside the data directory (e.g., 'raw', 'interim').
    - base_path: The base path to the data directory, relative to where this is executed.
    """
    
    # Normalize inputs to lists for uniform processing
    if isinstance(data, pd.DataFrame):
        data = [data]
    if isinstance(names, str):
        names = [names]
        
    if len(data) != len(names):
        raise ValueError(f"Length mismatch: Provided {len(data)} DataFrames but {len(names)} names.")
        
    output_dir = os.path.join(base_path, folder_type)
    os.makedirs(output_dir, exist_ok=True)
    
    saved_files = []
    
    for df, name in zip(data, names):
        file_path = os.path.join(output_dir, f"{name}.csv")
        print(f"💾 Saving DataFrame to {file_path}...")
        df.to_csv(file_path, index=False)
        saved_files.append(file_path)
        
    for file_path in saved_files:
        print(f"📦 Tracking {file_path} with DVC...")
        try:
            subprocess.run(["dvc", "add", file_path], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to track {file_path} with DVC: {e.stderr.decode('utf-8')}")
            continue
            
        dvc_file = f"{file_path}.dvc"
        gitignore_file = os.path.join(os.path.dirname(file_path), ".gitignore")
        
        print(f"☁️ Pushing {dvc_file} to Oracle Cloud Bucket...")
        try:
            subprocess.run(["dvc", "push", dvc_file], check=True, capture_output=True)
            print(f"✅ Successfully pushed {os.path.basename(file_path)} data to the Oracle bucket.")
            
            # [NEW] Automatically stage the .dvc tracker and .gitignore updates in Git
            print(f"🔗 Staging {dvc_file} and {gitignore_file} in Git...")
            subprocess.run(["git", "add", dvc_file, gitignore_file], check=True, capture_output=True)
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to push or stage {dvc_file}: {e.stderr.decode('utf-8')}")

    print("\n🚨 CRITICAL: The raw data is safe in Oracle Cloud, but the Git tracking files (.dvc) are only staged locally.")
    print("👉 To share this new data with your team, you MUST run the `notebooks/99-push-to-github.ipynb` notebook before closing Colab!")

