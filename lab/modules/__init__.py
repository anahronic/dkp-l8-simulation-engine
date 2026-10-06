"""Installed lab modules (the only ones the API and the UI can run)."""

from lab.modules.prevention import PreventionModule
from lab.modules.time import TimeModule
from lab.modules.work_cycle import WorkCycleModule

MODULES = {m.id: m for m in (PreventionModule(), TimeModule(), WorkCycleModule())}
