import re
import pandas as pd 

'''
    ULS data is manually entered and not standardized. Thre can be misspellings, all CAPS entries, and no standardization of the data.
    This mostly AI generated set of data and functions will make sure your data is standardized. Sorry I can't handle misspellings of towns, etc.
'''
# ---------- USPS STYLE TABLES ----------

SUFFIX_MAP = {
    "STREET": "St", "ST": "St",
    "ROAD": "Rd", "RD": "Rd",
    "AVENUE": "Ave", "AVE": "Ave",
    "BOULEVARD": "Blvd", "BLVD": "Blvd",
    "DRIVE": "Dr", "DR": "Dr",
    "LANE": "Ln", "LN": "Ln",
    "COURT": "Ct", "CT": "Ct",
    "PLACE": "Pl", "PL": "Pl",
    "TERRACE": "Ter", "TER": "Ter",
    "CIRCLE": "Cir", "CIR": "Cir",
    "HIGHWAY": "Hwy", "HWY": "Hwy",
    "PARKWAY": "Pkwy", "PKWY": "Pkwy",
}

DIR_MAP = {
    "NORTH": "N", "N": "N",
    "SOUTH": "S", "S": "S",
    "EAST": "E", "E": "E",
    "WEST": "W", "W": "W",
    "NORTHEAST": "NE", "NE": "NE",
    "NORTHWEST": "NW", "NW": "NW",
    "SOUTHEAST": "SE", "SE": "SE",
    "SOUTHWEST": "SW", "SW": "SW",
}

UNIT_MAP = {
    "APARTMENT": "Apt", "APT": "Apt",
    "SUITE": "Ste", "STE": "Ste",
    "BUILDING": "Bldg", "BLDG": "Bldg",
    "FLOOR": "Fl", "FL": "Fl",
    "UNIT": "Unit",
}





# ---------- TEXT PROPER CASE (Your Regex Style) ----------
#Fix ALL CAPS
def proper_case_text(value: str) -> str:
    '''
        Changes the cae of a string.
        
        Paramaters:
            value (str): the item to be fixed
            
        Returns:
            (str) the cleaned string
    '''
    if not value:
        return value

    value = value.strip().lower()

    value = re.sub(
        r"(^|[\s\-\'])\w",
        lambda m: m.group(0).upper(),
        value
    )

    return value

# ---------- MAIN NORMALIZER ----------
## This fixes street addressed amd nakes them fit a structure
def normalize_usps_address(address: str) -> str:
    '''
        Uses the USPS style tables to standardize the addresses provided in the file.
        
        Paramaters:
            address (str): address to standardize
            
        Returns:
            (str): the corrected address
    '''
    if not address:
        return address

    address = address.replace(".", " ")
    address = re.sub(r"\s+", " ", address).strip()

    words = address.split()
    normalized_words = []

    seen_suffix = False

    for i, word in enumerate(words):
        upper = word.upper()

        # ---------- Numbers ----------
        if upper.isdigit():
            normalized_words.append(upper)
            continue

        # ---------- Street suffix ----------
        if upper in SUFFIX_MAP:
            normalized_words.append(SUFFIX_MAP[upper])
            seen_suffix = True
            continue

        # ---------- Directionals ----------
        # ONLY convert AFTER suffix
        if upper in DIR_MAP and seen_suffix:
            normalized_words.append(DIR_MAP[upper])
            continue

        # ---------- Unit ----------
        if upper in UNIT_MAP:
            normalized_words.append(UNIT_MAP[upper])
            continue

        # ---------- Default (street name / place name) ----------
        normalized_words.append(proper_case_text(word))

    return " ".join(normalized_words)

#cleanup comments file
def file_cleaner(filepath):
    '''
        Fixes specifically the CO file as its format can generate odd extra lines.
        Function: file_cleaner
        Parameters:
            filepath (str): full path to the file to be fixed
    '''
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    # Replace newlines that are NOT followed by a new row starting with CO|
    fixed = re.sub(r"\n(?!CO\|)", " ", raw)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(fixed)


#Checks
def check_column_counts(filepath, columns):
    '''
        Checks to make sure the column count did not change (will warn about file format updates).
        Function: check_column_counts
        Parameters:
            filepath (str): full path to the file to be fixed
            columns (list): the columns which should be present        
    '''
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        first_line = f.readline()

    actual_cols = first_line.count("|") + 1
    expected_cols = len(columns)

    if actual_cols != expected_cols:
        raise ValueError(
            f"FILE FORMAT CHANGED: expected {expected_cols}, got {actual_cols}"
        )    

def check_value_length(tablename, df, engine):
    '''
        Verifies that the length of the data will not exceed the defined length in the database.
        Function: check_value_length
        Parameters:
            tablename (str): database table name
            df (dataframe): the data loaded into the dataframe to check
            engine (sqlalchemy engine): engine to look up the table definition
    '''
    query = """
        SELECT column_name, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = '{tablename}'
        AND character_maximum_length IS NOT NULL;
        """ 
    limits_df = pd.read_sql(query, engine)

    limits = dict(zip(limits_df.column_name, limits_df.character_maximum_length))
    
    bad = {}

    for col, maxlen in limits.items():
        mask = df[col].astype(str).str.len() > maxlen
        if mask.any():
            bad[col] = df.loc[mask, col]

    return bad, limits
