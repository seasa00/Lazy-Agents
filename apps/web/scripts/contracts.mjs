// Generate HTTP envelope types from FastAPI without starting the execution service.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import openapiTS, { astToString } from 'openapi-typescript';
import { format, resolveConfig } from 'prettier';
const python = process.env.API_PYTHON || 'python3';
const schema = JSON.parse(
  execFileSync(
    python,
    [
      '-c',
      'import json; from app.main import app; print(json.dumps(app.openapi()))',
    ],
    { cwd: '../api', encoding: 'utf8' },
  ),
);
const target = 'lib/api/openapi.d.ts';
writeFileSync(
  target,
  await format(astToString(await openapiTS(schema)), {
    ...(await resolveConfig(target)),
    parser: 'typescript',
  }),
);
