"""Assignment-aware inventory counting and immutable submission snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_inventory_counting"
down_revision = "0002_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inventory_count_sessions", sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE inventory_count_sessions SET assigned_to = created_by")
    op.alter_column("inventory_count_sessions", "assigned_to", nullable=False)
    op.create_foreign_key("fk_inventory_count_assignee", "inventory_count_sessions", "users", ["assigned_to"], ["id"])
    op.add_column("inventory_count_sessions", sa.Column("storage_zone_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_inventory_count_zone_scope", "inventory_count_sessions", "inventory_storage_zones", ["organization_id", "location_id", "storage_zone_id"], ["organization_id", "location_id", "id"])
    op.add_column("inventory_count_sessions", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("inventory_count_sessions", sa.Column("cutoff_at", sa.DateTime(timezone=True)))
    op.add_column("inventory_count_sessions", sa.Column("quantity_threshold", sa.Numeric(24, 6), nullable=False, server_default="0"))
    op.add_column("inventory_count_sessions", sa.Column("percentage_threshold", sa.Numeric(18, 6), nullable=False, server_default="5"))
    op.create_check_constraint("ck_inventory_count_version_thresholds", "inventory_count_sessions", "version > 0 AND quantity_threshold >= 0 AND percentage_threshold >= 0")
    op.drop_constraint("ck_inventory_count_sessions_status", "inventory_count_sessions", type_="check")
    op.create_check_constraint("ck_inventory_count_sessions_status", "inventory_count_sessions", "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected')")
    op.add_column("inventory_count_lines", sa.Column("counted_by", postgresql.UUID(as_uuid=True)))
    op.execute("UPDATE inventory_count_lines l SET counted_by = s.created_by FROM inventory_count_sessions s WHERE l.session_id = s.id")
    op.alter_column("inventory_count_lines", "counted_by", nullable=False)
    op.create_foreign_key("fk_inventory_count_line_counter", "inventory_count_lines", "users", ["counted_by"], ["id"])
    op.add_column("inventory_count_lines", sa.Column("snapshot", postgresql.JSONB()))
    op.execute(sa.text("""
    CREATE FUNCTION inventory_can(org uuid, loc uuid, permission_key text) RETURNS boolean
    LANGUAGE sql STABLE AS $$
      SELECT EXISTS (
        SELECT 1 FROM user_location_assignments a
        JOIN roles r ON r.id = a.role_id
        JOIN role_permissions rp ON rp.role_id = r.id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE a.user_id::text = current_setting('app.user_id', true)
          AND a.organization_id = org AND a.active
          AND (a.location_id = loc OR r.name = 'Corporate Owner') AND p.key = permission_key
      )
    $$;
    CREATE FUNCTION inventory_reviewer(org uuid, loc uuid) RETURNS boolean
    LANGUAGE sql STABLE AS $$
      SELECT inventory_can(org, loc, 'inventory:approve') OR inventory_can(org, loc, 'inventory:catalog:manage')
    $$;
    """))
    for table in ("inventory_count_sessions", "inventory_count_lines"):
        op.execute(f"DROP POLICY inventory_location_read_scope ON {table}")
        op.execute(f"DROP POLICY inventory_location_write_scope ON {table}")
    scope = "organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
    permitted = "(assigned_to::text = current_setting('app.user_id', true) AND inventory_can(organization_id, location_id, 'inventory:count') OR inventory_reviewer(organization_id, location_id))"
    op.execute(f"CREATE POLICY count_session_read ON inventory_count_sessions FOR SELECT USING ({scope} AND {permitted})")
    op.execute(f"CREATE POLICY count_session_insert ON inventory_count_sessions FOR INSERT WITH CHECK ({scope} AND {permitted})")
    op.execute(f"CREATE POLICY count_session_update ON inventory_count_sessions FOR UPDATE USING ({scope} AND {permitted}) WITH CHECK ({scope} AND {permitted})")
    line_parent = "EXISTS (SELECT 1 FROM inventory_count_sessions s WHERE s.id = session_id AND s.organization_id = inventory_count_lines.organization_id AND s.location_id = inventory_count_lines.location_id)"
    line_writer = "EXISTS (SELECT 1 FROM inventory_count_sessions s WHERE s.id = session_id AND s.organization_id = inventory_count_lines.organization_id AND s.location_id = inventory_count_lines.location_id AND s.status = 'draft' AND s.assigned_to::text = current_setting('app.user_id', true) AND inventory_can(s.organization_id, s.location_id, 'inventory:count'))"
    op.execute(f"CREATE POLICY count_line_read ON inventory_count_lines FOR SELECT USING ({scope} AND {line_parent})")
    op.execute(f"CREATE POLICY count_line_insert ON inventory_count_lines FOR INSERT WITH CHECK ({scope} AND {line_writer})")
    op.execute(f"CREATE POLICY count_line_update ON inventory_count_lines FOR UPDATE USING ({scope} AND {line_writer}) WITH CHECK ({scope} AND {line_writer})")
    op.execute(f"CREATE POLICY count_line_delete ON inventory_count_lines FOR DELETE USING ({scope} AND {line_writer})")
    op.execute("REVOKE DELETE, TRUNCATE ON inventory_count_sessions FROM chubby_app")
    op.execute("REVOKE TRUNCATE ON inventory_count_lines FROM chubby_app")
    op.execute(sa.text("""
    CREATE FUNCTION inventory_count_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE s inventory_count_sessions; i inventory_items; f numeric; unit_dimension text; stock_dimension text;
    BEGIN
      IF TG_OP = 'DELETE' THEN
        SELECT * INTO s FROM inventory_count_sessions WHERE id = OLD.session_id FOR UPDATE;
      ELSE
        SELECT * INTO s FROM inventory_count_sessions WHERE id = NEW.session_id FOR UPDATE;
      END IF;
      IF s.id IS NULL OR s.status <> 'draft' OR s.assigned_to::text IS DISTINCT FROM current_setting('app.user_id', true)
         OR NOT inventory_can(s.organization_id, s.location_id, 'inventory:count') THEN
        RAISE EXCEPTION 'only the assigned counter can edit a draft session';
      END IF;
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      IF TG_OP = 'UPDATE' AND (NEW.organization_id, NEW.location_id, NEW.session_id, NEW.inventory_item_id, NEW.id)
         IS DISTINCT FROM (OLD.organization_id, OLD.location_id, OLD.session_id, OLD.inventory_item_id, OLD.id) THEN
        RAISE EXCEPTION 'count line identity is immutable';
      END IF;
      IF pg_trigger_depth() = 1 AND (NEW.snapshot IS NOT NULL OR NEW.counted_by::text IS DISTINCT FROM current_setting('app.user_id', true)) THEN
        RAISE EXCEPTION 'snapshot is generated only by submission';
      END IF;
      SELECT i0.* INTO i FROM inventory_items i0 JOIN inventory_location_items li ON li.inventory_item_id = i0.id AND li.organization_id = i0.organization_id
        WHERE li.organization_id = s.organization_id AND li.location_id = s.location_id AND li.inventory_item_id = NEW.inventory_item_id
          AND li.active AND i0.active AND (s.storage_zone_id IS NULL OR li.storage_zone_id = s.storage_zone_id);
      IF i.id IS NULL THEN RAISE EXCEPTION 'item is not enabled in this session location and zone'; END IF;
      SELECT dimension INTO unit_dimension FROM inventory_units WHERE code = NEW.unit_code;
      SELECT dimension INTO stock_dimension FROM inventory_units WHERE code = i.base_unit_code;
      SELECT factor_to_stock_unit INTO f FROM inventory_item_unit_conversions
        WHERE organization_id = s.organization_id AND location_id = s.location_id AND inventory_item_id = i.id AND unit_code = NEW.unit_code;
      IF unit_dimension IS NULL OR (unit_dimension <> stock_dimension AND f IS NULL) THEN
        RAISE EXCEPTION 'unit requires a compatible dimension or explicit item conversion';
      END IF;
      IF NEW.photo_object_key IS NOT NULL AND NEW.photo_object_key NOT LIKE s.organization_id::text || '/' || s.location_id::text || '/%' THEN
        RAISE EXCEPTION 'photo metadata must be scoped to the session location';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER inventory_count_line_guard BEFORE INSERT OR UPDATE OR DELETE ON inventory_count_lines
      FOR EACH ROW EXECUTE FUNCTION inventory_count_line_guard();

    CREATE FUNCTION inventory_ledger_posting_clock() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM pg_advisory_xact_lock(hashtextextended(NEW.organization_id::text || ':' || NEW.location_id::text, 0));
      NEW.created_at := clock_timestamp();
      RETURN NEW;
    END $$;
    CREATE TRIGGER stock_movements_posting_clock BEFORE INSERT ON stock_movements
      FOR EACH ROW EXECUTE FUNCTION inventory_ledger_posting_clock();

    CREATE FUNCTION inventory_count_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
        JOIN employees e ON e.user_id = a.user_id AND e.organization_id = a.organization_id AND e.location_id = a.location_id
        WHERE a.user_id = NEW.assigned_to AND a.organization_id = NEW.organization_id AND a.location_id = NEW.location_id
          AND a.active AND e.status = 'active' AND p.key = 'inventory:count'
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
    CREATE TRIGGER inventory_count_session_guard BEFORE INSERT OR UPDATE ON inventory_count_sessions
      FOR EACH ROW EXECUTE FUNCTION inventory_count_session_guard();
    """))


def downgrade():
    # Return the 2A policies without changing the ledger's original immutability guards.
    for trigger, table in (("inventory_count_session_guard", "inventory_count_sessions"), ("inventory_count_line_guard", "inventory_count_lines"), ("stock_movements_posting_clock", "stock_movements")):
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
    for function in ("inventory_count_session_guard()", "inventory_count_line_guard()", "inventory_ledger_posting_clock()"):
        op.execute(f"DROP FUNCTION {function}")
    for table, policies in (("inventory_count_sessions", ("count_session_read", "count_session_insert", "count_session_update")), ("inventory_count_lines", ("count_line_read", "count_line_insert", "count_line_update", "count_line_delete"))):
        for policy in policies:
            op.execute(f"DROP POLICY {policy} ON {table}")
        scope = "organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
        op.execute(f"CREATE POLICY inventory_location_read_scope ON {table} FOR SELECT USING ({scope})")
        op.execute(f"CREATE POLICY inventory_location_write_scope ON {table} FOR ALL USING ({scope}) WITH CHECK ({scope})")
    op.execute("DROP FUNCTION inventory_reviewer(uuid, uuid)")
    op.execute("DROP FUNCTION inventory_can(uuid, uuid, text)")
    op.drop_constraint("fk_inventory_count_line_counter", "inventory_count_lines", type_="foreignkey")
    op.drop_column("inventory_count_lines", "snapshot")
    op.drop_column("inventory_count_lines", "counted_by")
    op.drop_constraint("fk_inventory_count_zone_scope", "inventory_count_sessions", type_="foreignkey")
    op.drop_constraint("fk_inventory_count_assignee", "inventory_count_sessions", type_="foreignkey")
    op.drop_constraint("ck_inventory_count_version_thresholds", "inventory_count_sessions", type_="check")
    op.execute("UPDATE inventory_count_sessions SET status = 'submitted' WHERE status = 'under_review'")
    op.drop_constraint("ck_inventory_count_sessions_status", "inventory_count_sessions", type_="check")
    op.create_check_constraint("ck_inventory_count_sessions_status", "inventory_count_sessions", "status IN ('draft', 'submitted', 'approved', 'rejected')")
    for column in ("assigned_to", "storage_zone_id", "version", "cutoff_at", "quantity_threshold", "percentage_threshold"):
        op.drop_column("inventory_count_sessions", column)
