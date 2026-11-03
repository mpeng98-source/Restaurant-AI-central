"""Independent opening balances, protected evidence and operational audit records.

0001-0004 remain byte-for-byte unchanged. All functions are security invoker.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_inventory_pilot"
down_revision = "0004_inventory_approvals"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text(SCHEMA))
    scope = "organization_id::text=current_setting('app.organization_id',true) AND location_id::text=ANY(string_to_array(current_setting('app.location_ids',true),','))"
    for table in ('inventory_opening_requests', 'inventory_opening_decisions', 'inventory_operations', 'inventory_evidence'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        read = "inventory_can(organization_id,location_id,'inventory:read')"
        write = "inventory_can(organization_id,location_id,'inventory:catalog:manage')"
        if table == 'inventory_opening_decisions':
            write = "inventory_can(organization_id,location_id,'inventory:approve')"
        if table == 'inventory_evidence':
            read = 'EXISTS(SELECT 1 FROM inventory_count_sessions s WHERE s.id=session_id AND s.organization_id=inventory_evidence.organization_id AND s.location_id=inventory_evidence.location_id)'
            write = read
        op.execute(f'CREATE POLICY pilot_read ON {table} FOR SELECT USING ({scope} AND ({read}))')
        op.execute(f'CREATE POLICY pilot_insert ON {table} FOR INSERT WITH CHECK ({scope} AND ({write}))')
        op.execute(f'REVOKE UPDATE,DELETE,TRUNCATE ON {table} FROM chubby_app')
        if table != 'inventory_evidence':
            op.execute(f'CREATE TRIGGER pilot_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION prevent_inventory_decision_mutation()')
            op.execute(f'CREATE TRIGGER pilot_no_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION prevent_inventory_decision_mutation()')
    op.execute('GRANT UPDATE ON inventory_evidence TO chubby_app')
    op.execute(f"CREATE POLICY evidence_update ON inventory_evidence FOR UPDATE USING ({scope} AND inventory_can(organization_id,location_id,'inventory:approve')) WITH CHECK ({scope} AND inventory_can(organization_id,location_id,'inventory:approve'))")
    # Existing permissive catalog policies are intersected with these restrictions.
    for table in ('inventory_categories', 'inventory_items', 'inventory_vendors'):
        allowed = "inventory_can(organization_id,nullif(split_part(current_setting('app.location_ids',true),',',1),'')::uuid,'inventory:catalog:manage')"
        for command in ('INSERT', 'UPDATE', 'DELETE'):
            clause = f'WITH CHECK ({allowed})' if command == 'INSERT' else f'USING ({allowed})' + (f' WITH CHECK ({allowed})' if command == 'UPDATE' else '')
            op.execute(f'CREATE POLICY pilot_catalog_{command.lower()} ON {table} AS RESTRICTIVE FOR {command} {clause}')
    for table in ('inventory_location_items', 'inventory_storage_zones', 'inventory_item_unit_conversions', 'inventory_vendor_items'):
        allowed = "inventory_can(organization_id,location_id,'inventory:catalog:manage')"
        for command in ('INSERT', 'UPDATE', 'DELETE'):
            clause = f'WITH CHECK ({allowed})' if command == 'INSERT' else f'USING ({allowed})' + (f' WITH CHECK ({allowed})' if command == 'UPDATE' else '')
            op.execute(f'CREATE POLICY pilot_catalog_{command.lower()} ON {table} AS RESTRICTIVE FOR {command} {clause}')
    op.execute("CREATE POLICY pilot_movement_writer ON stock_movements AS RESTRICTIVE FOR INSERT WITH CHECK (inventory_can(organization_id,location_id,'inventory:approve') OR inventory_can(organization_id,location_id,'inventory:catalog:manage'))")
    op.execute(sa.text(FUNCTIONS))
    op.execute(sa.text(SNAPSHOT_FUNCTION))


SCHEMA = r"""
CREATE TABLE inventory_opening_requests (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, location_id uuid NOT NULL, inventory_item_id uuid NOT NULL,
 quantity numeric(24,6) NOT NULL CHECK(quantity>=0), unit_code varchar(24) NOT NULL REFERENCES inventory_units(code),
 base_quantity numeric(24,6) NOT NULL CHECK(base_quantity>=0), base_unit_code varchar(24) NOT NULL,
 factor numeric(30,12) NOT NULL CHECK(factor>0), sku varchar(80) NOT NULL, item_name varchar(180) NOT NULL,
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000), idempotency_key varchar(128) NOT NULL CHECK(length(trim(idempotency_key))>0),
 requested_by uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(organization_id,location_id,id), UNIQUE(organization_id,location_id,idempotency_key),
 FOREIGN KEY(organization_id,location_id,inventory_item_id) REFERENCES inventory_location_items(organization_id,location_id,inventory_item_id)
);
CREATE TABLE inventory_opening_decisions (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, location_id uuid NOT NULL, request_id uuid NOT NULL,
 action varchar(16) NOT NULL CHECK(action IN ('approved','rejected')), reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 2000),
 idempotency_key varchar(128) NOT NULL CHECK(length(trim(idempotency_key))>0), decided_by uuid NOT NULL REFERENCES users(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), audit_log_id uuid NOT NULL REFERENCES audit_logs(id) DEFERRABLE INITIALLY DEFERRED,
 UNIQUE(organization_id,location_id,id), UNIQUE(organization_id,location_id,request_id), UNIQUE(organization_id,location_id,idempotency_key),
 FOREIGN KEY(organization_id,location_id,request_id) REFERENCES inventory_opening_requests(organization_id,location_id,id)
);
CREATE TABLE inventory_operations (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, location_id uuid NOT NULL,
 kind varchar(24) NOT NULL CHECK(kind IN ('catalog_import','reconciliation','opening_import')), idempotency_key varchar(128) NOT NULL CHECK(length(trim(idempotency_key))>0),
 request_hash varchar(64) NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'), payload jsonb NOT NULL,
 actor_id uuid NOT NULL REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(organization_id,location_id,kind,idempotency_key), FOREIGN KEY(organization_id,location_id) REFERENCES locations(organization_id,id)
);
CREATE TABLE inventory_evidence (
 id uuid PRIMARY KEY, organization_id uuid NOT NULL, location_id uuid NOT NULL, session_id uuid NOT NULL,
 object_key varchar(512) NOT NULL UNIQUE, sha256 varchar(64) NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'),
 byte_size integer NOT NULL CHECK(byte_size BETWEEN 1 AND 5242880), mime_type varchar(32) NOT NULL CHECK(mime_type='image/jpeg'),
 scanner_status varchar(24) NOT NULL CHECK(scanner_status IN ('sanitized_only','scanned')),
 uploaded_by uuid NOT NULL REFERENCES users(id), uploaded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 retain_until timestamptz NOT NULL, legal_hold boolean NOT NULL DEFAULT false, deleted_at timestamptz,
 control_reason text NOT NULL CHECK(length(trim(control_reason)) BETWEEN 1 AND 2000),
 UNIQUE(organization_id,location_id,id),
 FOREIGN KEY(organization_id,location_id,session_id) REFERENCES inventory_count_sessions(organization_id,location_id,id)
);
CREATE INDEX evidence_retention ON inventory_evidence(organization_id,location_id,retain_until) WHERE deleted_at IS NULL;
"""

FUNCTIONS = r"""
CREATE FUNCTION inventory_opening_factor(org uuid,loc uuid,item uuid,unit text) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT coalesce((SELECT factor_to_stock_unit FROM inventory_item_unit_conversions WHERE organization_id=org AND location_id=loc AND inventory_item_id=item AND unit_code=unit),
   CASE WHEN u.dimension=b.dimension THEN u.factor_to_base/b.factor_to_base ELSE NULL END)
 FROM inventory_items i JOIN inventory_units b ON b.code=i.base_unit_code JOIN inventory_units u ON u.code=unit
 JOIN inventory_location_items li ON li.organization_id=i.organization_id AND li.inventory_item_id=i.id AND li.location_id=loc
 WHERE i.organization_id=org AND i.id=item AND i.active AND li.active
$$;
CREATE FUNCTION inventory_opening_request_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE i inventory_items;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.organization_id::text||':'||NEW.location_id::text,0));
 IF NEW.requested_by::text IS DISTINCT FROM current_setting('app.user_id',true) OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:catalog:manage') THEN RAISE EXCEPTION 'opening setup permission required' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM stock_movements WHERE organization_id=NEW.organization_id AND location_id=NEW.location_id AND inventory_item_id=NEW.inventory_item_id)
    OR EXISTS(SELECT 1 FROM inventory_opening_decisions d JOIN inventory_opening_requests r ON r.id=d.request_id WHERE r.organization_id=NEW.organization_id AND r.location_id=NEW.location_id AND r.inventory_item_id=NEW.inventory_item_id AND d.action='approved') THEN
    RAISE EXCEPTION 'opening balance already initialized or ledger activity exists'; END IF;
 SELECT * INTO i FROM inventory_items WHERE organization_id=NEW.organization_id AND id=NEW.inventory_item_id;
 NEW.factor:=inventory_opening_factor(NEW.organization_id,NEW.location_id,NEW.inventory_item_id,NEW.unit_code);
 IF NEW.factor IS NULL THEN RAISE EXCEPTION 'active item and explicit compatible unit required'; END IF;
 NEW.base_quantity:=round(NEW.quantity*NEW.factor,6); NEW.base_unit_code:=i.base_unit_code; NEW.sku:=i.sku; NEW.item_name:=i.name;
 NEW.created_at:=clock_timestamp(); NEW.reason:=trim(NEW.reason); RETURN NEW;
END $$;
CREATE TRIGGER opening_request_guard BEFORE INSERT ON inventory_opening_requests FOR EACH ROW EXECUTE FUNCTION inventory_opening_request_guard();
CREATE FUNCTION inventory_request_opening(org uuid,loc uuid,item uuid,qty numeric,unit text,reason_text text,key_text text) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE previous inventory_opening_requests; result uuid;
BEGIN
 IF NOT inventory_can(org,loc,'inventory:catalog:manage') THEN RAISE EXCEPTION 'opening setup permission required' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(org::text||':'||loc::text,0));
 SELECT * INTO previous FROM inventory_opening_requests WHERE organization_id=org AND location_id=loc AND idempotency_key=key_text;
 IF previous.id IS NOT NULL THEN
  IF previous.inventory_item_id=item AND previous.quantity=qty AND previous.unit_code=unit AND previous.reason=trim(reason_text) AND previous.requested_by::text=current_setting('app.user_id',true) THEN RETURN previous.id; END IF;
  RAISE EXCEPTION 'opening idempotency key reused with different input'; END IF;
 result:=gen_random_uuid();
 INSERT INTO inventory_opening_requests(id,organization_id,location_id,inventory_item_id,quantity,unit_code,base_quantity,base_unit_code,factor,sku,item_name,reason,idempotency_key,requested_by)
 VALUES(result,org,loc,item,qty,unit,0,'',1,'','',reason_text,key_text,nullif(current_setting('app.user_id',true),'')::uuid);
 RETURN result;
END $$;
CREATE FUNCTION inventory_opening_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r inventory_opening_requests;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(NEW.organization_id::text||':'||NEW.location_id::text,0));
 SELECT * INTO r FROM inventory_opening_requests WHERE organization_id=NEW.organization_id AND location_id=NEW.location_id AND id=NEW.request_id;
 IF r.id IS NULL THEN RAISE EXCEPTION 'opening request not found' USING ERRCODE='P0002'; END IF;
 IF NEW.decided_by::text IS DISTINCT FROM current_setting('app.user_id',true) OR NEW.decided_by=r.requested_by OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve') THEN RAISE EXCEPTION 'independent opening reviewer required' USING ERRCODE='42501'; END IF;
 IF NEW.action='approved' THEN
  IF inventory_opening_factor(r.organization_id,r.location_id,r.inventory_item_id,r.unit_code) IS DISTINCT FROM r.factor OR NOT EXISTS(SELECT 1 FROM inventory_items i WHERE i.id=r.inventory_item_id AND i.base_unit_code=r.base_unit_code AND i.sku=r.sku AND i.name=r.item_name) THEN RAISE EXCEPTION 'opening catalog changed; submit a fresh proposal'; END IF;
  IF EXISTS(SELECT 1 FROM stock_movements WHERE organization_id=r.organization_id AND location_id=r.location_id AND inventory_item_id=r.inventory_item_id)
    OR EXISTS(SELECT 1 FROM inventory_opening_decisions d JOIN inventory_opening_requests o ON o.id=d.request_id WHERE o.organization_id=r.organization_id AND o.location_id=r.location_id AND o.inventory_item_id=r.inventory_item_id AND d.action='approved') THEN RAISE EXCEPTION 'opening balance already initialized or ledger activity exists'; END IF;
 END IF;
 NEW.reason:=trim(NEW.reason); NEW.created_at:=clock_timestamp(); NEW.audit_log_id:=gen_random_uuid(); RETURN NEW;
END $$;
CREATE TRIGGER opening_decision_guard BEFORE INSERT ON inventory_opening_decisions FOR EACH ROW EXECUTE FUNCTION inventory_opening_decision_guard();
CREATE FUNCTION inventory_post_opening() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r inventory_opening_requests;
BEGIN
 SELECT * INTO r FROM inventory_opening_requests WHERE id=NEW.request_id;
 INSERT INTO audit_logs(id,organization_id,location_id,user_id,action,entity_type,entity_id,metadata) VALUES(NEW.audit_log_id,NEW.organization_id,NEW.location_id,NEW.decided_by,'inventory.opening.'||NEW.action,'inventory_opening_decision',NEW.id::text,jsonb_build_object('request_id',r.id,'proposer',r.requested_by,'quantity',r.quantity::text,'unit',r.unit_code,'factor',r.factor::text,'base_quantity',r.base_quantity::text,'reason',NEW.reason));
 IF NEW.action='approved' AND r.base_quantity>0 THEN
 INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,source_type,source_id,actor_id,approver_id,reason,balance_before,balance_after,audit_log_id)
 VALUES(NEW.id,r.organization_id,r.location_id,r.inventory_item_id,'opening',r.base_quantity,r.base_unit_code,'opening:'||NEW.id::text,'inventory_opening_decision',NEW.id::text,NEW.decided_by,NEW.decided_by,NEW.reason,0,r.base_quantity,NEW.audit_log_id);
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER opening_post AFTER INSERT ON inventory_opening_decisions FOR EACH ROW EXECUTE FUNCTION inventory_post_opening();
CREATE FUNCTION inventory_decide_opening(org uuid,loc uuid,request uuid,decision text,reason_text text,key_text text) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE previous inventory_opening_decisions; result uuid; actor uuid;
BEGIN
 IF NOT inventory_can(org,loc,'inventory:approve') THEN RAISE EXCEPTION 'opening approval permission required' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(org::text||':'||loc::text,0)); actor:=nullif(current_setting('app.user_id',true),'')::uuid;
 SELECT * INTO previous FROM inventory_opening_decisions WHERE organization_id=org AND location_id=loc AND (request_id=request OR idempotency_key=key_text);
 IF previous.id IS NOT NULL THEN
  IF previous.request_id=request AND previous.action=decision AND previous.reason=trim(reason_text) AND previous.idempotency_key=key_text AND previous.decided_by=actor THEN RETURN previous.id; END IF;
  RAISE EXCEPTION 'opening already decided or idempotency key reused'; END IF;
 result:=gen_random_uuid();
 INSERT INTO inventory_opening_decisions(id,organization_id,location_id,request_id,action,reason,idempotency_key,decided_by,audit_log_id) VALUES(result,org,loc,request,decision,reason_text,key_text,actor,gen_random_uuid()); RETURN result;
END $$;
CREATE FUNCTION inventory_opening_movement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.movement_type='opening' AND (pg_trigger_depth()<2 OR NOT EXISTS(
  SELECT 1 FROM inventory_opening_decisions d JOIN inventory_opening_requests r ON r.id=d.request_id WHERE d.organization_id=NEW.organization_id AND d.location_id=NEW.location_id
  AND d.id=NEW.id AND d.action='approved' AND r.inventory_item_id=NEW.inventory_item_id AND r.base_quantity=NEW.quantity_delta AND r.base_unit_code=NEW.unit_code
  AND NEW.source_type='inventory_opening_decision' AND NEW.source_id=d.id::text AND NEW.actor_id=d.decided_by AND NEW.approver_id=d.decided_by
  AND NEW.audit_log_id=d.audit_log_id AND NEW.balance_before=0 AND NEW.balance_after=r.base_quantity AND NEW.reason=d.reason
 )) THEN RAISE EXCEPTION 'opening movements require an independently approved immutable proposal' USING ERRCODE='42501'; END IF; RETURN NEW;
END $$;
CREATE TRIGGER stock_opening_validate BEFORE INSERT ON stock_movements FOR EACH ROW EXECUTE FUNCTION inventory_opening_movement_guard();
CREATE FUNCTION inventory_pilot_record_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 INSERT INTO audit_logs(id,organization_id,location_id,user_id,action,entity_type,entity_id,metadata)
 VALUES(gen_random_uuid(),NEW.organization_id,NEW.location_id,nullif(current_setting('app.user_id',true),'')::uuid,TG_ARGV[0],TG_TABLE_NAME,NEW.id::text,to_jsonb(NEW)); RETURN NEW;
END $$;
CREATE TRIGGER opening_requested_audit AFTER INSERT ON inventory_opening_requests FOR EACH ROW EXECUTE FUNCTION inventory_pilot_record_audit('inventory.opening.requested');
CREATE FUNCTION inventory_operation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.actor_id::text IS DISTINCT FROM current_setting('app.user_id',true) OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:catalog:manage') THEN RAISE EXCEPTION 'operational catalog permission required' USING ERRCODE='42501'; END IF;
 NEW.created_at:=clock_timestamp(); RETURN NEW;
END $$;
CREATE TRIGGER operation_guard BEFORE INSERT ON inventory_operations FOR EACH ROW EXECUTE FUNCTION inventory_operation_guard();
CREATE TRIGGER operation_audit AFTER INSERT ON inventory_operations FOR EACH ROW EXECUTE FUNCTION inventory_pilot_record_audit('inventory.operation.recorded');
CREATE FUNCTION inventory_evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s inventory_count_sessions;
BEGIN
 IF TG_OP='DELETE' OR TG_OP='TRUNCATE' THEN RAISE EXCEPTION 'evidence metadata must retain a tombstone'; END IF;
 IF TG_OP='INSERT' THEN
  SELECT * INTO s FROM inventory_count_sessions WHERE id=NEW.session_id FOR UPDATE;
  IF s.id IS NULL OR s.status<>'draft' OR s.assigned_to::text IS DISTINCT FROM current_setting('app.user_id',true) OR NEW.uploaded_by<>s.assigned_to OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:count') THEN RAISE EXCEPTION 'only assigned counter may upload to a draft' USING ERRCODE='42501'; END IF;
  NEW.uploaded_at:=clock_timestamp();
  IF NEW.retain_until<=NEW.uploaded_at OR NEW.retain_until>NEW.uploaded_at+interval '365 days' OR NEW.deleted_at IS NOT NULL OR NEW.legal_hold THEN RAISE EXCEPTION 'invalid initial evidence retention'; END IF;
 ELSE
  IF (NEW.id,NEW.organization_id,NEW.location_id,NEW.session_id,NEW.object_key,NEW.sha256,NEW.byte_size,NEW.mime_type,NEW.uploaded_by,NEW.uploaded_at,NEW.scanner_status)
    IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.location_id,OLD.session_id,OLD.object_key,OLD.sha256,OLD.byte_size,OLD.mime_type,OLD.uploaded_by,OLD.uploaded_at,OLD.scanner_status)
    OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve') OR OLD.deleted_at IS NOT NULL THEN RAISE EXCEPTION 'immutable evidence identity or deleted object' USING ERRCODE='42501'; END IF;
  IF NEW.retain_until<OLD.retain_until OR NEW.retain_until>clock_timestamp()+interval '365 days' THEN RAISE EXCEPTION 'retention can only be extended up to 365 days'; END IF;
  IF NEW.deleted_at IS NOT NULL THEN
   IF OLD.legal_hold OR NEW.legal_hold OR OLD.retain_until>clock_timestamp() THEN RAISE EXCEPTION 'retention or legal hold prevents deletion'; END IF;
   NEW.deleted_at:=clock_timestamp();
  END IF;
 END IF;
 IF NEW.object_key IS DISTINCT FROM NEW.organization_id::text||'/'||NEW.location_id::text||'/'||NEW.id::text||'.jpg' THEN RAISE EXCEPTION 'evidence object key must match its scope and identity'; END IF;
 NEW.control_reason:=trim(NEW.control_reason); RETURN NEW;
END $$;
CREATE TRIGGER evidence_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_evidence FOR EACH ROW EXECUTE FUNCTION inventory_evidence_guard();
CREATE TRIGGER evidence_no_truncate BEFORE TRUNCATE ON inventory_evidence FOR EACH STATEMENT EXECUTE FUNCTION inventory_evidence_guard();
CREATE TRIGGER evidence_audit AFTER INSERT OR UPDATE ON inventory_evidence FOR EACH ROW EXECUTE FUNCTION inventory_pilot_record_audit('inventory.evidence.controlled');
CREATE FUNCTION inventory_photo_reference_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.photo_object_key IS NOT NULL AND NOT EXISTS(SELECT 1 FROM inventory_evidence e WHERE e.organization_id=NEW.organization_id AND e.location_id=NEW.location_id AND e.session_id=NEW.session_id AND e.object_key=NEW.photo_object_key AND e.deleted_at IS NULL AND (e.legal_hold OR e.retain_until>clock_timestamp())) THEN RAISE EXCEPTION 'count photo must be live protected evidence from this session'; END IF; RETURN NEW;
END $$;
CREATE TRIGGER count_photo_reference BEFORE INSERT OR UPDATE ON inventory_count_lines FOR EACH ROW WHEN(NEW.photo_object_key IS NOT NULL) EXECUTE FUNCTION inventory_photo_reference_guard();
"""

# Snapshot function is frozen in this migration, with one additive check for an
# explicit, independently approved ZERO baseline (no zero-valued ledger entry).
SNAPSHOT_FUNCTION = r"""
    CREATE OR REPLACE FUNCTION inventory_count_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE l record; factor numeric; normalized numeric; expected numeric; baseline boolean; variance numeric; percentage numeric; flag text; explanation text;
    BEGIN
      IF TG_OP = 'INSERT' THEN
        IF NEW.created_by::text IS DISTINCT FROM current_setting('app.user_id', true) OR NEW.status <> 'draft' OR NEW.version <> 1
           OR NEW.submitted_at IS NOT NULL OR NEW.cutoff_at IS NOT NULL THEN
          RAISE EXCEPTION 'sessions must start as an authenticated version-one draft';
        END IF;
      ELSE
        IF (NEW.id, NEW.organization_id, NEW.location_id, NEW.created_by, NEW.created_at, NEW.idempotency_key)
           IS DISTINCT FROM (OLD.id, OLD.organization_id, OLD.location_id, OLD.created_by, OLD.created_at, OLD.idempotency_key)
           OR NEW.version <> OLD.version + 1 THEN RAISE EXCEPTION 'immutable session identity or stale version'; END IF;
        IF OLD.status = 'draft' AND NEW.status IN ('draft', 'submitted') THEN
          IF NEW.assigned_to IS DISTINCT FROM OLD.assigned_to OR NEW.storage_zone_id IS DISTINCT FROM OLD.storage_zone_id
             OR NEW.quantity_threshold <> OLD.quantity_threshold OR NEW.percentage_threshold <> OLD.percentage_threshold THEN
            IF NOT inventory_reviewer(NEW.organization_id, NEW.location_id) THEN RAISE EXCEPTION 'assignment and thresholds require manager access'; END IF;
          END IF;
        ELSIF OLD.status = 'submitted' AND NEW.status = 'under_review' AND inventory_reviewer(NEW.organization_id, NEW.location_id) THEN
          IF (NEW.assigned_to, NEW.storage_zone_id, NEW.quantity_threshold, NEW.percentage_threshold, NEW.cutoff_at, NEW.submitted_at)
             IS DISTINCT FROM (OLD.assigned_to, OLD.storage_zone_id, OLD.quantity_threshold, OLD.percentage_threshold, OLD.cutoff_at, OLD.submitted_at) THEN
            RAISE EXCEPTION 'submitted session is frozen';
          END IF;
          RETURN NEW;
        ELSE RAISE EXCEPTION 'invalid count state transition'; END IF;
      END IF;
      IF NEW.assigned_to::text IS DISTINCT FROM current_setting('app.user_id', true) AND NOT inventory_reviewer(NEW.organization_id, NEW.location_id) THEN
        RAISE EXCEPTION 'only managers can assign another counter';
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM user_location_assignments a JOIN role_permissions rp ON rp.role_id = a.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE a.user_id = NEW.assigned_to AND a.organization_id = NEW.organization_id AND a.location_id = NEW.location_id
          AND a.active AND p.key = 'inventory:count'
      ) THEN RAISE EXCEPTION 'counter must be an active employee assigned to this location'; END IF;
      IF NEW.status = 'draft' THEN
        IF NEW.submitted_at IS NOT NULL OR NEW.cutoff_at IS NOT NULL THEN RAISE EXCEPTION 'draft cannot have a cutoff'; END IF;
        IF NEW.storage_zone_id IS NOT NULL AND EXISTS (
          SELECT 1 FROM inventory_count_lines c JOIN inventory_location_items li ON li.inventory_item_id = c.inventory_item_id
            AND li.organization_id = c.organization_id AND li.location_id = c.location_id
          WHERE c.session_id = NEW.id AND li.storage_zone_id IS DISTINCT FROM NEW.storage_zone_id
        ) THEN RAISE EXCEPTION 'existing count lines are outside the selected zone'; END IF;
        RETURN NEW;
      END IF;
      IF NEW.assigned_to::text IS DISTINCT FROM current_setting('app.user_id', true) OR NOT inventory_can(NEW.organization_id, NEW.location_id, 'inventory:count') THEN
        RAISE EXCEPTION 'only the assigned counter can submit';
      END IF;
      IF NOT EXISTS (SELECT 1 FROM inventory_count_lines WHERE session_id = NEW.id) THEN RAISE EXCEPTION 'cannot submit an empty count'; END IF;
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.organization_id::text || ':' || NEW.location_id::text, 0));
      NEW.cutoff_at := clock_timestamp(); NEW.submitted_at := NEW.cutoff_at;
      FOR l IN SELECT c.*, i.sku, i.name, i.base_unit_code, u.dimension, u.factor_to_base, b.dimension AS stock_dimension, b.factor_to_base AS stock_factor
        FROM inventory_count_lines c JOIN inventory_items i ON i.id = c.inventory_item_id AND i.organization_id = c.organization_id
        JOIN inventory_units u ON u.code = c.unit_code JOIN inventory_units b ON b.code = i.base_unit_code WHERE c.session_id = NEW.id
      LOOP
        SELECT factor_to_stock_unit INTO factor FROM inventory_item_unit_conversions WHERE organization_id = NEW.organization_id
          AND location_id = NEW.location_id AND inventory_item_id = l.inventory_item_id AND unit_code = l.unit_code;
        IF factor IS NULL AND l.dimension = l.stock_dimension THEN factor := l.factor_to_base / l.stock_factor; END IF;
        IF factor IS NULL THEN RAISE EXCEPTION 'unit conversion is no longer configured'; END IF;
        normalized := round(l.quantity * factor, 6);
        SELECT coalesce(sum(quantity_delta), 0), coalesce(bool_or(movement_type IN ('opening', 'count_adjustment')), false)
          INTO expected, baseline FROM stock_movements WHERE organization_id = NEW.organization_id AND location_id = NEW.location_id
          AND inventory_item_id = l.inventory_item_id AND created_at <= NEW.cutoff_at;
        baseline := baseline OR EXISTS(SELECT 1 FROM inventory_opening_requests r JOIN inventory_opening_decisions d ON d.request_id=r.id
          WHERE r.organization_id=NEW.organization_id AND r.location_id=NEW.location_id AND r.inventory_item_id=l.inventory_item_id
            AND d.action='approved' AND d.created_at<=NEW.cutoff_at);
        IF NOT baseline THEN
          expected := NULL; variance := NULL; percentage := NULL; flag := 'baseline_required';
          explanation := 'No opening balance or approved count baseline exists at the cutoff. Expected stock is unknown.';
        ELSE
          variance := normalized - expected;
          percentage := CASE WHEN expected = 0 THEN NULL ELSE round(variance / abs(expected) * 100, 6) END;
          flag := CASE WHEN abs(variance) > NEW.quantity_threshold OR (percentage IS NOT NULL AND abs(percentage) > NEW.percentage_threshold)
            THEN 'above_threshold' ELSE 'within_threshold' END;
          explanation := 'Expected stock is the sum of committed ledger movements at the cutoff. Variance equals confirmed count minus expected stock; no adjustment has been posted.';
          IF expected = 0 THEN explanation := explanation || ' Percentage is undefined for a zero expected balance.'; END IF;
        END IF;
        UPDATE inventory_count_lines SET snapshot = jsonb_build_object(
          'sku', l.sku, 'name', l.name, 'quantity', l.quantity::text, 'unit_code', l.unit_code,
          'base_unit_code', l.base_unit_code, 'factor_to_stock_unit', factor::text, 'base_quantity', normalized::text,
          'expected_quantity', expected::text, 'variance_quantity', variance::text, 'variance_percentage', percentage::text,
          'status', flag, 'explanation', explanation, 'counted_by', l.counted_by::text,
          'note', l.note, 'photo_object_key', l.photo_object_key, 'cutoff_at', NEW.cutoff_at)
          WHERE id = l.id;
      END LOOP;
      RETURN NEW;
    END $$;

"""


def downgrade():
    raise RuntimeError("0005_inventory_pilot is forward-only; retain evidence and audited inventory history")
