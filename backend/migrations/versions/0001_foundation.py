"""Initial tenant-aware platform schema."""
from alembic import op
from sqlalchemy import text
from app.db import Base
import app.models  # noqa: F401

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # Establish the bootstrap tenant context for this migration transaction. The
    # same GUCs are set per request by the authenticated API in the next milestone.
    op.execute("SELECT set_config('app.organization_id', '00000000-0000-0000-0000-000000000001', true)")
    op.execute("SELECT set_config('app.location_ids', '00000000-0000-0000-0000-000000000002', true)")
    tenant_tables = ["organizations", "locations", "employees", "user_location_assignments", "devices", "notifications", "ai_recommendations", "approval_requests", "invitation_locations"]
    for table in tenant_tables:
        op.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        if table == "user_location_assignments":
            visible = "user_id::text = current_setting('app.user_id', true) OR (organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')))"
            own_insert = "user_id::text = current_setting('app.user_id', true) AND organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
            op.execute(text(f"CREATE POLICY assignment_read_scope ON {table} FOR SELECT USING ({visible})"))
            op.execute(text(f"CREATE POLICY assignment_insert_self ON {table} FOR INSERT WITH CHECK ({own_insert})"))
            continue
        if table == "organizations":
            policy = "id::text = current_setting('app.organization_id', true)"
        elif table == "locations":
            policy = "organization_id::text = current_setting('app.organization_id', true) AND (id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')) OR current_setting('app.can_read_all_locations', true) = 'true')"
        elif table == "employees":
            policy = "user_id::text = current_setting('app.user_id', true) OR (organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')) AND current_setting('app.can_read_location_employees', true) = 'true')"
        elif table == "invitation_locations":
            policy = "organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
        elif table == "notifications":
            policy = "user_id::text = current_setting('app.user_id', true)"
        else:
            policy = "organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))"
        op.execute(text(f"CREATE POLICY tenant_scope ON {table} USING ({policy}) WITH CHECK ({policy})"))
    op.execute(text("REVOKE INSERT, UPDATE, DELETE ON roles, permissions, role_permissions, alembic_version FROM chubby_app"))
    op.execute(text("GRANT SELECT ON roles, permissions, role_permissions TO chubby_app"))
    for table in ["users", "sessions", "password_reset_tokens"]:
        op.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    op.execute(text("CREATE POLICY user_scope ON users USING (id::text = current_setting('app.user_id', true) OR lower(email) = current_setting('app.login_email', true)) WITH CHECK (id::text = current_setting('app.user_id', true))"))
    op.execute(text("CREATE POLICY session_scope ON sessions USING (token_hash = current_setting('app.session_token_hash', true) OR user_id::text = current_setting('app.user_id', true)) WITH CHECK (user_id::text = current_setting('app.user_id', true))"))
    op.execute(text("CREATE POLICY password_reset_scope ON password_reset_tokens USING (user_id::text = current_setting('app.user_id', true) OR token_hash = current_setting('app.password_reset_token_hash', true)) WITH CHECK (user_id::text = current_setting('app.user_id', true))"))
    op.execute(text("ALTER TABLE invitations ENABLE ROW LEVEL SECURITY"))
    op.execute(text("ALTER TABLE invitations FORCE ROW LEVEL SECURITY"))
    op.execute(text("CREATE POLICY tenant_scope ON invitations USING (organization_id::text = current_setting('app.organization_id', true) OR token_hash = current_setting('app.invitation_token_hash', true)) WITH CHECK (organization_id::text = current_setting('app.organization_id', true))"))
    op.execute(text("CREATE POLICY invitation_location_scope ON invitation_locations USING (invitation_id::text = current_setting('app.invitation_id', true) OR (organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')))) WITH CHECK (organization_id::text = current_setting('app.organization_id', true) AND location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')))"))
    op.execute(text("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY"))
    op.execute(text("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY"))
    audit_scope = "((organization_id IS NULL AND location_id IS NULL AND (user_id IS NULL OR user_id::text = current_setting('app.user_id', true))) OR (organization_id::text = current_setting('app.organization_id', true) AND (location_id IS NULL OR location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ',')))))"
    audit_read_scope = "(organization_id::text = current_setting('app.organization_id', true) AND (location_id IS NULL OR location_id::text = ANY(string_to_array(current_setting('app.location_ids', true), ','))))"
    op.execute(text(f"CREATE POLICY audit_read_scope ON audit_logs FOR SELECT USING {audit_read_scope}"))
    op.execute(text(f"CREATE POLICY audit_insert_scope ON audit_logs FOR INSERT WITH CHECK {audit_scope}"))
    op.execute(text("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'chubby_app') THEN
                REVOKE UPDATE, DELETE ON audit_logs FROM chubby_app;
            END IF;
        END $$
    """))
    op.execute(text("""
        CREATE FUNCTION prevent_audit_log_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'audit logs are append-only';
        END $$
    """))
    op.execute(text("CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()"))
    op.execute(text("""
        INSERT INTO organizations (id, name, slug, status)
        VALUES ('00000000-0000-0000-0000-000000000001', 'Chubby Group', 'chubby-group', 'active')
        ON CONFLICT (slug) DO NOTHING
    """))
    op.execute(text("""
        INSERT INTO locations (id, organization_id, name, code, status)
        VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', 'Chubby Dumplings Burbank', 'BURBANK-001', 'active')
        ON CONFLICT (organization_id, code) DO NOTHING
    """))
    op.execute(text("""
        INSERT INTO roles (id, name, scope) VALUES
        ('00000000-0000-0000-0000-000000000011', 'Platform Administrator', 'platform'),
        ('00000000-0000-0000-0000-000000000012', 'Corporate Owner', 'organization'),
        ('00000000-0000-0000-0000-000000000013', 'Corporate Operations Manager', 'organization'),
        ('00000000-0000-0000-0000-000000000014', 'Regional Manager', 'location'),
        ('00000000-0000-0000-0000-000000000015', 'General Manager', 'location'),
        ('00000000-0000-0000-0000-000000000016', 'Employee', 'location') ON CONFLICT (name) DO NOTHING
    """))
    permissions = [
        ("dashboard:read", "View the assigned restaurant dashboard"),
        ("location:read", "View assigned location details"),
        ("employee:read:location", "View employee profiles for an assigned location"),
        ("user:invite", "Invite users to authorized locations"),
        ("profile:read:self", "View the signed-in user's own employee profile"),
        ("notification:read:self", "View notifications addressed to the signed-in user"),
        ("task:read:self", "View tasks assigned to the signed-in user"),
        ("sop:read", "View standard operating procedures"),
    ]
    for key, description in permissions:
        op.execute(text("INSERT INTO permissions (id, key, description) VALUES (gen_random_uuid(), :key, :description) ON CONFLICT (key) DO NOTHING").bindparams(key=key, description=description))
    role_permissions = {
        "Corporate Owner": ["dashboard:read", "location:read", "employee:read:location", "user:invite"],
        "General Manager": ["dashboard:read", "location:read", "employee:read:location", "profile:read:self", "notification:read:self", "task:read:self"],
        "Employee": ["profile:read:self", "notification:read:self", "task:read:self", "sop:read"],
    }
    for role_name, keys in role_permissions.items():
        for key in keys:
            op.execute(text("INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.name = :role_name AND p.key = :permission_key ON CONFLICT DO NOTHING").bindparams(role_name=role_name, permission_key=key))


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
    Base.metadata.drop_all(bind=op.get_bind())
