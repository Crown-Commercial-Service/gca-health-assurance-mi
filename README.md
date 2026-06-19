# HWA Transaction Extraction
This repo contains a script and configuration tools to extract MI for specific suppliers under specific frameworks.

## Initial Setup

If this is your first time using this tool, follow these instructions to set things up:
1. Clone the repo
    ```
    git clone REPO-URL
    ```
2. Build the python environment
    ```
    python -m venv venv
    source venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    ```
3. Create the `.env` file, with the following keys:
    ```
    DB_SERVER=
    DB_DRIVER=
    DB_NAME_CUSTOMERS=
    DB_NAME_SUPPLIERS=
    DB_NAME_MI=
    ```
    See the internal docs for the values for each key.

## How to Run
1. Specify your supplier details. Create a `suppliers.tsv` file in the base dir, where the columns are:
    * Column 1: supplier name (in uppercase)
    * Column 2: RM number of framework (if >1 RM number, separate them with commas)
    e.g.
    ```
    SUPPLIER 1  RM00001
    SUPPLIER 2  RM00001,RM00002
    ```
2. Run the ExtractTransactions.py script:
    ```
    python ExtractTransactions.py
    ```