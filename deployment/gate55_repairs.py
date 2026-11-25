"""Narrow retrieval/confirmation helpers; no independent identity approval."""
import re


def ct_parenthetical_candidate(name, targets, normalize):
    """Retain a complete parent name; later EIN/full-office proof is mandatory."""
    parts=re.fullmatch(r'\s*(.+?)\s*\([^()]{3,160}\)\s*(?:,?\s*(?:inc\.?|incorporated|corp\.?|corporation))?\s*',name,re.I)
    if not parts:return False
    parent=normalize(parts[1])
    return len(parent.split())>=3 and any(parent==normalize(t) for t in targets)


def wi_delimiter_variants(plan,required=()):
    """One delimiter alternative; retain required identities and time allowance."""
    if len(plan)<2:return plan
    alternative=next((re.sub(r',\s+(?=(?:inc\.?|incorporated|corp\.?|corporation)\s*$)',' ',q,flags=re.I).rstrip('.')
        for q in plan[1:] if re.search(r',\s+(?:inc\.?|incorporated|corp\.?|corporation)\s*$',q,re.I)),None)
    if not alternative or alternative.casefold() in {q.casefold() for q in plan}:return plan
    result=[plan[0],alternative,*plan[1:]]
    protected={q.casefold() for q in [plan[0],alternative,*required]}
    while len(result)>len(plan):
        index=next((i for i in range(len(result)-1,0,-1) if result[i].casefold() not in protected),None)
        if index is None:return result  # At most one extra query; original shared deadline still applies.
        result.pop(index)
    return result


def tn_contains_coverage_order(names):
    """Earlier existing literal coverage; no new names or identity assumptions."""
    if len(names)<3:return names
    scored=[]
    for index,name in enumerate(names[1:],1):
        words=re.findall(r'[A-Za-z]+',name)
        if len(words)<3 or len(name)<12 or '(' in name:continue
        count=sum(name.casefold() in other.casefold() for other in names[1:])
        if count>=3:scored.append((-count,index,name))
    if scored:
        _,index,_=min(scored)
        names=[names[0],names[index],*names[1:index],*names[index+1:]]
    # Keep a reviewed acronym. Broad two-letter Contains queries can hit the
    # source's result cap before more distinctive required names get a turn.
    return [names[0], *sorted(names[1:],key=lambda name: bool(re.fullmatch(r'[a-zA-Z]{1,2}',name.strip())))]


def ak_completed_recent_ein_years(master,result):
    proof=result.get('ak_ein_year_evidence')
    if not isinstance(proof,dict) or not result.get('success') or not master.ak_confirmed_identity_result(result):return False
    completed=proof.get('completed_years')
    if not isinstance(completed,list) or any(type(y)is not int for y in completed):return False
    current=master.ak_latest_registration_cycle()
    expected=list(range(current,min(current,master.AK_RECENT_FILING_CUTOFF_YEAR)-1,-1))
    return (proof.get('schema')==1 and proof.get('ein')==master.canonical_ein_digits(result.get('ein',''))
        and proof.get('expected_recent_years')==expected
        and set(expected)<=set(completed))
