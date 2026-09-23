"""Provider adapters (spec §13): one interface, many backends.

`AIProvider` is the boundary between Origin and any model vendor. Everything that talks to
a vendor (execution, connection tests, model discovery, usage pricing, parameter support)
lives behind it so the rest of the system never depends on one provider's SDK.
"""
