# New York Search enable wait

The .11 issue-control run retrieved National Housing Trust, then Power to Decide returned `NY_CONNECTOR_SEARCH_BUTTON_TIMEOUT`. Its saved result establishes the failed stage, not the precise reason New York's UI remained disabled. No claim is made that this was a matching error or that all New York intermittency is resolved.

The connector allowed only 3 seconds between successful verification and the real Search button becoming enabled. The official public registry JavaScript updates verification state asynchronously after its verification response. New tests separately schedule response completion and the enabled UI state; valid updates after 4, 10, and 14.9 seconds fail with the old limit and pass with a 15-second limit. A button that never enables still fails at that bounded deadline without clicking Search or returning registration evidence.

Connector 0.3.4 changes only that wait from 3 to 15 seconds. It adds no retry, permissions, token manipulation, or state interpretation. Existing verification rejection, queue, cancellation, rate-limit, and query isolation rules remain unchanged. The backend change only admits connector version 0.3.4; all state search, matching, identity discovery, and status function bodies are unchanged from .11.

Validate the full connector regression and saved-source state controls, then stage the new release and repeat all five reported New York issue controls plus the same frozen random sample. Keep the failed .11 control and every later attempt. Live recovery is required before describing the reported failure as resolved. Production is excluded.
