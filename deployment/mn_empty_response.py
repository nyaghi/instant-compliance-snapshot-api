"""Recognize the public portal's completed, query-bound empty result layout."""
from urllib.parse import urlsplit


def complete(page, query):
    if not isinstance(page.url, str):
        return False
    url = urlsplit(page.url)
    if (url.scheme != 'https' or url.netloc != 'www.ag.state.mn.us'
            or url.path.lower() != '/charity/search/results.asp' or url.query or url.fragment
            or not isinstance(query, str) or not query.strip() or '\ufffd' in query):
        return False
    try:
        return page.locator('#content').evaluate(r'''(content, query) => {
          const norm = s => (s || '').replace(/\s+/g, ' ').trim().replace(/\s*"\s*/g, '"');
          const headings = content.querySelectorAll('h1');
          const echoes = content.querySelectorAll('h4 strong');
          const restart = [...content.querySelectorAll('a')];
          if (headings.length !== 1 || echoes.length !== 1 || restart.length !== 1
              || !content.getClientRects().length || !echoes[0].getClientRects().length
              || norm(headings[0].textContent) !== 'Search Organization Database'
              || echoes[0].textContent.trim() !== query.trim()
              || norm(restart[0].textContent) !== 'Conduct New Search'
              || new URL(restart[0].href).pathname.toLowerCase() !== '/charity/search/default.asp'
              || content.querySelector('table, iframe, input, [role="alert"], [role="progressbar"]')) return false;
          // No unrecognized message, hidden result row, spinner or error may be
          // discarded merely because this layout has no table.
          // The publisher emits a raw 0xA0 separator despite declaring UTF-8.
          // Permit its one trailing replacement glyph after the restart link,
          // never replacement characters inside a query or a result/error.
          const text = norm(content.textContent).replace(/(Conduct New Search)\s*\uFFFD$/, '$1');
          return text === norm('Search Organization Database Showing Results for "'
            + query.trim() + '" Conduct New Search');
        }''', query, timeout=1000) is True
    except Exception:
        return False
