# Data Analysis Project

## Setup for Team (4 people)

1. **Clone Repo**
   ```bash
   git clone <repo-url>
   cd computer-data-analysis-report
   ```

2. **Install Environment (Conda)**
   ```bash
   conda env create -f environment.yml
   conda activate data-analysis-env
   ```

3. **Install DVC (Data Version Control)**
   - Needs DVC installed globally or in conda environment.
   - Run `dvc init` (if not done yet by repo creator).
   - Configure remote storage (e.g., S3, Google Drive): `dvc remote add -d myremote <url>`
   - Pull data: `dvc pull`

## Folder Structure
- `data/` - Raw, interim, and processed data (tracked by DVC, NOT Git).
- `docs/` - Important info, sources, links.
- `notebooks/` - Colab/Jupyter exploration.
- `src/` - Source code (data pipelines, features, models).
- `models/` - Trained models (tracked by DVC).
- `report/tex/` - LaTeX report and figures.