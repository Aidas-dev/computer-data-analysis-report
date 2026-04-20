#!/bin/bash
set -e

# Universal Setup Script for Google Colab + GitHub Codespaces
# Run this script as Cell 1 of every notebook: !bash setup.sh

echo "Detecting environment..."

# Detect if running in Google Colab
if command -v google.colab &> /dev/null; then
    echo "Running in Google Colab..."
    
    # Clone repository if not present
    if [ ! -d "computer-data-analysis-report" ]; then
        echo "Cloning repository..."
        git clone --depth 1 https://github.com/Aidas-dev/computer-data-analysis-report.git
    fi
    
    cd computer-data-analysis-report
    
    # Install uv for fast dependency resolution
    echo "Installing uv..."
    pip install uv -q
    
    # Install dependencies
    echo "Installing dependencies with uv..."
    uv pip install --system -r requirements.txt -q
    
    # Configure DVC if secrets are available
    if [ -n "$OCI_ACCESS_KEY" ] && [ -n "$OCI_SECRET_KEY" ]; then
        echo "Configuring DVC..."
        dvc remote modify --local oracle_remote access_key_id "$OCI_ACCESS_KEY"
        dvc remote modify --local oracle_remote secret_access_key "$OCI_SECRET_KEY"
        dvc pull -q || true
    fi
    
    echo "✅ Colab setup complete!"

# Detect if running in GitHub Codespaces
elif [ -n "$CODESPACES" ] || [ -n "$GITHUB_CODESPACE_URL" ]; then
    echo "Running in GitHub Codespaces..."
    
    cd $(dirname "$GITHUB_WORKSPACE"/computer-data-analysis-report 2>/dev/null) || cd /workspaces/computer-data-analysis-report
    
    # Install uv
    echo "Installing uv..."
    pip install uv -q
    
    # Install dependencies
    echo "Installing dependencies with uv..."
    uv pip install -r requirements.txt -q
    
    # Configure DVC if secrets are available
    if [ -n "$OCI_ACCESS_KEY" ] && [ -n "$OCI_SECRET_KEY" ]; then
        echo "Configuring DVC..."
        dvc remote modify --local oracle_remote access_key_id "$OCI_ACCESS_KEY"
        dvc remote modify --local oracle_remote secret_access_key "$OCI_SECRET_KEY"
        dvc pull -q || true
    fi
    
    echo "✅ Codespaces setup complete!"

# Local development (no Colab, no Codespaces)
else
    echo "Running locally..."
    
    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        echo "Installing uv..."
        pip install uv -q
    fi
    
    # Install dependencies
    echo "Installing dependencies with uv..."
    uv pip install -r requirements.txt -q
    
    echo "✅ Local setup complete!"
fi

echo "Environment ready for data analysis!"
