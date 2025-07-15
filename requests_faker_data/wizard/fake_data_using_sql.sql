INSERT INTO request_request (
    name,
    request_text,
    type_id,
    category_id,
    stage_id,
    priority,
    employee_id,
    assigned_to_id,
    date_request,
    create_uid,
    create_date,
    write_uid,
    write_date
)
SELECT
    'REQ-' || (1000000 + seq)::text,
    jsonb_build_object('en_US', '<p>This is a test request for performance testing.</p>'),
    (SELECT id FROM request_type ORDER BY random() LIMIT 1),
    (SELECT id FROM request_category ORDER BY random() LIMIT 1),
    (SELECT id FROM request_type_stage ORDER BY random() LIMIT 1),
    CASE
        WHEN random() < 0.8 THEN '0'
        WHEN random() < 0.9 THEN '1'
        WHEN random() < 0.95 THEN '2'
        ELSE '3'
    END,
    (SELECT id FROM hr_employee ORDER BY random() LIMIT 1),
    CASE WHEN random() < 0.7 THEN (SELECT id FROM hr_employee ORDER BY random() LIMIT 1) ELSE NULL END,
    now() - (random() * interval '365 days'),
    1,
    now(),
    1,
    now()
FROM generate_series(1, 1000000) seq;