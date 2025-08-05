#!/bin/bash
set -e # exit on error

echo "--- This script demonstrates the correct workflow ---"

# Ensure pyenv is initialized
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Get the same miniconda version we used in the reproduction script
MINICONDA_VERSION=$(pyenv install --list | grep 'miniconda3-3.9' | grep -v '[a-zA-Z]$' | tail -n 1 | tr -d ' ')

if [[ -z "$MINICONDA_VERSION" ]]; then
    echo "Could not find a suitable miniconda version. Please run reproduce_issue.sh first."
    exit 1
fi

echo "--- Step 1: Select Miniconda version with pyenv ---"
pyenv shell $MINICONDA_VERSION
echo "Using Python version:"
python --version

echo "--- Accepting Anaconda Terms of Service ---"
conda config --set channel_priority strict
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# The conda command will now be available
echo "Using conda version:"
conda --version

echo
echo "--- Step 2: Create a new environment with conda ---"
ENV_NAME="my-project-env"
# Remove the environment if it exists from a previous run
conda env remove --name $ENV_NAME > /dev/null 2>&1 || true
echo "Creating new conda environment named '$ENV_NAME'..."
conda create --name $ENV_NAME python=3.9 --yes

echo
echo "--- Step 3: Activate the new environment ---"
# In a script, we need to source the conda activation script
source $(conda info --base)/etc/profile.d/conda.sh
conda activate $ENV_NAME

echo "Active environment is now: $CONDA_DEFAULT_ENV"
echo "Python version in new env:"
python --version
echo "Which python:"
which python

echo
echo "--- Step 4: Install packages into the environment ---"
echo "Installing jupyter..."
conda install jupyter --yes > /dev/null 2>&1

echo
echo "--- FINAL VERIFICATION ---"
echo "Verifying that both 'python -m conda' and 'python -m jupyter' work."

echo
echo "--> Checking 'python -m conda --version':"
if python -m conda --version >/dev/null 2>&1; then
    echo "--> WORKED as expected."
else
    echo "--> FAILED unexpectedly."
fi

echo
echo "--> Checking 'python -m jupyter --version':"
if python -m jupyter --version >/dev/null 2>&1; then
    echo "--> WORKED as expected."
else
    echo "--> FAILED unexpectedly."
fi

echo
echo "--- Solution script finished successfully! ---"

# Deactivate the environment
conda deactivate
pyenv shell --unset
