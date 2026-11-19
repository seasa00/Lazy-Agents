export interface paths {
  '/projects': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Projects */
    get: operations['projects_projects_get'];
    put?: never;
    /** Create */
    post: operations['create_projects_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/snapshot': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Snapshot */
    get: operations['snapshot_projects__project_id__snapshot_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Snapshot */
    get: operations['snapshot_projects__project_id__get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/settings': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Settings */
    get: operations['settings_projects__project_id__settings_get'];
    put?: never;
    /** Configure */
    post: operations['configure_projects__project_id__settings_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/runs/{run_id}/inspection': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Inspection */
    get: operations['inspection_projects__project_id__runs__run_id__inspection_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/plan': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Plan */
    post: operations['plan_projects__project_id__plan_post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/runs/{run_id}/{action}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    get?: never;
    put?: never;
    /** Command */
    post: operations['command_projects__project_id__runs__run_id___action__post'];
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/runs/{run_id}/{kind}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Read */
    get: operations['read_projects__project_id__runs__run_id___kind__get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/runs/{run_id}/artifacts/{submission_id}': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Artifact */
    get: operations['artifact_projects__project_id__runs__run_id__artifacts__submission_id__get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
  '/projects/{project_id}/events': {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    /** Events */
    get: operations['events_projects__project_id__events_get'];
    put?: never;
    post?: never;
    delete?: never;
    options?: never;
    head?: never;
    patch?: never;
    trace?: never;
  };
}
export type webhooks = Record<string, never>;
export interface components {
  schemas: {
    /** AgentSettings */
    AgentSettings: {
      /** Expected Version */
      expected_version: number;
      /**
       * Kind
       * @enum {string}
       */
      kind: 'manager' | 'developer' | 'reviewer';
      /** Name */
      name: string;
      /** Role */
      role: string;
      /** Model */
      model: string;
      /** System Instructions */
      system_instructions: string;
    };
    /** Command */
    Command: {
      /** Expected Version */
      expected_version: number;
      /** Approval Id */
      approval_id?: string | null;
      /** Approved */
      approved?: boolean | null;
      /** Operation Id */
      operation_id?: string | null;
      /** Action */
      action?: string | null;
      /**
       * Reason
       * @default
       */
      reason: string;
      /** Expected Epoch */
      expected_epoch?: number | null;
      /**
       * Quiescent
       * @default false
       */
      quiescent: boolean;
    };
    /** CommandAcknowledgement */
    CommandAcknowledgement: {
      /** Command Id */
      command_id: string;
      /**
       * Status
       * @enum {string}
       */
      status: 'pending' | 'applied' | 'rejected';
      /** Project Id */
      project_id: string;
      /** Run Id */
      run_id?: string | null;
      /** Project Version */
      project_version?: number | null;
      /** Event Cursor */
      event_cursor?: number | null;
      /** Error */
      error?: string | null;
    };
    /** CreateProject */
    CreateProject: {
      /** Name */
      name: string;
      /** Goal */
      goal: string;
      /** Requirements */
      requirements: components['schemas']['RequirementInput'][];
    };
    /** HTTPValidationError */
    HTTPValidationError: {
      /** Detail */
      detail?: components['schemas']['ValidationError'][];
    };
    /** ProjectSnapshot */
    ProjectSnapshot: {
      /**
       * Schema Version
       * @default 1
       * @constant
       */
      schema_version: 1;
      /** Project */
      project: {
        [key: string]: unknown;
      };
      /** Event Cursor */
      event_cursor: number;
    };
    /** RequirementInput */
    RequirementInput: {
      /** Id */
      id: string;
      /** Description */
      description: string;
      /** Acceptance Criteria */
      acceptance_criteria: string[];
      /**
       * Priority
       * @default normal
       */
      priority: string;
    };
    /** ValidationError */
    ValidationError: {
      /** Location */
      loc: (string | number)[];
      /** Message */
      msg: string;
      /** Error Type */
      type: string;
      /** Input */
      input?: unknown;
      /** Context */
      ctx?: Record<string, never>;
    };
  };
  responses: never;
  parameters: never;
  requestBodies: never;
  headers: never;
  pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
  projects_projects_get: {
    parameters: {
      query?: never;
      header?: never;
      path?: never;
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': unknown;
        };
      };
    };
  };
  create_projects_post: {
    parameters: {
      query?: never;
      header: {
        'idempotency-key': string;
      };
      path?: never;
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['CreateProject'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CommandAcknowledgement'];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  snapshot_projects__project_id__snapshot_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ProjectSnapshot'];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  snapshot_projects__project_id__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['ProjectSnapshot'];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  settings_projects__project_id__settings_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  configure_projects__project_id__settings_post: {
    parameters: {
      query?: never;
      header: {
        'idempotency-key': string;
      };
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['AgentSettings'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CommandAcknowledgement'];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  inspection_projects__project_id__runs__run_id__inspection_get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        run_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  plan_projects__project_id__plan_post: {
    parameters: {
      query?: never;
      header: {
        'idempotency-key': string;
      };
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['Command'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CommandAcknowledgement'];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  command_projects__project_id__runs__run_id___action__post: {
    parameters: {
      query?: never;
      header: {
        'idempotency-key': string;
      };
      path: {
        project_id: string;
        run_id: string;
        action:
          | 'approve'
          | 'start'
          | 'pause'
          | 'resume'
          | 'cancel'
          | 'permission'
          | 'recovery';
      };
      cookie?: never;
    };
    requestBody: {
      content: {
        'application/json': components['schemas']['Command'];
      };
    };
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['CommandAcknowledgement'];
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  read_projects__project_id__runs__run_id___kind__get: {
    parameters: {
      query?: never;
      header?: never;
      path: {
        project_id: string;
        run_id: string;
        kind:
          | 'tasks'
          | 'reviews'
          | 'evidence'
          | 'usage'
          | 'permissions'
          | 'recovery';
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  artifact_projects__project_id__runs__run_id__artifacts__submission_id__get: {
    parameters: {
      query: {
        path: string;
      };
      header?: never;
      path: {
        project_id: string;
        run_id: string;
        submission_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
  events_projects__project_id__events_get: {
    parameters: {
      query?: {
        after?: number;
      };
      header?: {
        'last-event-id'?: string | null;
      };
      path: {
        project_id: string;
      };
      cookie?: never;
    };
    requestBody?: never;
    responses: {
      /** @description Successful Response */
      200: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': unknown;
        };
      };
      /** @description Validation Error */
      422: {
        headers: {
          [name: string]: unknown;
        };
        content: {
          'application/json': components['schemas']['HTTPValidationError'];
        };
      };
    };
  };
}
