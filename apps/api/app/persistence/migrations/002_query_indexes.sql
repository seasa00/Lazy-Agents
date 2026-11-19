CREATE INDEX events_project_sequence ON events(project_id,sequence);
CREATE INDEX llm_calls_agent ON llm_calls(project_id,run_id,agent_id);
