# Chubby AI repository guidance

## Product and security constraints
- This is a multi-organization, multi-location restaurant operating platform. Resolve organization and location access on the server from the authenticated user's assignments; never trust a client-supplied location identifier by itself.
- Enforce tenant isolation in application authorization and PostgreSQL Row-Level Security. Application database sessions must set transaction-local tenant context and must not connect as a superuser or a role with `BYPASSRLS`.
- Store only password hashes, use secure opaque server-side sessions, and keep credentials in environment variables locally and managed secrets in production. Never commit secrets.
- Audit security and administrative events. Ordinary application operations must not update or delete audit records.
- AI recommendations are records for human review only. Never execute financial, HR, or inventory actions automatically.
- Keep permissions configurable and location-aware. Add locations as data, not schema changes.

## Engineering practices
- Keep the frontend and backend typed and validate all API inputs at the boundary.
- Add migrations for schema changes. Do not rely on automatic production schema creation.
- Add automated coverage for authentication, authorization, tenant/location isolation, RLS, audit logging, expiration, and validation as these components are introduced.
- Do not claim a test, staging deployment, or security property succeeded unless it was actually verified. Local development is not a staging deployment.
- Keep services in a small, understandable application architecture; Redis and a worker are infrastructure foundations, not excuses to create unnecessary services.
- Update architecture/runbook documentation when implementation decisions change.
