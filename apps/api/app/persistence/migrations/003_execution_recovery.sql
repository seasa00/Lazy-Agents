CREATE TABLE execution_operations (
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    id TEXT NOT NULL,
    kind TEXT NOT NULL,
    stage TEXT NOT NULL,
    certainty TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY(project_id,run_id,id),
    FOREIGN KEY(project_id,run_id) REFERENCES runs(project_id,id)
);
CREATE INDEX operations_run_stage ON execution_operations(project_id,run_id,stage);
