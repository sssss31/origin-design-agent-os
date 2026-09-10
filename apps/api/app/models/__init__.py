"""Import every model module so `Base.metadata` is complete for Alembic and tests."""

from app.models.agents import Agent, AgentHandoff, AgentSkillBinding, AgentToolBinding, AgentVersion
from app.models.governance import AuditLog, SecretRef
from app.models.identity import Organization, OrganizationMember, RefreshToken, User
from app.models.providers import AIProvider, ProviderModel
from app.models.skills import Skill, SkillFile, SkillVersion
from app.models.tools import Tool, ToolPermission, ToolVersion
from app.models.workspace import Project, ProjectRule, Workspace, WorkspaceMember

__all__ = [
    "AIProvider",
    "Agent",
    "AgentHandoff",
    "AgentSkillBinding",
    "AgentToolBinding",
    "AgentVersion",
    "AuditLog",
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
