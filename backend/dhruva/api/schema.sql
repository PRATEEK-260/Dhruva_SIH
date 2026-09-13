-- advisory_log is a REQUEST LOG, not vessel tracking. No boat ever reports a
-- position back to shore in this architecture (CLAUDE.md: the NavIC uplink is
-- ISRO's, no team transmits) -- this table only records that an advisory was
-- requested, from where, and what verdict came back. Never read a row here
-- as "this boat is currently there."
CREATE TABLE IF NOT EXISTS advisory_log (
    id          bigserial PRIMARY KEY,
    boat_class  text NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    risk_class  text NOT NULL,
    issued_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS advisory_log_issued_idx ON advisory_log (issued_at DESC);
