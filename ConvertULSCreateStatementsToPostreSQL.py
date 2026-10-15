import re

CONSTRAINT_KEYWORDS = {
    "NULL", "NOT", "PRIMARY", "KEY", "UNIQUE", "CHECK",
    "REFERENCES", "DEFAULT", "ON", "UPDATE", "DELETE"
}


TYPE_MAP = {
    # Character types
    "VARCHAR": "VARCHAR",
    "VARCHAR(MAX)": "TEXT",
    "NVARCHAR": "VARCHAR",
    "NVARCHAR(MAX)": "TEXT",
    "CHAR": "CHAR",
    "NCHAR": "CHAR",
    "TEXT": "TEXT",

    # Numeric types
    "INT": "INTEGER",
    "INTEGER": "INTEGER",
    "BIGINT": "BIGINT",
    "SMALLINT": "SMALLINT",
    "TINYINT": "SMALLINT",  # closest PG type
    "BIT": "BOOLEAN",
    "DECIMAL": "DECIMAL",
    "NUMERIC": "NUMERIC",
    "MONEY": "NUMERIC(19,4)",
    "SMALLMONEY": "NUMERIC(10,4)",

    # Date/time
    "DATETIME": "TIMESTAMP",
    "DATETIME2": "TIMESTAMP",
    "DATE": "DATE",
    "TIME": "TIME",

    # Binary
    "VARBINARY": "BYTEA",
    "IMAGE": "BYTEA",

    # Other
    "UNIQUEIDENTIFIER": "UUID",
}



POSTGRES_RESERVED = {
    "ALL", "ANALYSE", "ANALYZE", "AND", "ANY", "ARRAY", "AS", "ASC",
    "ASYMMETRIC", "AUTHORIZATION", "BETWEEN", "BINARY", "BOTH", "CASE",
    "CAST", "CHECK", "COLLATE", "COLUMN", "CONCURRENTLY", "CONSTRAINT",
    "CREATE", "CROSS", "CURRENT_CATALOG", "CURRENT_DATE", "CURRENT_ROLE",
    "CURRENT_SCHEMA", "CURRENT_TIME", "CURRENT_TIMESTAMP", "CURRENT_USER",
    "DEFAULT", "DEFERRABLE", "DESC", "DISTINCT", "DO", "ELSE", "END",
    "EXCEPT", "FALSE", "FETCH", "FOR", "FOREIGN", "FREEZE", "FROM",
    "FULL", "GRANT", "GROUP", "HAVING", "ILIKE", "IN", "INITIALLY",
    "INNER", "INTERSECT", "INTO", "IS", "ISNULL", "JOIN", "LATERAL",
    "LEADING", "LEFT", "LIKE", "LIMIT", "LOCALTIME", "LOCALTIMESTAMP",
    "NATURAL", "NOT", "NOTNULL", "NULL", "OFFSET", "ON", "ONLY", "OR",
    "ORDER", "OUTER", "OVERLAPS", "PLACING", "PRIMARY", "REFERENCES",
    "RETURNING", "RIGHT", "SELECT", "SESSION_USER", "SIMILAR", "SOME",
    "SYMMETRIC", "TABLE", "TABLESAMPLE", "THEN", "TO", "TRAILING",
    "TRUE", "UNION", "UNIQUE", "USER", "USING", "VARIADIC", "VERBOSE",
    "WHEN", "WHERE", "WINDOW", "WITH"
}

# Identifiers in CREATE TABLE appear in predictable places.
IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"

TOKEN_REGEX = re.compile(
    r"""
    ("[^"]*")                 | # quoted identifiers
    (

\[[^\]

]+\]

)              | # SQL Server bracketed identifiers
    ('[^']*')                 | # single-quoted strings
    (--[^\n]*)                | # single-line comments
    (/\*[\s\S]*?\*/)          | # multi-line comments
    ([A-Za-z_][A-Za-z0-9_]*)  | # identifiers
    (\S)                      | # punctuation
    (\s+)                     | # WHITESPACE (NEW!)
    """,
    re.VERBOSE
)


def normalize_identifier(identifier: str) -> str:
    '''
        Convert SQL Server [brackets] → plain identifier.
        Function: normalize_identifier
        Parameters:
            identifier (str): field name
        returns : str: identifier without [ or ]
    '''
    if identifier.startswith("[") and identifier.endswith("]"):
        return identifier[1:-1]
    return identifier

def quote_if_reserved(identifier: str) -> str:
    '''
        Quote only if identifier is a reserved PostgreSQL keyword.
        Function: quote_if_reserved
        Parameters:
            identifier (str): field name
        returns : str: identifier quoted as needed    
    '''
    
    if identifier.upper() in POSTGRES_RESERVED:
        return f'"{identifier}"'
    return identifier

def map_type(sql_type: str) -> str:
    '''
        Maps SQL types to PostgreSQL types
        Function: map_type
        Parameters:
            sql_type (str): the typed field
        returns : str: SQL type mapped to PG type
    '''
    
    original = sql_type.strip().upper()

    # Handle IDENTITY(...) → GENERATED ALWAYS AS IDENTITY
    identity = None
    if "IDENTITY" in original:
        identity = "GENERATED ALWAYS AS IDENTITY"
        original = re.sub(r"IDENTITY\s*\([^)]*\)", "", original).strip()

    # Extract base type and optional size
    m = re.match(r"([A-Z]+)(\([^)]+\))?", original)
    if not m:
        return sql_type  # fallback

    base, size = m.groups()
    size = size or ""

    # Handle VARCHAR(MAX) / NVARCHAR(MAX)
    if "MAX" in size:
        return "TEXT" + (" " + identity if identity else "")

    # Map base type
    mapped = TYPE_MAP.get(base, base)

    # Preserve size for types that support it
    if size and mapped not in ("TEXT", "BYTEA", "UUID", "BOOLEAN", "INTEGER", "BIGINT", "SMALLINT"):
        mapped = f"{mapped}{size}"

    # Append identity if needed
    if identity:
        mapped += f" {identity}"

    return mapped

def tokenize_ddl(sql: str) -> str:
    '''
        Takes the SQL string and applies the functions to normalize and update it.
        Function: tokenize_ddl
        Parameters:
            sqlstring (str): SQL to tokenize
        returns : str: SQL fixed for PG
    '''
    
    output = []
    prev_identifier = None
    in_columns = False  # NEW: track whether we are inside column definitions

    for match in TOKEN_REGEX.finditer(sql):
        quoted, bracketed, string_sq, comment_sl, comment_ml, identifier, other, whitespace = match.groups()

        # Detect entering/exiting column list
        if other == "(":
            in_columns = True
            output.append("(")
            prev_identifier = None
            continue

        if other == ")":
            in_columns = False
            output.append(")")
            prev_identifier = None
            continue

        # Handle NOT NULL as a single constraint
        if identifier and identifier.upper() == "NOT":
            # Peek ahead: if next token is NULL, treat both as constraints
            next_match = TOKEN_REGEX.search(sql, match.end())
            if next_match:
                next_identifier = next_match.group(5)
                if next_identifier and next_identifier.upper() == "NULL":
                    output.append("NOT")
                    prev_identifier = "NOT"
                    continue

        if quoted:
            output.append(quoted)
            prev_identifier = None

        elif bracketed:
            ident = normalize_identifier(bracketed)
            # Only quote inside column list
            output.append(quote_if_reserved(ident) if in_columns else ident)
            prev_identifier = ident

        elif whitespace:
            output.append(whitespace)
            prev_identifier = None


        elif identifier:
            upper = identifier.upper()

            # Constraint keywords should NEVER be quoted
            if upper in CONSTRAINT_KEYWORDS:
                output.append(identifier)
                prev_identifier = identifier
                continue

            # If inside column list → this is a column name or type
            if in_columns:
                # Type mapping
                if prev_identifier and upper in TYPE_MAP:
                    output.append(map_type(identifier))
                else:
                    output.append(quote_if_reserved(identifier))
            else:
                # Outside column list → never quote
                output.append(identifier)

            prev_identifier = identifier


        else:
            # Always append a string, never None
            token = string_sq or comment_sl or comment_ml or other
            output.append(token or "")
            prev_identifier = None

    return "".join(output)


#read in file and split on create NOTE this removes the word
with open (r"C:\Users\ldupe\OneDrive\AdditionalDocuments\Radio\public_access_database_definitions_sql_20250417.txt","r") as sqlfile:
    filecontent = sqlfile.read()

createtable = filecontent.split("create")
 
 #now clean up and generate the new file
with open(r"C:\Users\ldupe\OneDrive\AdditionalDocuments\Radio\ULS_PostgreSQL_style.sql","w", encoding="utf-8") as sqloutput:
    for sqlstring in createtable[1:]:
        #fix reserved/protected words
        tokenized= tokenize_ddl(sqlstring)
        #replace go with ;
        semicolon = re.sub("^go", ";", tokenized, flags=re.MULTILINE)
        # quote table names to protect case
        quote_table = re.sub(r"PUBACC_(\w{2})", r'"\g<0>"', semicolon)
        #remove dbo (not appropriate for postgres)
        remove_do = re.sub(r"dbo\.", "", quote_table)
        #turn dates into dates
        final_string = re.sub(r'(_date\s+)[Cc][Hh][Aa][Rr]\(10\)', r'\1date', remove_do)
        #split removes the create
        
        sqloutput.write(f"create{final_string}")    