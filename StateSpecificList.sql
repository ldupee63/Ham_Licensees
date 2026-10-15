select DISTINCT
    e.unique_system_identifier,
    e.call_sign,
    e.first_name,
    e.mi,
    e.last_name,
   COALESCE(e.street_address, 'PO Box ' || e.po_box) AS "Street",
    e.city,
    e.state,
    CASE
        WHEN LENGTH(e.zip_code) > 5 THEN LEFT(e.zip_code, 5) || '-' || RIGHT(e.zip_code, LENGTH(e.zip_code) - 5)
        ELSE e.zip_code
    END AS zip,
    u."description" AS License,
    --s.log_date AS granted,
    NULL as granted,
    c."description" AS Comment
from
    PUBACC_EN e
    INNER JOIN PUBACC_HS s on e.unique_system_identifier = s.unique_system_identifier
    INNER JOIN PUBACC_AM a on e.unique_system_identifier = a.unique_system_identifier
    LEFT JOIN PUBACC_CO c on e.unique_system_identifier = c.unique_system_identifier
    LEFT JOIN PUBACC_HD d on e.unique_system_identifier = d.unique_system_identifier
    INNER JOIN ULSCodes u on u."service" = 'AM'
    and u.code = a.operator_class
WHERE
    e."state" = 'VT'
    --and s.code IN ('LIISS','AUTHPR', 'LIMOD')
    AND (
        c."description" NOT LIKE '%deceased%'
        or c."description" IS NULL
    )
    AND NOT EXISTS (
        SELECT
            1
        FROM
            PUBACC_HS x
        WHERE
            x.unique_system_identifier = e.unique_system_identifier
            AND x.code IN ('LITERM', 'LIEXP', 'LICAN')
    )
    AND d.expired_date > (CURRENT_DATE - INTERVAL '2 years')
    AND d.cancellation_date IS NULL
ORDER BY
    e.unique_system_identifier
