"""Adapters for *existing* agents (Origin Agent Workspace V0 §7, §34).

Origin does not recreate the agents: it sends the user message (+ conversation context +
files) to the agent's own API and relays the answer. One `AgentGateway` interface, small
adapters per API contract.
"""
