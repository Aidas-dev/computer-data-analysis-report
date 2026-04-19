# AI Data Center Buildout Promises vs. Reality

## Project Overview
Investigating what parameters (economic climate, supply chain, grid constraints) influence whether an AI data center buildout promise is kept in the United States.

## Setup for Team (4 people)

1. **Clone Repo**
   ```bash
   git clone https://github.com/Aidas-dev/computer-data-analysis-report.git
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

3. **Install Pre-Commit Hooks (Crucial)**
   Run this once locally to prevent Jupyter merge conflicts and hardcoded secret leaks:
   ```bash
   pre-commit install
   ```

4. **Setup DVC (Data Version Control) Locally**
   We use an Oracle Cloud 10GB Bucket (S3 compatible) for data storage.
   - Run `dvc init` (if not done yet).
   - **Configure Oracle Remote:**
     ```bash
     dvc remote add -d oracle_remote s3://computer-data-analysis-report/dvc-storage
     dvc remote modify oracle_remote endpointurl https://fr4e2dl6aex0.compat.objectstorage.eu-frankfurt-1.oraclecloud.com
     ```
   - **Set Secret Credentials (run this locally, do not commit):**
     ```bash
     dvc remote modify --local oracle_remote access_key_id <provided-access-key>
     dvc remote modify --local oracle_remote secret_access_key <provided-secret-key>
     ```
   - Pull data: `dvc pull`

## Google Colab Usage

**🚨 CRITICAL:** When using Google Colab, you MUST run the `notebooks/00-colab-setup.ipynb` notebook at the beginning of *every* new Colab session. Colab environments are ephemeral, so this notebook clones the public code, installs dependencies, and securely pulls the private data from Oracle Cloud using your Colab Secrets.

1. Open Google Colab and click the **🔑 Secrets** icon on the left sidebar.
2. Add these secrets (for DVC and GitHub pushing):
   - Name: `OCI_ACCESS_KEY` | Value: `<provided-access-key>`
   - Name: `OCI_SECRET_KEY` | Value: `<provided-secret-key>`
   - Name: `GITHUB_PAT` | Value: `<your-personal-access-token>`
   - Name: `GITHUB_USERNAME` | Value: `<your-github-username>`
   - Name: `GITHUB_EMAIL` | Value: `<your-github-email>`
3. **Open from GitHub:** Point Colab to `Aidas-dev/computer-data-analysis-report` and open `notebooks/00-colab-setup.ipynb`. Click "Run All".

### Pushing Code from Colab
When you finish your analysis in Colab, **do not download and manually upload files**. 
1. Open the utility notebook: `notebooks/99-push-to-github.ipynb`
2. Run the cells to securely configure Git with your Colab Secrets and push directly to the `main` branch.

## Automated LaTeX Report
This repository contains a GitHub Actions workflow (`.github/workflows/compile_latex.yml`). Every time you push changes to `report/tex/main.tex`, GitHub will automatically compile the LaTeX code into a PDF. You can download the finished PDF from the **Actions** tab on the GitHub repository page.

## Folder Structure
- `data/` - Raw, interim, and processed data (tracked by DVC, NOT Git).
- `docs/` - Research foundation, sources, links.
- `notebooks/` - Colab/Jupyter exploration, data extraction, ML training.
- `src/` - Source code (data pipelines, DVC storage utility).
- `models/` - Trained models (tracked by DVC).
- `report/tex/` - LaTeX report and figures.
