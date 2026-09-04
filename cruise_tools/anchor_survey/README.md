# ⚓ Anchor Survey Tool

Interactive Python tool for estimating seafloor anchor positions from ship survey data.

---

## Features
* **File Input**: Load station .dat files for survey analysis
* **Custom Inputs**: Enter ship transducer depth, drop lat/lon (DMS), and sound speed
* **Real-Time Visualization**: Interactive Matplotlib plot of triangulated anchor position
* **Robust Computation**: Iterative least-squares anchor location solver with RMS error reporting
* **Automated Testing**: Pytest suite with GitHub Actions integration
* **Fully Reproducible**: Conda + pip hybrid environment and Makefile automation

## Installation
```bash
git clone git@github.com:WHOIGit/anchor_survey.git
cd anchor_survey
make env
```

## Usage
#### Launch Gui
```
panel serve gui/survey_gui.py --show
```

#### Run from Python
```
from survey.survey import calculate_anchor_position
```

#### Example data

An example ```stations.dat``` file and ```drop_points.dat``` file are provided in **```data```** folder.

## Quick Start
1️⃣ **Clone the repository**
```bash
git clone git@github.com:WHOIGit/anchor_survey.git
cd anchor_survey
```

---
2️⃣ **Create the environment**

Use the included Makefile to create or update the Conda environment:
```bash
make env
```
Or, manually:
```bash
conda env create -f environment.yml
```

This will:
* Create an environment named anchor_survey
* Install all required dependencies (numpy, pandas, matplotlib, panel)
* Install the package in editable mode (```-e .```)

---
3️⃣ **Activate the environment**

```bash
conda activate anchor_survey
```
Check libraries installed (optional):
```bash
make check-env
```

---
4️⃣ **Launch the GUI**

Run the interactive Panel-based interface:
```bash
make gui
```
This opens your default browser with the web app at: http://localhost:5006/survey_gui

---
5️⃣ **Run tests**

To confirm the code is working properly:
```bash
make test
```


## Repository Organization
```
anchor_survey/
│
├── survey/       
│   ├── __init__.py
│   ├── survey.py                    
│   ├── utils.py                     
│
├── gui/
│   ├── __init__.py
│   ├── survey_gui.py                
│
├── data/
│   ├── example_stations.dat
│   ├── drop_points.dat         
│
├── tests/
│   ├── __init__.py
│   ├── test_survey.py               
│
├── notebooks/
│   ├── exploration.ipynb            
│              
├── environment.yml                  
├── .gitignore
├── README.md
├── LICENSE
├── Makefile                          
└── pyproject.toml                         
```

## Citation & License

This project is released under the BSD-3-clause License

If you use this tool in a publication, please cite:

> Reed, A. (2025). Anchor Triangulation Tool: Python Implementation of Acoustic Survey Positioning. GitHub Repository. https://github.com/reedan88/anchor_survey
