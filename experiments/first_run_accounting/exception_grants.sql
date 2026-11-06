-- REVIEW CANDIDATE ONLY: apply only after separate approval and schema install.
-- No credentials, roles, policy rows, or table privileges are created.
BEGIN;
GRANT USAGE ON SCHEMA dev_agent_canary_exception TO dev_agent_verifier_v27;
GRANT EXECUTE ON FUNCTION dev_agent_canary_exception.consume(text,bigint,bigint,integer,text,text,text)
 TO dev_agent_verifier_v27;
COMMIT;
