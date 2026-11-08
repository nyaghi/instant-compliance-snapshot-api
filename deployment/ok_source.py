"""Official Oklahoma charity search and archived-source host allowlist."""

HOST = "business.sos.ok.gov"
ARCHIVED_HOSTS = frozenset({HOST, "www.sos.ok.gov"})
SEARCH_URL = f"https://{HOST}/corp/charityInquiryFind.aspx"
DETAIL_URL = f"https://{HOST}/corp/charityDetail.aspx?id="
