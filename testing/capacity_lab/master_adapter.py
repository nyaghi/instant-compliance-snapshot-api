"""Local integration seam; never imported by the deployed master backend.

The caller must already authorize the workflow. This adapter is not an HTTP
authentication layer. The master retains normalization and reviewed-name scope.
Existing state adapters still need internal cooperative cancellation; these
outer checkpoints cannot interrupt a blocking registry/browser operation.
"""


class MasterAdapter:
    def __init__(self, master):
        self.master = master

    def __call__(self, payload, control):
        control.checkpoint()
        state = str(payload.get('state', '')).strip().upper()
        if state not in self.master.SUPPORTED_STATES:
            raise ValueError('Unsupported state')
        organizations = self.master.normalize_organization_requests(payload, privileged=False)
        if len(organizations) != 1:
            raise ValueError('A worker job must identify exactly one organization')
        result = self.master.run_state_lookups_parallel(organizations, [state])
        control.checkpoint()
        if len(result) != 1:
            raise ValueError('Unexpected worker result count')
        return result[0]
