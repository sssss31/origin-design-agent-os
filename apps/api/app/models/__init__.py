"""Import every model module so `Base.metadata` is complete for Alembic and tests."""

from app.models.agents import Agent, AgentHandoff, AgentSkillBinding, AgentToolBinding, AgentVersion
from app.models.chat import Conversation, Message, MessageAttachment
from app.models.files import Artifact, ArtifactVersion, Asset, AssetVersion
from app.models.governance import AuditLog, SecretRef
from app.models.identity import Organization, OrganizationMember, RefreshToken, User
from app.models.integrations import CustomIntegration, IntegrationSecret
from app.models.providers import AIProvider, ProviderModel
from app.models.skills import Skill, SkillFile, SkillVersion
from app.models.tools import Tool, ToolPermission, ToolVersion
from app.models.workflows import (
    ApiUsage,
    ErrorEvent,
    ExecutionEvent,
    ModelPricing,
    NodeRun,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowVersion,
)
from app.models.workspace import Project, ProjectRule, Workspace, WorkspaceMember

__all__ = [
    "Artifact",
    "ArtifactVersion",
    "Asset",
    "AssetVersion",
    "Conversation",
    "Message",
    "MessageAttachment",
    "AIProvider",
    "Agent",
    "AgentHandoff",
    "AgentSkillBinding",
    "AgentToolBinding",
    "AgentVersion",
    "ApiUsage",
    "ErrorEvent",
    "ExecutionEvent",
    "NodeRun",
    "WorkflowDefinition",
    "WorkflowRun",
    "WorkflowVersion",
    "AuditLog",
    "CustomIntegration",
    "IntegrationSecret",
    "ModelPricing",
    "Organization",
    "OrganizationMember",
    "Project",
    "ProjectRule",
    "ProviderModel",
    "RefreshToken",
    "SecretRef",
    "Skill",
    "SkillFile",
    "SkillVersion",
    "Tool",
    "ToolPermission",
    "ToolVersion",
    "User",
    "Workspace",
    "WorkspaceMember",
]
