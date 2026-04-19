# Data Analysis Project

## Setup for Team (4 people)

1. **Clone Repo**
   ```bash
   git clone <repo-url>
   cd computer-data-analysis-report
   ```

2. **Install Environment**
   
   **Option A: Conda**
   ```bash
   conda env create -f environment.yml
   conda activate data-analysis-env
   ```

   **Option B: Pip / Venv**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Install DVC (Data Version Control)**
   - Needs DVC installed globally or in conda/pip environment.
   - We use an Oracle Cloud 10GB Bucket (S3 compatible) for data storage.
   - Run `dvc init` (if not done yet).
   - **Configure Oracle Remote:**
     ```bash
     # OCI S3 API URL Format: https://<namespace>.compat.objectstorage.<region>.oraclecloud.com
     dvc remote add -d oracle_remote s3://<your-bucket-name>/dvc-storage
     dvc remote modify oracle_remote endpointurl https://fr4e2dl6aex0.compat.objectstorage.eu-frankfurt-1.oraclecloud.com
     
     # Note: Contact repo owner for the Access Key and Secret Key!
     dvc remote modify oracle_remote access_key_id <provided-access-key>
     dvc remote modify oracle_remote secret_access_key <provided-secret-key>
     ```
   - Pull data: `dvc pull`

## Folder Structure
- `data/` - Raw, interim, and processed data (tracked by DVC, NOT Git).
- `docs/` - Important info, sources, links.
- `notebooks/` - Colab/Jupyter exploration.
- `src/` - Source code (data pipelines, features, models).
- `models/` - Trained models (tracked by DVC).
- `report/tex/` - LaTeX report and figures.