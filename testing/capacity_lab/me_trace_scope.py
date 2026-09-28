"""Normalize only Maine's inclusion in the existing passive trace observer."""
import ast

def strip_me_transport_trace(tree):
    for fn in tree.body:
        if getattr(fn,'name','')=='transport_route':
            for node in ast.walk(fn):
                if isinstance(node,ast.Try):
                    found=[n for n in node.body if isinstance(n,ast.If) and ast.unparse(n.test)=="state == 'ME' and parsed.hostname == 'www.pfr.maine.gov'"]
                    for n in found:
                        assert len(n.body)==1 and not n.orelse
                        assert ast.unparse(n.body[0])=="return {'/almsonline/almsquery/searchcompany.aspx': 'search', '/almsonline/almsquery/searchresults.aspx': 'results', '/almsonline/almsquery/showdetail.aspx': 'details'}.get(parsed.path.casefold())"
                        node.body.remove(n)
        if getattr(fn,'name','') in {'observe_transport','log_transport_failure'}:
            for node in ast.walk(fn):
                if isinstance(node,ast.Set) and all(isinstance(n,ast.Constant) for n in node.elts):
                    labels={n.value for n in node.elts}
                    if labels in ({'MI','NJ','ME'},{'MI','NJ','WI','ME'}):
                        node.elts=[n for n in node.elts if n.value!='ME']
