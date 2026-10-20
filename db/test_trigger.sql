-- Test: the negative-stock trigger should block deductions that
-- would make quantity_on_hand negative.
--
-- Run with:  psql -U stocksense -d stocksense -f db/test_trigger.sql
-- PowerShell: docker compose exec db psql -U stocksense -d stocksense -f /docker-entrypoint-initdb.d/test_trigger.sql
-- Expected:  two PASS messages, zero FAILs.
--
-- Uses a SAVEPOINT so each test is independent, and high-numbered
-- IDs so it works even when seed data is loaded.

BEGIN;

-- Setup: create minimal test data with names unlikely to collide
INSERT INTO categories (category_name) VALUES ('_TriggerTest_Cat');
INSERT INTO suppliers  (supplier_name)  VALUES ('_TriggerTest_Sup');

-- Grab the IDs we just inserted
DO $$
DECLARE
    v_cat_id INT;
    v_sup_id INT;
    v_prod_id INT;
    v_wh_id  INT;
    v_stock  INT;
BEGIN
    SELECT category_id INTO v_cat_id FROM categories WHERE category_name = '_TriggerTest_Cat';
    SELECT supplier_id INTO v_sup_id FROM suppliers  WHERE supplier_name = '_TriggerTest_Sup';

    INSERT INTO products (sku, product_name, category_id, supplier_id, unit_price, lead_time_days)
    VALUES ('_TEST-TRIG', '_Trigger Test Widget', v_cat_id, v_sup_id, 10.00, 5)
    RETURNING product_id INTO v_prod_id;

    INSERT INTO warehouses (warehouse_name, location) VALUES ('_TriggerTest_WH', '_Test City')
    RETURNING warehouse_id INTO v_wh_id;

    INSERT INTO stock_levels (product_id, warehouse_id, quantity_on_hand)
    VALUES (v_prod_id, v_wh_id, 10);

    -- Test 1: valid deduction should succeed
    PERFORM fn_deduct_stock(v_prod_id, v_wh_id, 5);
    SELECT quantity_on_hand INTO v_stock
      FROM stock_levels WHERE product_id = v_prod_id AND warehouse_id = v_wh_id;
    IF v_stock = 5 THEN
        RAISE NOTICE 'PASS: valid deduction reduced stock from 10 to 5';
    ELSE
        RAISE NOTICE 'FAIL: stock is % after deducting 5 from 10', v_stock;
    END IF;

    -- Test 2: over-deduction should be blocked by the trigger
    BEGIN
        PERFORM fn_deduct_stock(v_prod_id, v_wh_id, 999);
        RAISE NOTICE 'FAIL: over-deduction was not blocked';
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'PASS: over-deduction blocked with error: %', SQLERRM;
    END;
END $$;

ROLLBACK;  -- clean up so the test is idempotent
