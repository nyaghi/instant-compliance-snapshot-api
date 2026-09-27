"""Exact-source recipe used by scope controls to verify unchanged FL rules."""
import textwrap


def expected_fl_business_function(old):
    select_start=old.index('            best_candidate = None\n')
    select_end=old.index('            if not best_candidate:\n', select_start)
    selection=old[select_start:select_end]
    finish_start=old.index('            row_text = best_candidate["row_text"]\n', select_end)
    finish_end=old.index('        except Exception as exc:\n', finish_start)
    finish=old[finish_start:finish_end]
    assert finish.count('                best_result = result\n                continue\n')==1
    finish=finish.replace('                best_result = result\n                continue\n','                return None\n')
    helpers=('    def select_fl_candidate(candidate_rows):\n'
             '        nonlocal alias_review\n'+textwrap.indent(textwrap.dedent(selection),'        ')+
             '        return best_candidate\n\n'
             '    def finish_fl_candidate(result, best_candidate):\n'+
             textwrap.indent(textwrap.dedent(finish),'        ')+'\n')
    new=old[:finish_start]+('            classified = finish_fl_candidate(result, best_candidate)\n'
                         '            if classified is not None:\n'
                         '                return classified\n'
                         '            best_result = result\n'
                         '            continue\n')+old[finish_end:]
    new=new[:select_start]+'            best_candidate = select_fl_candidate(candidate_rows)\n'+new[select_end:]
    new=new.replace('    generated_variants = [\n',helpers+'    generated_variants = [\n',1)
    prefix='''    if (fl_business_lookup_enabled() and search_variants and not getattr(org, "evidence_mode", False)
            and not CAPTURE_EVIDENCE_SCREENSHOTS and not CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT):
        rows = fl_business_public_rows(canonical_name_punctuation(original_name), deadline)
        exact = [row for row in rows if normalized_match_name(row["business_evidence"]["name"])
                 in {normalized_match_name(name) for name in safe_targets}]
        # Extra/inactive names cannot displace the requested legal entity.
        # Multiple exact credentials remain on the existing browser path.
        if len(exact) == 1 and exact[0]["business_evidence"]["status"] in {
                "Registered", "Active Small Charity", "Suspended", "Revoked"}:
            candidate = select_fl_candidate(exact)
            if candidate is not None:
                evidence = exact[0]["business_evidence"]
                alternate = checker.StateResult(original_name, org.ein, "FL", checker.STATUS_UNKNOWN, evidence["url"])
                confirmed = finish_fl_candidate(alternate, candidate)
                if confirmed is not None:
                    confirmed.source_note = "FL uses the charity license status and expiration date in the official FDACS Business Lookup."
                    confirmed._cc_registration_date_evidence = evidence
                    confirmed._cc_fl_business_source_verified = True
                    return confirmed
'''
    new=new.replace('    for variant in search_variants:\n',prefix+'    for variant in search_variants:\n',1)
    return new
