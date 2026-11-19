"""Disposable M5.2 inspection fixtures; no production routes or workflow rules.

Seed a completed real-file workflow and interrupt a Reviewer after its durable
execution fence. The application startup uses the normal M4.2 recovery gate.
"""
from app.agents.contracts import Requirement
from app.domain.projects import ProjectState


def seed(store, factory):
    if store.list_projects():
        return
    for identity, name, interrupt in (
        ('inspection-completed', 'Completed evidence fixture', False),
        ('inspection-interrupted', 'Interrupted recovery fixture', True),
    ):
        store.create_project(ProjectState(identity, name, 'Inspect a bounded greeting change.',
            requirements=(Requirement('r1', 'Greeting contains hello world', ('Greeting contains hello world',)),)))
        run = store.create_run(identity)
        runner = factory(store, identity, run.id)
        runner.provider.hook = None
        runner.initialize()
        runner.run_until_stopped()
        runner.approve()
        runner.run_until_stopped()  # exact runtime permission request
        approval = store.approvals(identity, run.id)[0]
        runner.controls.resolve_command(approval.id, approved=True, reason='Trusted disposable fixture setup')
        if interrupt:
            def crash(request):
                if request.context['workflow']['phase'] == 'review':
                    raise SystemExit('controlled interruption after durable provider fence')
            runner.provider.hook = crash
            try:
                runner.run_until_stopped()
            except SystemExit:
                pass
        else:
            runner.run_until_stopped()
