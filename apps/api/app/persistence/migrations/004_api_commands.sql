CREATE TABLE api_commands (
    scope TEXT NOT NULL,
    key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    receipt TEXT,
    PRIMARY KEY (scope, key)
);
