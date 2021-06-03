# Discrete Sample Summary Spreadsheet Checker
Author: Andrew Reed
Email: areed@whoi.edu

This directory contains a jupyter notebook, python script, and input data needed to run the checker. The checker performs the following critical functions:
1. Column Heading and Order Validation
2. Data Format, Type, and Reasonableness Validation
3. Metadata Consistency Validation

The Column Heading and Order Validation ensures that the column headers are identical


## Dependencies
In order to run the checker, the following packages need to be installed:
* ```numpy```
* ```pandas```
* ```pandas_schema```

If you are using a **conda** or **miniconda** install of python, both the ```numpy``` and ```pandas``` packages should have been installed automatically during setup. If not, these can be install as follows:
```
conda install numpy
conda install pandas
```
The ```pandas_schema``` package is not distrubted on either the default **conda** or **conda-forge** channels. Instead, it should be installed via **```pip```**.


  ```
  pip install -e pandas_schema
  ```
