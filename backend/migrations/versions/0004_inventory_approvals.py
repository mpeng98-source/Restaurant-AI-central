"""Four-eyes count decisions, atomic adjustments and audited reversals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "0004_inventory_approvals"
down_revision = "0003_inventory_counting"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_count_decisions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("request_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("reviewed_lines", pg.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("decided_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_log_id", pg.UUID(as_uuid=True), sa.ForeignKey("audit_logs.id", deferrable=True, initially="DEFERRED"), nullable=False),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_count_decision_scope_id"),
        sa.UniqueConstraint("organization_id", "location_id", "session_id", name="uq_count_decision_session"),
        sa.UniqueConstraint("organization_id", "location_id", "idempotency_key", name="uq_count_decision_key"),
        sa.ForeignKeyConstraint(["organization_id", "location_id", "session_id"], ["inventory_count_sessions.organization_id", "inventory_count_sessions.location_id", "inventory_count_sessions.id"], name="fk_count_decision_session_scope"),
        sa.CheckConstraint("action IN ('approved', 'rejected') AND request_version > 0 AND length(trim(reason)) BETWEEN 1 AND 2000 AND length(trim(idempotency_key)) BETWEEN 1 AND 128", name="ck_count_decision_input"),
    )
    op.create_table(
        "inventory_movement_reversals",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("original_movement_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expected_balance", sa.Numeric(24, 6), nullable=False),
        sa.Column("quantity_delta", sa.Numeric(24, 6), nullable=False),
        sa.Column("balance_before", sa.Numeric(24, 6), nullable=False),
        sa.Column("balance_after", sa.Numeric(24, 6), nullable=False),
        sa.Column("requested_by", pg.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_log_id", pg.UUID(as_uuid=True), sa.ForeignKey("audit_logs.id", deferrable=True, initially="DEFERRED"), nullable=False),
        sa.UniqueConstraint("organization_id", "location_id", "id", name="uq_count_reversal_scope_id"),
        sa.UniqueConstraint("organization_id", "location_id", "original_movement_id", name="uq_count_reversal_original"),
        sa.UniqueConstraint("organization_id", "location_id", "idempotency_key", name="uq_count_reversal_key"),
        sa.ForeignKeyConstraint(["organization_id", "location_id", "original_movement_id"], ["stock_movements.organization_id", "stock_movements.location_id", "stock_movements.id"], name="fk_count_reversal_movement_scope"),
        sa.CheckConstraint("length(trim(reason)) BETWEEN 1 AND 2000 AND length(trim(idempotency_key)) BETWEEN 1 AND 128", name="ck_count_reversal_input"),
    )
    op.add_column("inventory_adjustment_approvals", sa.Column("decision_id", pg.UUID(as_uuid=True)))
    op.create_foreign_key("fk_line_approval_decision_scope", "inventory_adjustment_approvals", "inventory_count_decisions", ["organization_id", "location_id", "decision_id"], ["organization_id", "location_id", "id"])
    for name, kind in (("decision_id", pg.UUID(as_uuid=True)), ("count_line_id", pg.UUID(as_uuid=True)), ("reversal_record_id", pg.UUID(as_uuid=True)), ("reason", sa.Text()), ("balance_before", sa.Numeric(24, 6)), ("balance_after", sa.Numeric(24, 6)), ("count_cutoff_at", sa.DateTime(timezone=True)), ("audit_log_id", pg.UUID(as_uuid=True))):
        op.add_column("stock_movements", sa.Column(name, kind))
    for name, target, target_id in (("decision_id", "inventory_count_decisions", "id"), ("count_line_id", "inventory_count_lines", "id"), ("reversal_record_id", "inventory_movement_reversals", "id")):
        op.create_foreign_key(f"fk_stock_{name}_scope", "stock_movements", target, ["organization_id", "location_id", name], ["organization_id", "location_id", target_id])
    op.create_foreign_key("fk_stock_audit", "stock_movements", "audit_logs", ["audit_log_id"], ["id"])
    op.execute("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name='Corporate Owner' AND p.key='inventory:approve' ON CONFLICT DO NOTHING")
    scope = "organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
    for table in ("inventory_count_decisions", "inventory_movement_reversals"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        read = "inventory_reviewer(organization_id,location_id)"
        if table == "inventory_count_decisions":
            read += " OR EXISTS (SELECT 1 FROM inventory_count_sessions s WHERE s.id=session_id AND s.assigned_to::text=current_setting('app.user_id',true))"
        op.execute(f"CREATE POLICY decision_read ON {table} FOR SELECT USING ({scope} AND ({read}))")
        op.execute(f"CREATE POLICY decision_insert ON {table} FOR INSERT WITH CHECK ({scope} AND inventory_can(organization_id,location_id,'inventory:approve'))")
        op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {table} FROM chubby_app")
    op.execute("DROP POLICY inventory_location_read_scope ON inventory_adjustment_approvals")
    op.execute("DROP POLICY inventory_location_write_scope ON inventory_adjustment_approvals")
    op.execute(f"CREATE POLICY line_approval_read ON inventory_adjustment_approvals FOR SELECT USING ({scope} AND inventory_reviewer(organization_id,location_id))")
    op.execute(f"CREATE POLICY line_approval_insert ON inventory_adjustment_approvals FOR INSERT WITH CHECK ({scope} AND inventory_can(organization_id,location_id,'inventory:approve'))")
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON inventory_adjustment_approvals FROM chubby_app")
    op.execute(sa.text(SQL))


SQL = r"""
CREATE FUNCTION inventory_report_counter_ids(report_id uuid) RETURNS SETOF uuid LANGUAGE sql STABLE AS $$
  SELECT assigned_to FROM inventory_count_sessions WHERE id=report_id
  UNION SELECT counted_by FROM inventory_count_lines WHERE session_id=report_id
  UNION SELECT a.user_id FROM audit_logs a JOIN inventory_count_sessions s ON a.entity_id=s.id::text
    AND a.organization_id=s.organization_id AND a.location_id=s.location_id
    WHERE s.id=report_id AND a.entity_type='inventory_count_session' AND a.action='inventory.count.line_saved' AND a.user_id IS NOT NULL
$$;
CREATE FUNCTION inventory_report_digest(report_id uuid) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT encode(sha256(convert_to(jsonb_build_object('session',s.id,'organization',s.organization_id,'location',s.location_id,
    'assigned_to',s.assigned_to,'cutoff',s.cutoff_at,'quantity_threshold',s.quantity_threshold,'percentage_threshold',s.percentage_threshold,
    'counters',(SELECT jsonb_agg(c.counter ORDER BY c.counter) FROM inventory_report_counter_ids(s.id) AS c(counter)),
    'lines',(SELECT jsonb_agg(jsonb_build_object('id',l.id,'item',l.inventory_item_id,'counter',l.counted_by,'snapshot',l.snapshot) ORDER BY l.id)
      FROM inventory_count_lines l WHERE l.session_id=s.id))::text,'UTF8')),'hex')
  FROM inventory_count_sessions s WHERE s.id=report_id AND s.status <> 'draft'
$$;
CREATE FUNCTION inventory_review_choices(choices jsonb) RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
  SELECT jsonb_agg(jsonb_build_object('line_id',v->>'line_id','verdict',v->>'verdict') ORDER BY v->>'line_id') FROM jsonb_array_elements(choices) v
$$;
CREATE FUNCTION inventory_decision_request_hash(v integer, digest text, action text, reason text, choices jsonb, actor uuid)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT encode(sha256(convert_to(jsonb_build_object('version',v,'snapshot_hash',digest,'action',action,'reason',trim(reason),
    'lines',inventory_review_choices(choices),'actor',actor)::text,'UTF8')),'hex')
$$;
CREATE FUNCTION prevent_inventory_decision_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'inventory decisions, approvals and reversals are append-only'; END $$;
CREATE TRIGGER count_decisions_immutable BEFORE UPDATE OR DELETE ON inventory_count_decisions FOR EACH ROW EXECUTE FUNCTION prevent_inventory_decision_mutation();
CREATE TRIGGER count_decisions_no_truncate BEFORE TRUNCATE ON inventory_count_decisions FOR EACH STATEMENT EXECUTE FUNCTION prevent_inventory_decision_mutation();
CREATE TRIGGER count_reversals_immutable BEFORE UPDATE OR DELETE ON inventory_movement_reversals FOR EACH ROW EXECUTE FUNCTION prevent_inventory_decision_mutation();
CREATE TRIGGER count_reversals_no_truncate BEFORE TRUNCATE ON inventory_movement_reversals FOR EACH STATEMENT EXECUTE FUNCTION prevent_inventory_decision_mutation();
CREATE TRIGGER line_approvals_immutable BEFORE UPDATE OR DELETE ON inventory_adjustment_approvals FOR EACH ROW EXECUTE FUNCTION prevent_inventory_decision_mutation();
CREATE TRIGGER line_approvals_no_truncate BEFORE TRUNCATE ON inventory_adjustment_approvals FOR EACH STATEMENT EXECUTE FUNCTION prevent_inventory_decision_mutation();

CREATE FUNCTION inventory_decision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s inventory_count_sessions; total integer; n integer; l record; balance numeric;
BEGIN
  SELECT * INTO s FROM inventory_count_sessions WHERE id=NEW.session_id AND organization_id=NEW.organization_id AND location_id=NEW.location_id FOR UPDATE;
  IF s.id IS NULL THEN RAISE EXCEPTION 'count report not found' USING ERRCODE='P0002'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.organization_id::text || ':' || NEW.location_id::text,0));
  IF NEW.decided_by::text IS DISTINCT FROM current_setting('app.user_id',true) OR NOT inventory_can(s.organization_id,s.location_id,'inventory:approve') THEN
    RAISE EXCEPTION 'approval permission required' USING ERRCODE='42501'; END IF;
  IF EXISTS(SELECT 1 FROM inventory_report_counter_ids(s.id) AS c(counter) WHERE c.counter=NEW.decided_by) THEN
    RAISE EXCEPTION 'four-eyes control: counters cannot decide their own reports' USING ERRCODE='42501'; END IF;
  IF s.status <> 'under_review' OR s.version <> NEW.request_version OR NEW.snapshot_hash IS DISTINCT FROM inventory_report_digest(s.id) THEN
    RAISE EXCEPTION 'stale report state, version or reviewed snapshot'; END IF;
  NEW.reason:=trim(NEW.reason);
  IF NEW.action NOT IN ('approved','rejected') OR length(NEW.reason) NOT BETWEEN 1 AND 2000 OR jsonb_typeof(NEW.reviewed_lines) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid decision input'; END IF;
  SELECT count(*) INTO total FROM inventory_count_lines WHERE session_id=s.id;
  SELECT count(DISTINCT v->>'line_id') INTO n FROM jsonb_array_elements(NEW.reviewed_lines) v;
  IF total=0 OR n<>total OR jsonb_array_length(NEW.reviewed_lines)<>total OR EXISTS(
    SELECT 1 FROM jsonb_array_elements(NEW.reviewed_lines) v WHERE v->>'verdict' NOT IN ('accepted','disputed') OR v->>'verdict' IS NULL
      OR NOT EXISTS(SELECT 1 FROM inventory_count_lines l0 WHERE l0.session_id=s.id AND l0.id::text=v->>'line_id')
  ) THEN RAISE EXCEPTION 'every frozen line must be reviewed exactly once'; END IF;
  NEW.reviewed_lines:=inventory_review_choices(NEW.reviewed_lines);
  IF NEW.action='approved' AND EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.reviewed_lines) v WHERE v->>'verdict'<>'accepted') THEN
    RAISE EXCEPTION 'approval is atomic: all lines must be accepted'; END IF;
  IF NEW.action='rejected' AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(NEW.reviewed_lines) v WHERE v->>'verdict'='disputed') THEN
    RAISE EXCEPTION 'rejection requires at least one explicitly disputed line'; END IF;
  IF NEW.action='approved' AND EXISTS(
    SELECT 1 FROM inventory_report_counter_ids(s.id) AS counters(counter)
    WHERE NOT EXISTS(SELECT 1 FROM user_location_assignments a JOIN role_permissions rp ON rp.role_id=a.role_id JOIN permissions p ON p.id=rp.permission_id
      WHERE a.user_id=counters.counter AND a.organization_id=s.organization_id AND a.location_id=s.location_id AND a.active AND p.key='inventory:count')
  ) THEN RAISE EXCEPTION 'counter assignment changed; a fresh count is required'; END IF;
  IF NEW.action='approved' THEN
    FOR l IN SELECT * FROM inventory_count_lines WHERE session_id=s.id LOOP
      IF l.snapshot IS NULL OR l.snapshot->>'status'='baseline_required' OR l.snapshot->>'expected_quantity' IS NULL THEN
        RAISE EXCEPTION 'baseline required; initialize stock manually and perform a fresh count'; END IF;
      IF EXISTS(SELECT 1 FROM stock_movements WHERE organization_id=s.organization_id AND location_id=s.location_id
        AND inventory_item_id=l.inventory_item_id AND created_at>s.cutoff_at) THEN
        RAISE EXCEPTION 'ledger changed after submission; recount or reconcile in a new session'; END IF;
      SELECT coalesce(sum(quantity_delta),0) INTO balance FROM stock_movements WHERE organization_id=s.organization_id AND location_id=s.location_id AND inventory_item_id=l.inventory_item_id;
      IF balance IS DISTINCT FROM (l.snapshot->>'expected_quantity')::numeric THEN RAISE EXCEPTION 'ledger balance no longer matches the reviewed snapshot'; END IF;
    END LOOP;
  END IF;
  NEW.request_hash:=inventory_decision_request_hash(NEW.request_version,NEW.snapshot_hash,NEW.action,NEW.reason,NEW.reviewed_lines,NEW.decided_by);
  NEW.decided_at:=clock_timestamp(); NEW.audit_log_id:=gen_random_uuid();
  RETURN NEW;
END $$;
CREATE TRIGGER count_decision_validate BEFORE INSERT ON inventory_count_decisions FOR EACH ROW EXECUTE FUNCTION inventory_decision_guard();

CREATE FUNCTION inventory_line_approval_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF pg_trigger_depth()<2 OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve') OR NOT EXISTS(
    SELECT 1 FROM inventory_count_decisions d JOIN inventory_count_lines l ON l.session_id=d.session_id
      WHERE d.id=NEW.decision_id AND d.organization_id=NEW.organization_id AND d.location_id=NEW.location_id AND l.id=NEW.count_line_id
      AND d.action=NEW.status AND d.decided_by=NEW.decided_by AND d.reason=NEW.reason AND d.decided_at=NEW.decided_at
  ) THEN RAISE EXCEPTION 'line approvals are created only by an authorized report decision' USING ERRCODE='42501'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER line_approval_validate BEFORE INSERT ON inventory_adjustment_approvals FOR EACH ROW EXECUTE FUNCTION inventory_line_approval_guard();

CREATE FUNCTION inventory_terminal_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' THEN RAISE EXCEPTION 'a terminal report must originate from a draft'; END IF;
  IF pg_trigger_depth()<2 OR OLD.status<>'under_review' OR NEW.version<>OLD.version+1 OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve')
     OR (NEW.id,NEW.organization_id,NEW.location_id,NEW.created_by,NEW.created_at,NEW.idempotency_key,NEW.assigned_to,NEW.storage_zone_id,NEW.quantity_threshold,NEW.percentage_threshold,NEW.submitted_at,NEW.cutoff_at)
       IS DISTINCT FROM (OLD.id,OLD.organization_id,OLD.location_id,OLD.created_by,OLD.created_at,OLD.idempotency_key,OLD.assigned_to,OLD.storage_zone_id,OLD.quantity_threshold,OLD.percentage_threshold,OLD.submitted_at,OLD.cutoff_at)
     OR NOT EXISTS(SELECT 1 FROM inventory_count_decisions d WHERE d.session_id=NEW.id AND d.action=NEW.status AND d.request_version=OLD.version AND d.decided_by::text=current_setting('app.user_id',true)) THEN
    RAISE EXCEPTION 'terminal transitions require an immutable report decision'; END IF;
  RETURN NEW;
END $$;
DROP TRIGGER inventory_count_session_guard ON inventory_count_sessions;
CREATE TRIGGER inventory_count_session_guard BEFORE INSERT OR UPDATE ON inventory_count_sessions FOR EACH ROW
  WHEN (NEW.status NOT IN ('approved','rejected')) EXECUTE FUNCTION inventory_count_session_guard();
CREATE TRIGGER inventory_terminal_session_guard BEFORE INSERT OR UPDATE ON inventory_count_sessions FOR EACH ROW
  WHEN (NEW.status IN ('approved','rejected')) EXECUTE FUNCTION inventory_terminal_session_guard();

CREATE FUNCTION inventory_post_count_decision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE l record; approval uuid; s inventory_count_sessions; delta numeric; before_balance numeric; after_balance numeric;
BEGIN
  SELECT * INTO s FROM inventory_count_sessions WHERE id=NEW.session_id;
  INSERT INTO audit_logs(id,organization_id,location_id,user_id,action,entity_type,entity_id,metadata)
    VALUES(NEW.audit_log_id,NEW.organization_id,NEW.location_id,NEW.decided_by,'inventory.count.'||NEW.action,'inventory_count_decision',NEW.id::text,
      jsonb_build_object('session_id',s.id,'snapshot_hash',NEW.snapshot_hash,'cutoff',s.cutoff_at,'reason',NEW.reason,'reviewed_lines',NEW.reviewed_lines));
  FOR l IN SELECT * FROM inventory_count_lines WHERE session_id=s.id ORDER BY id LOOP
    approval:=gen_random_uuid();
    INSERT INTO inventory_adjustment_approvals(id,organization_id,location_id,count_line_id,status,decided_by,decided_at,reason,decision_id)
      VALUES(approval,s.organization_id,s.location_id,l.id,NEW.action,NEW.decided_by,NEW.decided_at,NEW.reason,NEW.id);
    IF NEW.action='approved' THEN
      delta:=(l.snapshot->>'variance_quantity')::numeric;
      before_balance:=(l.snapshot->>'expected_quantity')::numeric;
      after_balance:=(l.snapshot->>'base_quantity')::numeric;
      IF delta<>0 THEN
        INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,
          source_type,source_id,approval_id,actor_id,approver_id,decision_id,count_line_id,reason,balance_before,balance_after,count_cutoff_at,audit_log_id)
        VALUES(gen_random_uuid(),s.organization_id,s.location_id,l.inventory_item_id,'count_adjustment',delta,l.snapshot->>'base_unit_code','count:'||approval::text,
          'inventory_count_session',s.id::text,approval,NEW.decided_by,NEW.decided_by,NEW.id,l.id,NEW.reason,before_balance,after_balance,s.cutoff_at,NEW.audit_log_id);
      END IF;
    END IF;
  END LOOP;
  UPDATE inventory_count_sessions SET status=NEW.action,version=version+1 WHERE id=s.id;
  RETURN NEW;
END $$;
CREATE TRIGGER count_decision_post AFTER INSERT ON inventory_count_decisions FOR EACH ROW EXECUTE FUNCTION inventory_post_count_decision();

CREATE FUNCTION inventory_decide_count(org uuid,loc uuid,report_id uuid,expected_version integer,digest text,decision text,reason_text text,key_text text,choices jsonb)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE s inventory_count_sessions; previous inventory_count_decisions; actor uuid; result uuid; fingerprint text;
BEGIN
  IF NOT inventory_can(org,loc,'inventory:approve') THEN RAISE EXCEPTION 'approval permission required' USING ERRCODE='42501'; END IF;
  actor:=nullif(current_setting('app.user_id',true),'')::uuid;
  SELECT * INTO s FROM inventory_count_sessions WHERE id=report_id AND organization_id=org AND location_id=loc FOR UPDATE;
  IF s.id IS NULL THEN RAISE EXCEPTION 'count report not found' USING ERRCODE='P0002'; END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(org::text||':'||loc::text,0));
  fingerprint:=inventory_decision_request_hash(expected_version,digest,decision,reason_text,choices,actor);
  SELECT * INTO previous FROM inventory_count_decisions WHERE organization_id=org AND location_id=loc AND (session_id=report_id OR idempotency_key=key_text);
  IF previous.id IS NOT NULL THEN
    IF previous.session_id=report_id AND previous.idempotency_key=key_text AND previous.request_hash=fingerprint THEN RETURN previous.id; END IF;
    RAISE EXCEPTION 'report already decided or idempotency key reused with different input';
  END IF;
  result:=gen_random_uuid();
  INSERT INTO inventory_count_decisions(id,organization_id,location_id,session_id,action,request_version,snapshot_hash,reviewed_lines,reason,idempotency_key,request_hash,decided_by,decided_at,audit_log_id)
    VALUES(result,org,loc,report_id,decision,expected_version,digest,choices,reason_text,key_text,fingerprint,actor,clock_timestamp(),gen_random_uuid());
  RETURN result;
END $$;

CREATE FUNCTION inventory_reversal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original stock_movements; d inventory_count_decisions; s inventory_count_sessions; balance numeric;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtextextended(NEW.organization_id::text||':'||NEW.location_id::text,0));
  SELECT * INTO original FROM stock_movements WHERE id=NEW.original_movement_id AND organization_id=NEW.organization_id AND location_id=NEW.location_id;
  IF original.id IS NULL OR original.movement_type<>'count_adjustment' THEN RAISE EXCEPTION 'count adjustment not found' USING ERRCODE='P0002'; END IF;
  IF NEW.requested_by::text IS DISTINCT FROM current_setting('app.user_id',true) OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve') THEN
    RAISE EXCEPTION 'reversal requires location approval permission' USING ERRCODE='42501'; END IF;
  SELECT * INTO d FROM inventory_count_decisions WHERE id=original.decision_id;
  SELECT * INTO s FROM inventory_count_sessions WHERE id=d.session_id;
  IF d.id IS NULL OR EXISTS(SELECT 1 FROM inventory_report_counter_ids(s.id) AS c(counter) WHERE c.counter=NEW.requested_by) THEN
    RAISE EXCEPTION 'four-eyes control: a counter cannot reverse their own report adjustment' USING ERRCODE='42501'; END IF;
  SELECT coalesce(sum(quantity_delta),0) INTO balance FROM stock_movements WHERE organization_id=NEW.organization_id AND location_id=NEW.location_id AND inventory_item_id=original.inventory_item_id;
  IF NEW.expected_balance IS DISTINCT FROM balance THEN RAISE EXCEPTION 'ledger changed since reversal preview; review again'; END IF;
  NEW.reason:=trim(NEW.reason); NEW.quantity_delta:=-original.quantity_delta; NEW.balance_before:=balance; NEW.balance_after:=balance-original.quantity_delta;
  NEW.created_at:=clock_timestamp(); NEW.audit_log_id:=gen_random_uuid();
  RETURN NEW;
END $$;
CREATE TRIGGER count_reversal_validate BEFORE INSERT ON inventory_movement_reversals FOR EACH ROW EXECUTE FUNCTION inventory_reversal_guard();
CREATE FUNCTION inventory_post_count_reversal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original stock_movements;
BEGIN
  SELECT * INTO original FROM stock_movements WHERE id=NEW.original_movement_id;
  INSERT INTO audit_logs(id,organization_id,location_id,user_id,action,entity_type,entity_id,metadata)
    VALUES(NEW.audit_log_id,NEW.organization_id,NEW.location_id,NEW.requested_by,'inventory.adjustment.reversed','inventory_movement_reversal',NEW.id::text,
      jsonb_build_object('original_movement_id',original.id,'decision_id',original.decision_id,'reason',NEW.reason,'before',NEW.balance_before::text,'after',NEW.balance_after::text,'delta',NEW.quantity_delta::text));
  INSERT INTO stock_movements(id,organization_id,location_id,inventory_item_id,movement_type,quantity_delta,unit_code,idempotency_key,source_type,source_id,
    reverses_movement_id,actor_id,approver_id,decision_id,count_line_id,reversal_record_id,reason,balance_before,balance_after,count_cutoff_at,audit_log_id)
  VALUES(NEW.id,NEW.organization_id,NEW.location_id,original.inventory_item_id,'reversal',NEW.quantity_delta,original.unit_code,'reverse:'||NEW.id::text,'inventory_movement_reversal',NEW.id::text,
    original.id,NEW.requested_by,NEW.requested_by,original.decision_id,original.count_line_id,NEW.id,NEW.reason,NEW.balance_before,NEW.balance_after,original.count_cutoff_at,NEW.audit_log_id);
  RETURN NEW;
END $$;
CREATE TRIGGER count_reversal_post AFTER INSERT ON inventory_movement_reversals FOR EACH ROW EXECUTE FUNCTION inventory_post_count_reversal();
CREATE FUNCTION inventory_reverse_count_movement(org uuid,loc uuid,original_id uuid,key_text text,reason_text text,preview_balance numeric)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE previous inventory_movement_reversals; actor uuid; result uuid;
BEGIN
  IF NOT inventory_can(org,loc,'inventory:approve') THEN RAISE EXCEPTION 'reversal permission required' USING ERRCODE='42501'; END IF;
  actor:=nullif(current_setting('app.user_id',true),'')::uuid;
  PERFORM pg_advisory_xact_lock(hashtextextended(org::text||':'||loc::text,0));
  SELECT * INTO previous FROM inventory_movement_reversals WHERE organization_id=org AND location_id=loc AND (original_movement_id=original_id OR idempotency_key=key_text);
  IF previous.id IS NOT NULL THEN
    IF previous.original_movement_id=original_id AND previous.idempotency_key=key_text AND previous.requested_by=actor
       AND previous.reason=trim(reason_text) AND previous.expected_balance=preview_balance THEN RETURN previous.id; END IF;
    RAISE EXCEPTION 'adjustment already reversed or idempotency key reused';
  END IF;
  result:=gen_random_uuid();
  INSERT INTO inventory_movement_reversals(id,organization_id,location_id,original_movement_id,idempotency_key,reason,expected_balance,quantity_delta,balance_before,balance_after,requested_by,created_at,audit_log_id)
    VALUES(result,org,loc,original_id,key_text,reason_text,preview_balance,0,0,0,actor,clock_timestamp(),gen_random_uuid());
  RETURN result;
END $$;

CREATE OR REPLACE FUNCTION validate_stock_movement_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE expected_unit text; original stock_movements; d inventory_count_decisions; a inventory_adjustment_approvals; l inventory_count_lines; s inventory_count_sessions; r inventory_movement_reversals;
BEGIN
  IF NEW.actor_id::text IS DISTINCT FROM current_setting('app.user_id',true) THEN RAISE EXCEPTION 'stock movement actor must match the authenticated user context'; END IF;
  SELECT base_unit_code INTO expected_unit FROM inventory_items WHERE id=NEW.inventory_item_id AND organization_id=NEW.organization_id;
  IF expected_unit IS NULL OR NEW.unit_code IS DISTINCT FROM expected_unit THEN RAISE EXCEPTION 'stock movement quantity must use the inventory item base unit'; END IF;
  IF NEW.movement_type='count_adjustment' THEN
    SELECT * INTO d FROM inventory_count_decisions WHERE id=NEW.decision_id AND organization_id=NEW.organization_id AND location_id=NEW.location_id;
    SELECT * INTO a FROM inventory_adjustment_approvals WHERE id=NEW.approval_id AND decision_id=d.id AND count_line_id=NEW.count_line_id AND status='approved';
    SELECT * INTO l FROM inventory_count_lines WHERE id=NEW.count_line_id AND session_id=d.session_id;
    SELECT * INTO s FROM inventory_count_sessions WHERE id=d.session_id;
    IF pg_trigger_depth()<2 OR d.id IS NULL OR d.action<>'approved' OR a.id IS NULL OR l.id IS NULL OR l.inventory_item_id<>NEW.inventory_item_id
       OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve') OR NEW.actor_id<>d.decided_by OR NEW.approver_id IS DISTINCT FROM d.decided_by
       OR NEW.quantity_delta IS DISTINCT FROM (l.snapshot->>'variance_quantity')::numeric
       OR NEW.balance_before IS DISTINCT FROM (l.snapshot->>'expected_quantity')::numeric OR NEW.balance_after IS DISTINCT FROM (l.snapshot->>'base_quantity')::numeric
       OR NEW.audit_log_id IS DISTINCT FROM d.audit_log_id OR NEW.reason IS DISTINCT FROM d.reason OR NEW.count_cutoff_at IS DISTINCT FROM s.cutoff_at
       OR NEW.source_type IS DISTINCT FROM 'inventory_count_session' OR NEW.source_id IS DISTINCT FROM s.id::text THEN
      RAISE EXCEPTION 'count adjustments must be posted atomically by an approved immutable decision' USING ERRCODE='42501'; END IF;
  END IF;
  IF NEW.movement_type='reversal' THEN
    SELECT * INTO original FROM stock_movements WHERE id=NEW.reverses_movement_id AND organization_id=NEW.organization_id AND location_id=NEW.location_id;
    SELECT * INTO r FROM inventory_movement_reversals WHERE id=NEW.reversal_record_id AND original_movement_id=original.id;
    IF pg_trigger_depth()<2 OR original.id IS NULL OR r.id IS NULL OR original.inventory_item_id<>NEW.inventory_item_id OR NEW.quantity_delta IS DISTINCT FROM -original.quantity_delta
       OR NEW.id<>r.id OR NEW.actor_id<>r.requested_by OR NEW.approver_id IS DISTINCT FROM r.requested_by OR NEW.audit_log_id IS DISTINCT FROM r.audit_log_id
       OR NEW.reason IS DISTINCT FROM r.reason OR NEW.balance_before IS DISTINCT FROM r.balance_before OR NEW.balance_after IS DISTINCT FROM r.balance_after
       OR NEW.decision_id IS DISTINCT FROM original.decision_id OR NEW.count_line_id IS DISTINCT FROM original.count_line_id OR NEW.count_cutoff_at IS DISTINCT FROM original.count_cutoff_at
       OR NOT inventory_can(NEW.organization_id,NEW.location_id,'inventory:approve') THEN
      RAISE EXCEPTION 'reversals must exactly offset an authorized, audited adjustment' USING ERRCODE='42501'; END IF;
  END IF;
  RETURN NEW;
END $$;
"""


def downgrade():
    # Financial decisions must be exported and reconciled before removing this
    # schema. Refuse an automatic destructive rollback of approved history.
    raise RuntimeError("0004_inventory_approvals is forward-only; use an audited corrective migration")
