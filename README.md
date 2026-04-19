# Data Analysis Project

## Setup for Team (4 people)

1. **Clone Repo**
   ```bash
   git clone <repo-url>
   cd computer-data-analysis-report
   ```

2. **Install Environment**
   
   **Option A: Mamba / Conda (Recommended)**
   Using `mamba` is highly recommended for much faster installation times.
   ```bash
   mamba env create -f environment.yml
   mamba activate data-analysis-env
   ```
   *(If you don't have mamba, replace `mamba` with `conda` in the commands above)*

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
     dvc remote add -d oracle_remote s3://computer-data-analysis-report/dvc-storage
     dvc remote modify oracle_remote endpointurl https://fr4e2dl6aex0.compat.objectstorage.eu-frankfurt-1.oraclecloud.com
     ```
   - **Set Secret Credentials (run this locally, do not commit):**
     ```bash
     # Note: Contact repo owner for the Access Key and Secret Key!
     # The --local flag prevents keys from being tracked by Git.
     dvc remote modify --local oracle_remote access_key_id <provided-access-key>
     dvc remote modify --local oracle_remote secret_access_key <provided-secret-key>
     ```
   - Pull data: `dvc pull`

## Google Colab Usage

**🚨 CRITICAL:** When using Google Colab, you MUST run the `notebooks/00-colab-setup.ipynb` notebook at the beginning of *every* new Colab session. Colab environments are ephemeral, so this notebook clones the public code, installs dependencies, and securely pulls the private data from Oracle Cloud using your Colab Secrets.
1. Open Google Colab and click the **🔑 Secrets** icon on the left sidebar.
2. Add two new secrets:
   - Name: `OCI_ACCESS_KEY` | Value: `<provided-access-key>`
   - Name: `OCI_SECRET_KEY` | Value: `<provided-secret-key>`
3. Run this block in your first Colab cell:
   ```python
   # 1. Clone repository
   !git clone <your-repo-url>
   %cd computer-data-analysis-report

   # 2. Install dependencies (including DVC S3 and downgraded botocore)
   !pip install -r requirements.txt

   # 3. Authenticate DVC securely using Colab Secrets
   from google.colab import userdata
   import os

   access_key = userdata.get('OCI_ACCESS_KEY')
   secret_key = userdata.get('OCI_SECRET_KEY')

   !dvc remote modify --local oracle_remote access_key_id {access_key}
   !dvc remote modify --local oracle_remote secret_access_key {secret_key}

   # 4. Pull data
   !dvc pull
   ```

## Folder Structure
- `data/` - Raw, interim, and processed data (tracked by DVC, NOT Git).
- `docs/` - Important info, sources, links.
- `notebooks/` - Colab/Jupyter exploration.
- `src/` - Source code (data pipelines, features, models).
- `models/` - Trained models (tracked by DVC).
- `report/tex/` - LaTeX report and figures.