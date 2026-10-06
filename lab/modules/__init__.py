"""Installed lab modules (the only ones the API and the UI can run)."""

from lab.modules.contribution import ContributionModule
from lab.modules.dispute_correction import DisputeCorrectionModule
from lab.modules.failure_chain import FailureChainModule
from lab.modules.prevention import PreventionModule
from lab.modules.sensor_loss import SensorLossModule
from lab.modules.time import TimeModule
from lab.modules.work_cycle import WorkCycleModule

MODULES = {m.id: m for m in (PreventionModule(), TimeModule(), WorkCycleModule(), FailureChainModule(),
                             DisputeCorrectionModule(), ContributionModule(), SensorLossModule())}
