import re
import unicodedata

def make_postgresql(sqlstatement, type) -> str:
    '''
        This function will take the FCC format file, designed for TSQL
        and convert it to PostgreSQL format. 
    '''
    
    #fix reserved/protected words
    start = sqlstatement.find('(')
    end = sqlstatement.rfind(')')

    if start != -1 and end != -1:
        columns = sqlstatement[start + 1:end]

        columns = re.sub(
            r'^(\s*)([A-Za-z_][A-Za-z0-9_]*)',
            r'\1"\2"',
            columns,
            flags=re.MULTILINE
        )

        sqlstatement = sqlstatement[:start + 1] + columns + sqlstatement[end:]
    
    #replace go with ;
    semicolon = re.sub("^go", ";", sqlstatement, flags=re.MULTILINE)
    
    # quote table names to protect case
    #quote_table = re.sub(r"PUBACC_(\w{2})", r'"\g<0>"', semicolon)
    
    #remove dbo (not appropriate for postgres)
    if type == "staging":
        remove_dbo = re.sub(r"dbo\.", "staging_", semicolon)    
    else:
        remove_dbo = re.sub(r"dbo\.", "", semicolon)
    
    #datetime to timestamp
    replace_datetime = re.sub(r"datetime", "timestamp", remove_dbo)
    #tinyint to smallint
    replace_tinyint = re.sub("tinyint","smallint", replace_datetime)
    ##turn dates into dates
    final_string = re.sub(
        r'("[^"]*_date[^"]*")(\s+)char\(10\)',
        r'\1\2date',
        replace_tinyint,
        flags=re.IGNORECASE
        )
    return final_string
        


#grab the content 
with open (r"FILEPATH","r") as sqlfile:
    filecontent = sqlfile.read()
    
table_names = ['PUBACC_AM','PUBACC_CO','PUBACC_EN','PUBACC_HD','PUBACC_HS']
tables = []
for tn in table_names:
    table_regex = rf"create table dbo\.{tn}\b[\s\S]*?\)\s*\r?\n\s*go\s*(?:\r?\n|$)"
    table_match = re.search(table_regex, filecontent, flags=re.IGNORECASE | re.MULTILINE)
    
    if table_match:
        tables.append(make_postgresql(table_match.group(0), "staging")) #create the staging table
        tables.append(make_postgresql(table_match.group(0), "dbo")) #create the working table
    
pg_table_sql = "\n\n".join(tables)

#add some additional data and indexes

uls_codes = """
create table ulscodes
(
    "service" varchar(5),
    "code" varchar(10),
    "description" varchar(250)
);
"""

uls_inserts = """
insert into ulscodes (service, code, description) values
    ('AM','T','Technician'),
    ('AM','P','Technician Plus'),
    ('AM','N','Novice'),
    ('AM','G','General'),
    ('AM','E','Amateur Extra'),
    ('AM','A','Advanced');
"""
lastcomment = """  
CREATE TABLE lastcomment
  (
    unique_system_identifier numeric(9,0),
    code char(6)
  );
"""

indexes = """
create index idx_am_identifier on pubacc_am(unique_system_identifier);
create index idx_co_identifier on pubacc_co(unique_system_identifier);
create index idx_en_identifier on pubacc_en(unique_system_identifier);
create index idx_en_callsign on pubacc_en(call_sign);
create index idx_hd_identifier on pubacc_hd(unique_system_identifier);
create index idx_hs_identifier on pubacc_hs(unique_system_identifier, code);
create index idx_lastcomment_identifier on lastcomment (unique_system_identifier);
"""


staging_to_working_procedures = """
CREATE PROCEDURE MERGE_INTO_PUBACC_AM()
LANGUAGE plpgsql
AS $$
BEGIN
    MERGE INTO PUBACC_AM AS tgt
    USING staging_PUBACC_AM AS src
    ON tgt.record_type = src.record_type
    AND tgt.unique_system_identifier = src.unique_system_identifier

    WHEN MATCHED AND (
       tgt.uls_file_num IS DISTINCT FROM src.uls_file_num
    OR tgt.ebf_number IS DISTINCT FROM src.ebf_number
    OR tgt.callsign IS DISTINCT FROM src.callsign
    OR tgt.operator_class IS DISTINCT FROM src.operator_class
    OR tgt.group_code IS DISTINCT FROM src.group_code
    OR tgt.region_code IS DISTINCT FROM src.region_code
    OR tgt.trustee_callsign IS DISTINCT FROM src.trustee_callsign
    OR tgt.trustee_indicator IS DISTINCT FROM src.trustee_indicator
    OR tgt.physician_certification IS DISTINCT FROM src.physician_certification
    OR tgt.ve_signature IS DISTINCT FROM src.ve_signature
    OR tgt.systematic_callsign_change IS DISTINCT FROM src.systematic_callsign_change
    OR tgt.vanity_callsign_change IS DISTINCT FROM src.vanity_callsign_change
    OR tgt.vanity_relationship IS DISTINCT FROM src.vanity_relationship
    OR tgt.previous_callsign IS DISTINCT FROM src.previous_callsign
    OR tgt.previous_operator_class IS DISTINCT FROM src.previous_operator_class
    OR tgt.trustee_name IS DISTINCT FROM src.trustee_name
) THEN UPDATE SET
            uls_file_num = src.uls_file_num,
            ebf_number = src.ebf_number,
            callsign = src.callsign,
            operator_class = src.operator_class,
            group_code = src.group_code,
            region_code = src.region_code,
            trustee_callsign = src.trustee_callsign,
            trustee_indicator = src.trustee_indicator,
            physician_certification = src.physician_certification,
            ve_signature = src.ve_signature,
            systematic_callsign_change = src.systematic_callsign_change,
            vanity_callsign_change = src.vanity_callsign_change,
            vanity_relationship = src.vanity_relationship,
            previous_callsign = src.previous_callsign,
            previous_operator_class = src.previous_operator_class,
            trustee_name = src.trustee_name

    WHEN NOT MATCHED THEN
        INSERT (
            record_type,
            unique_system_identifier,
            uls_file_num,
            ebf_number,
            callsign,
            operator_class,
            group_code,
            region_code,
            trustee_callsign,
            trustee_indicator,
            physician_certification,
            ve_signature,
            systematic_callsign_change,
            vanity_callsign_change,
            vanity_relationship,
            previous_callsign,
            previous_operator_class,
            trustee_name
        )
        VALUES (
            src.record_type,
            src.unique_system_identifier,
            src.uls_file_num,
            src.ebf_number,
            src.callsign,
            src.operator_class,
            src.group_code,
            src.region_code,
            src.trustee_callsign,
            src.trustee_indicator,
            src.physician_certification,
            src.ve_signature,
            src.systematic_callsign_change,
            src.vanity_callsign_change,
            src.vanity_relationship,
            src.previous_callsign,
            src.previous_operator_class,
            src.trustee_name
        );
END;
$$;




CREATE PROCEDURE update_PUBACC_CO()
LANGUAGE plpgsql
AS $$
DECLARE max_comment_date timestamp;

BEGIN
SELECT COALESCE(MAX(comment_date), '1900-01-01') AS max_comment_date
INTO max_comment_date
FROM PUBACC_CO;

INSERT INTO PUBACC_CO (
    record_type,
    unique_system_identifier,
    uls_file_num,
    callsign,
    comment_date,
    "description",
    status_code,
    status_date
)
SELECT
    s.record_type,
    s.unique_system_identifier,
    s.uls_file_num,
    s.callsign,
    s.comment_date,
    s.description,
    s.status_code,
    s.status_date
FROM staging_PUBACC_CO AS s
WHERE s.comment_date > max_comment_date;

END;
$$;



CREATE PROCEDURE MERGE_INTO_PUBACC_EN()
LANGUAGE plpgsql
AS $$
BEGIN
MERGE INTO PUBACC_EN AS target
USING staging_PUBACC_EN AS source
ON target.unique_system_identifier = source.unique_system_identifier

-- When records match, update the existing records in the target table
WHEN MATCHED AND (
        target.record_type IS DISTINCT FROM source.record_type
        OR target.uls_file_number IS DISTINCT FROM source.uls_file_number
        OR target.ebf_number IS DISTINCT FROM source.ebf_number
        OR target.call_sign IS DISTINCT FROM source.call_sign
        OR target.entity_type IS DISTINCT FROM source.entity_type
        OR target.licensee_id IS DISTINCT FROM source.licensee_id
        OR target.entity_name IS DISTINCT FROM source.entity_name
        OR target.first_name IS DISTINCT FROM source.first_name
        OR target.mi IS DISTINCT FROM source.mi
        OR target.last_name IS DISTINCT FROM source.last_name
        OR target.suffix IS DISTINCT FROM source.suffix
        OR target.phone IS DISTINCT FROM source.phone
        OR target.fax IS DISTINCT FROM source.fax
        OR target.email IS DISTINCT FROM source.email
        OR target.street_address IS DISTINCT FROM source.street_address
        OR target.city IS DISTINCT FROM source.city
        OR target."state" IS DISTINCT FROM source."state"
        OR target.zip_code IS DISTINCT FROM source.zip_code
        OR target.po_box IS DISTINCT FROM source.po_box
        OR target.attention_line IS DISTINCT FROM source.attention_line
        OR target.sgin IS DISTINCT FROM source.sgin
        OR target.frn IS DISTINCT FROM source.frn
        OR target.applicant_type_code IS DISTINCT FROM source.applicant_type_code
        OR target.applicant_type_other IS DISTINCT FROM source.applicant_type_other
        OR target.status_code IS DISTINCT FROM source.status_code
        OR target.status_date IS DISTINCT FROM source.status_date
        OR target.lic_category_code IS DISTINCT FROM source.lic_category_code
        OR target.linked_license_id IS DISTINCT FROM source.linked_license_id
        OR target.linked_callsign IS DISTINCT FROM source.linked_callsign
)
THEN
    UPDATE SET
        record_type = source.record_type,
        uls_file_number = source.uls_file_number,
        ebf_number = source.ebf_number,
        call_sign = source.call_sign,
        entity_type = source.entity_type,
        licensee_id = source.licensee_id,
        entity_name = source.entity_name,
        first_name = source.first_name,
        mi = source.mi,
        last_name = source.last_name,
        suffix = source.suffix,
        phone = source.phone,
        fax = source.fax,
        email = source.email,
        street_address = source.street_address,
        city = source.city,
        "state" = source."state",
        zip_code = source.zip_code,
        po_box = source.po_box,
        attention_line = source.attention_line,
        sgin = source.sgin,
        frn = source.frn,
        applicant_type_code = source.applicant_type_code,
        applicant_type_other = source.applicant_type_other,
        status_code = source.status_code,
        status_date = source.status_date,
        lic_category_code = source.lic_category_code,
        linked_license_id = source.linked_license_id,
        linked_callsign = source.linked_callsign

-- When records do not match, insert new records into the target table
WHEN NOT MATCHED THEN
    INSERT (
        record_type,
        unique_system_identifier,
        uls_file_number,
        ebf_number,
        call_sign,
        entity_type,
        licensee_id,
        entity_name,
        first_name,
        mi,
        last_name,
        suffix,
        phone,
        fax,
        email,
        street_address,
        city,
        "state",
        zip_code,
        po_box,
        attention_line,
        sgin,
        frn,
        applicant_type_code,
        applicant_type_other,
        status_code,
        status_date,
        lic_category_code,
        linked_license_id,
        linked_callsign
    )
    VALUES (
        source.record_type,
        source.unique_system_identifier,
        source.uls_file_number,
        source.ebf_number,
        source.call_sign,
        source.entity_type,
        source.licensee_id,
        source.entity_name,
        source.first_name,
        source.mi,
        source.last_name,
        source.suffix,
        source.phone,
        source.fax,
        source.email,
        source.street_address,
        source.city,
        source."state",
        source.zip_code,
        source.po_box,
        source.attention_line,
        source.sgin,
        source.frn,
        source.applicant_type_code,
        source.applicant_type_other,
        source.status_code,
        source.status_date,
        source.lic_category_code,
        source.linked_license_id,
        source.linked_callsign
    );
END;
$$;

CREATE PROCEDURE MERGE_INTO_PUBACC_HD()
LANGUAGE plpgsql
AS $$
BEGIN

MERGE INTO PUBACC_HD AS target
USING staging_PUBACC_HD AS source
ON target.unique_system_identifier = source.unique_system_identifier

-- When records match, update the existing records in the target table
WHEN MATCHED AND
(        target.record_type IS DISTINCT FROM source.record_type
 OR target.uls_file_number IS DISTINCT FROM source.uls_file_number
 OR target.ebf_number IS DISTINCT FROM source.ebf_number
 OR target.call_sign IS DISTINCT FROM source.call_sign
 OR target.license_status IS DISTINCT FROM source.license_status
 OR target.radio_service_code IS DISTINCT FROM source.radio_service_code
 OR target.grant_date IS DISTINCT FROM source.grant_date
 OR target.expired_date IS DISTINCT FROM source.expired_date
 OR target.cancellation_date IS DISTINCT FROM source.cancellation_date
 OR target.eligibility_rule_num IS DISTINCT FROM source.eligibility_rule_num
 OR target.applicant_type_code_reserved IS DISTINCT FROM source.applicant_type_code_reserved
 OR target.alien IS DISTINCT FROM source.alien
 OR target.alien_government IS DISTINCT FROM source.alien_government
 OR target.alien_corporation IS DISTINCT FROM source.alien_corporation
 OR target.alien_officer IS DISTINCT FROM source.alien_officer
 OR target.alien_control IS DISTINCT FROM source.alien_control
 OR target.revoked IS DISTINCT FROM source.revoked
 OR target.convicted IS DISTINCT FROM source.convicted
 OR target.adjudged IS DISTINCT FROM source.adjudged
 OR target.involved_reserved IS DISTINCT FROM source.involved_reserved
 OR target.common_carrier IS DISTINCT FROM source.common_carrier
 OR target.non_common_carrier IS DISTINCT FROM source.non_common_carrier
 OR target.private_comm IS DISTINCT FROM source.private_comm
 OR target."fixed" IS DISTINCT FROM source."fixed"
 OR target.mobile IS DISTINCT FROM source.mobile
 OR target.radiolocation IS DISTINCT FROM source.radiolocation
 OR target.satellite IS DISTINCT FROM source.satellite
 OR target.developmental_or_sta IS DISTINCT FROM source.developmental_or_sta
 OR target.interconnected_service IS DISTINCT FROM source.interconnected_service
 OR target.certifier_first_name IS DISTINCT FROM source.certifier_first_name
 OR target.certifier_mi IS DISTINCT FROM source.certifier_mi
 OR target.certifier_last_name IS DISTINCT FROM source.certifier_last_name
 OR target.certifier_suffix IS DISTINCT FROM source.certifier_suffix
 OR target.certifier_title IS DISTINCT FROM source.certifier_title
 OR target.sex IS DISTINCT FROM source.sex
 OR target.african_american IS DISTINCT FROM source.african_american
 OR target.native_american IS DISTINCT FROM source.native_american
 OR target.hawaiian IS DISTINCT FROM source.hawaiian
 OR target.asian IS DISTINCT FROM source.asian
 OR target.white IS DISTINCT FROM source.white
 OR target.ethnicity IS DISTINCT FROM source.ethnicity
 OR target.effective_date IS DISTINCT FROM source.effective_date
 OR target.last_action_date IS DISTINCT FROM source.last_action_date
 OR target.auction_id IS DISTINCT FROM source.auction_id
 OR target.reg_stat_broad_serv IS DISTINCT FROM source.reg_stat_broad_serv
 OR target.band_manager IS DISTINCT FROM source.band_manager
 OR target.type_serv_broad_serv IS DISTINCT FROM source.type_serv_broad_serv
 OR target.alien_ruling IS DISTINCT FROM source.alien_ruling
 OR target.licensee_name_change IS DISTINCT FROM source.licensee_name_change
 OR target.whitespace_ind IS DISTINCT FROM source.whitespace_ind
 OR target.additional_cert_choice IS DISTINCT FROM source.additional_cert_choice
 OR target.additional_cert_answer IS DISTINCT FROM source.additional_cert_answer
 OR target.discontinuation_ind IS DISTINCT FROM source.discontinuation_ind
 OR target.regulatory_compliance_ind IS DISTINCT FROM source.regulatory_compliance_ind
 OR target.eligibility_cert_900 IS DISTINCT FROM source.eligibility_cert_900
 OR target.transition_plan_cert_900 IS DISTINCT FROM source.transition_plan_cert_900
 OR target.return_spectrum_cert_900 IS DISTINCT FROM source.return_spectrum_cert_900
 OR target.payment_cert_900 IS DISTINCT FROM source.payment_cert_900

)
  THEN UPDATE SET
        record_type = source.record_type,
        uls_file_number = source.uls_file_number,
        ebf_number = source.ebf_number,
        call_sign = source.call_sign,
        license_status = source.license_status,
        radio_service_code = source.radio_service_code,
        grant_date = source.grant_date,
        expired_date = source.expired_date,
        cancellation_date = source.cancellation_date,
        eligibility_rule_num = source.eligibility_rule_num,
        applicant_type_code_reserved = source.applicant_type_code_reserved,
        alien = source.alien,
        alien_government = source.alien_government,
        alien_corporation = source.alien_corporation,
        alien_officer = source.alien_officer,
        alien_control = source.alien_control,
        revoked = source.revoked,
        convicted = source.convicted,
        adjudged = source.adjudged,
        involved_reserved = source.involved_reserved,
        common_carrier = source.common_carrier,
        non_common_carrier = source.non_common_carrier,
        private_comm = source.private_comm,
        "fixed" = source."fixed",
        mobile = source.mobile,
        radiolocation = source.radiolocation,
        satellite = source.satellite,
        developmental_or_sta = source.developmental_or_sta,
        interconnected_service = source.interconnected_service,
        certifier_first_name = source.certifier_first_name,
        certifier_mi = source.certifier_mi,
        certifier_last_name = source.certifier_last_name,
        certifier_suffix = source.certifier_suffix,
        certifier_title = source.certifier_title,
        sex = source.sex,
        african_american = source.african_american,
        native_american = source.native_american,
        hawaiian = source.hawaiian,
        asian = source.asian,
        white = source.white,
        ethnicity = source.ethnicity,
        effective_date = source.effective_date,
        last_action_date = source.last_action_date,
        auction_id = source.auction_id,
        reg_stat_broad_serv = source.reg_stat_broad_serv,
        band_manager = source.band_manager,
        type_serv_broad_serv = source.type_serv_broad_serv,
        alien_ruling = source.alien_ruling,
        licensee_name_change = source.licensee_name_change,
        whitespace_ind = source.whitespace_ind,
        additional_cert_choice = source.additional_cert_choice,
        additional_cert_answer = source.additional_cert_answer,
        discontinuation_ind = source.discontinuation_ind,
        regulatory_compliance_ind = source.regulatory_compliance_ind,
        eligibility_cert_900 = source.eligibility_cert_900,
        transition_plan_cert_900 = source.transition_plan_cert_900,
        return_spectrum_cert_900 = source.return_spectrum_cert_900,
        payment_cert_900 = source.payment_cert_900

-- When records do not match, insert new records into the target table
WHEN NOT MATCHED THEN
    INSERT (
        record_type,
        unique_system_identifier,
        uls_file_number,
        ebf_number,
        call_sign,
        license_status,
        radio_service_code,
        grant_date,
        expired_date,
        cancellation_date,
        eligibility_rule_num,
        applicant_type_code_reserved,
        alien,
        alien_government,
        alien_corporation,
        alien_officer,
        alien_control,
        revoked,
        convicted,
        adjudged,
        involved_reserved,
        common_carrier,
        non_common_carrier,
        private_comm,
        "fixed",
        mobile,
        radiolocation,
        satellite,
        developmental_or_sta,
        interconnected_service,
        certifier_first_name,
        certifier_mi,
        certifier_last_name,
        certifier_suffix,
        certifier_title,
        sex,
        african_american,
        native_american,
        hawaiian,
        asian,
        white,
        ethnicity,
        effective_date,
        last_action_date,
        auction_id,
        reg_stat_broad_serv,
        band_manager,
        type_serv_broad_serv,
        alien_ruling,
        licensee_name_change,
        whitespace_ind,
        additional_cert_choice,
        additional_cert_answer,
        discontinuation_ind,
        regulatory_compliance_ind,
        eligibility_cert_900,
        transition_plan_cert_900,
        return_spectrum_cert_900,
        payment_cert_900
    )
    VALUES (
        source.record_type,
        source.unique_system_identifier,
        source.uls_file_number,
        source.ebf_number,
        source.call_sign,
        source.license_status,
        source.radio_service_code,
        source.grant_date,
        source.expired_date,
        source.cancellation_date,
        source.eligibility_rule_num,
        source.applicant_type_code_reserved,
        source.alien,
        source.alien_government,
        source.alien_corporation,
        source.alien_officer,
        source.alien_control,
        source.revoked,
        source.convicted,
        source.adjudged,
        source.involved_reserved,
        source.common_carrier,
        source.non_common_carrier,
        source.private_comm,
        source."fixed",
        source.mobile,
        source.radiolocation,
        source.satellite,
        source.developmental_or_sta,
        source.interconnected_service,
        source.certifier_first_name,
        source.certifier_mi,
        source.certifier_last_name,
        source.certifier_suffix,
        source.certifier_title,
        source.sex,
        source.african_american,
        source.native_american,
        source.hawaiian,
        source.asian,
        source.white,
        source.ethnicity,
        source.effective_date,
        source.last_action_date,
        source.auction_id,
        source.reg_stat_broad_serv,
        source.band_manager,
        source.type_serv_broad_serv,
        source.alien_ruling,
        source.licensee_name_change,
        source.whitespace_ind,
        source.additional_cert_choice,
        source.additional_cert_answer,
        source.discontinuation_ind,
        source.regulatory_compliance_ind,
        source.eligibility_cert_900,
        source.transition_plan_cert_900,
        source.return_spectrum_cert_900,
        source.payment_cert_900
    );
END;
$$;



CREATE PROCEDURE update_PUBACC_HS()
LANGUAGE plpgsql
AS $$

BEGIN

WITH MaxLogDates AS (
    SELECT 
        unique_system_identifier,
        COALESCE(MAX(log_date), '1900-01-01'::DATE) AS MaxLogDate
    FROM 
        PUBACC_HS
    GROUP BY 
        unique_system_identifier
)

INSERT INTO PUBACC_HS (
    record_type,
    unique_system_identifier,
    uls_file_number,
    callsign,
    log_date,
    "code"
)
SELECT 
    s.record_type,
    s.unique_system_identifier,
    s.uls_file_number,
    s.callsign,
    s.log_date,
    s.code
FROM 
    staging_PUBACC_HS AS s
LEFT JOIN 
    MaxLogDates AS m
    ON s.unique_system_identifier = m.unique_system_identifier
WHERE
    m.unique_system_identifier IS NULL OR
    s.log_date > m.MaxLogDate;

END;
$$;

"""

#Create the new SQL file
with open(r"C:\Users\ldupe\OneDrive\AdditionalDocuments\Radio\ULS_PostgreSQL_style.sql","w", encoding="utf-8") as sqloutput:
    sqloutput.write(pg_table_sql)
    sqloutput.write(uls_codes)
    sqloutput.write(uls_inserts)
    sqloutput.write(lastcomment)
    sqloutput.write(indexes)
    sqloutput.write(staging_to_working_procedures)