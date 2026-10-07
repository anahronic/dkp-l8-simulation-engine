"""Installed lab modules (the only ones the API and the UI can run)."""

from lab.modules.axiom_constraints import AxiomConstraintsModule
from lab.modules.calibration_expiry import CalibrationExpiryModule
from lab.modules.contribution import ContributionModule
from lab.modules.crisis_recovery import CrisisRecoveryModule
from lab.modules.dispute_correction import DisputeCorrectionModule
from lab.modules.economic_access import EconomicAccessModule
from lab.modules.exit_integration import ExitIntegrationModule
from lab.modules.failure_chain import FailureChainModule
from lab.modules.internal_security import InternalSecurityModule
from lab.modules.interop_failure import InteropFailureModule
from lab.modules.police_antiterror import PoliceAntiterrorModule
from lab.modules.prevention import PreventionModule
from lab.modules.sensor_loss import SensorLossModule
from lab.modules.time import TimeModule
from lab.modules.transport_capacity import TransportCapacityModule
from lab.modules.upgrade_lifecycle import UpgradeLifecycleModule
from lab.modules.work_cycle import WorkCycleModule

MODULES = {m.id: m for m in (PreventionModule(), TimeModule(), WorkCycleModule(), FailureChainModule(),
                             DisputeCorrectionModule(), ContributionModule(), SensorLossModule(),
                             CrisisRecoveryModule(), ExitIntegrationModule(),
                             InteropFailureModule(), CalibrationExpiryModule(),
                             TransportCapacityModule(), EconomicAccessModule(),
                             UpgradeLifecycleModule(), InternalSecurityModule(),
                             PoliceAntiterrorModule(), AxiomConstraintsModule())}
