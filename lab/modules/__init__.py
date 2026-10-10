"""Installed lab modules (the only ones the API and the UI can run)."""

from lab.modules.ai_subject import AiSubjectModule
from lab.modules.audit_trace import AuditTraceModule
from lab.modules.axiom_constraints import AxiomConstraintsModule
from lab.modules.calibration_expiry import CalibrationExpiryModule
from lab.modules.code_economy import CodeEconomyModule
from lab.modules.code_synergy import CodeSynergyModule
from lab.modules.contribution import ContributionModule
from lab.modules.crisis_recovery import CrisisRecoveryModule
from lab.modules.defense_envelope import DefenseEnvelopeModule
from lab.modules.dispute_correction import DisputeCorrectionModule
from lab.modules.economic_access import EconomicAccessModule
from lab.modules.edition_finality import EditionFinalityModule
from lab.modules.edu_culture import EduCultureModule
from lab.modules.epistemic_gate import EpistemicGateModule
from lab.modules.exit_integration import ExitIntegrationModule
from lab.modules.failure_chain import FailureChainModule
from lab.modules.finance_mechanics import FinanceMechanicsModule
from lab.modules.habitat_dignity import HabitatDignityModule
from lab.modules.impact_attribution import ImpactAttributionModule
from lab.modules.info_truth import InfoTruthModule
from lab.modules.internal_security import InternalSecurityModule
from lab.modules.interop_failure import InteropFailureModule
from lab.modules.oracle_ingestion import OracleIngestionModule
from lab.modules.police_antiterror import PoliceAntiterrorModule
from lab.modules.prevention import PreventionModule
from lab.modules.property_rights import PropertyRightsModule
from lab.modules.privacy_transparency import PrivacyTransparencyModule
from lab.modules.resilience_structure import ResilienceStructureModule
from lab.modules.scope_gate import ScopeGateModule
from lab.modules.sensor_loss import SensorLossModule
from lab.modules.simulation_gate import SimulationGateModule
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
                             PoliceAntiterrorModule(), AxiomConstraintsModule(),
                             InfoTruthModule(), PrivacyTransparencyModule(),
                             EduCultureModule(), AiSubjectModule(), CodeSynergyModule(),
                             CodeEconomyModule(), ScopeGateModule(),
                             OracleIngestionModule(), ImpactAttributionModule(),
                             EpistemicGateModule(), AuditTraceModule(),
                             SimulationGateModule(), DefenseEnvelopeModule(),
                             HabitatDignityModule(), ResilienceStructureModule(),
                             EditionFinalityModule(), FinanceMechanicsModule(),
                             PropertyRightsModule())}
