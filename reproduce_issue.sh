#!/bin/bash
set -e # exit on error

echo "--- Setting up pyenv ---"
if [ -d "$HOME/.pyenv" ]; then
  echo "pyenv is already installed."
else
  git clone https://github.com/pyenv/pyenv.git ~/.pyenv
fi

export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"

if ! command -v pyenv &> /dev/null; then
    echo "pyenv command not found, something is wrong with the installation."
    exit 1
fi

eval "$(pyenv init --path)"
eval "$(pyenv init -)"

if [ -d "$PYENV_ROOT/plugins/pyenv-virtualenv" ]; then
  echo "pyenv-virtualenv is already installed."
else
  git clone https://github.com/pyenv/pyenv-virtualenv.git $(pyenv root)/plugins/pyenv-virtualenv
fi

eval "$(pyenv virtualenv-init -)"

# Select the latest available miniconda version for python 3.9
MINICONDA_VERSION=$(pyenv install --list | grep 'miniconda3-3.9' | grep -v '[a-zA-Z]$' | tail -n 1 | tr -d ' ')

if [[ -z "$MINICONDA_VERSION" ]]; then
    echo "Could not find a miniconda version with python 3.9. Exiting."
    exit 1
fi


echo "--- Installing Miniconda version: $MINICONDA_VERSION ---"
if [ -d "$PYENV_ROOT/versions/$MINICONDA_VERSION" ]; then
    echo "Miniconda version $MINICONDA_VERSION is already installed."
else
    pyenv install $MINICONDA_VERSION
fi

pyenv global $MINICONDA_VERSION
pyenv rehash

echo "--- Accepting Anaconda Terms of Service ---"
"$PYENV_ROOT/versions/$MINICONDA_VERSION/bin/conda" config --set channel_priority strict
"$PYENV_ROOT/versions/$MINICONDA_VERSION/bin/conda" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
"$PYENV_ROOT/versions/$MINICONDA_VERSION/bin/conda" tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

echo "--- Installing Jupyter and virtualenv in base Miniconda environment ---"
# using the pip from the installed miniconda
"$PYENV_ROOT/versions/$MINICONDA_VERSION/bin/pip" install jupyter virtualenv

# Deactivate any active conda env to start clean
if [[ -n "$CONDA_DEFAULT_ENV" ]]; then
    conda deactivate
fi
pyenv global system # unset global version to not interfere

VENV_PATH="$HOME/my-test-venv"
echo
echo "--- SCENARIO 1: Using virtualenv ---"
echo "Creating virtualenv at $VENV_PATH"
rm -rf "$VENV_PATH" # clean up previous runs
mkdir -p "$VENV_PATH"
# Create venv using the python from the miniconda installation
"$PYENV_ROOT/versions/$MINICONDA_VERSION/bin/python" -m virtualenv "$VENV_PATH"

echo "Activating virtualenv using 'source'"
source "$VENV_PATH/bin/activate"

echo "--- Checking commands in virtualenv ---"
echo "python --version:"
python --version
echo "which python:"
which python

echo
echo "--> Checking 'python -m conda --version':"
if python -m conda --version >/dev/null 2>&1; then
    echo "--> python -m conda WORKED unexpectedly."
else
    echo "--> python -m conda FAILED as expected by user."
fi

echo
echo "--> Checking 'python -m jupyter --version':"
if python -m jupyter --version >/dev/null 2>&1; then
    echo "--> python -m jupyter WORKED as expected by user."
else
    echo "--> python -m jupyter FAILED unexpectedly."
fi

echo "Deactivating virtualenv"
deactivate

echo
echo "--- SCENARIO 2: Using 'pyenv activate' ---"
# pyenv activate is a shell function, so we need to use 'pyenv shell' in a script
pyenv shell $MINICONDA_VERSION

echo "--- Checking commands with pyenv activation ---"
echo "python --version:"
python --version
echo "which python:"
which python

echo
echo "--> Checking 'python -m conda --version':"
if python -m conda --version >/dev/null 2>&1; then
    echo "--> python -m conda WORKED as expected by user."
else
    echo "--> python -m conda FAILED unexpectedly."
fi

echo
echo "--> Checking 'python -m jupyter --version':"
if python -m jupyter --version >/dev/null 2>&1; then
    echo "--> python -m jupyter WORKED. This differs from the user's report."
else
    echo "--> python -m jupyter FAILED as expected by user."
fi


pyenv shell --unset

echo
echo "--- Replication script finished ---"
